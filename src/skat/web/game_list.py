from typing import TYPE_CHECKING, Annotated, Final, Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from skat.engine.kontra import Word  # noqa: TC001 - pydantic reads the field type at runtime
from skat.engine.value import Level  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.game_list import GameEnding, RamschSeriesEntryView
from skat.table.game_sheet import CardState, DeclaredCount
from skat.web.declaration_tokens import ANNOUNCEMENT_TOKENS, GAME_TOKENS, AnnouncementToken, GameToken
from skat.web.mcp import READ_SERIES_LIST_MARK, Exclusion, excluded
from skat.web.tables import TABLES_PATH, CardAnswer, SeatedCardAnswer, card_answer_of

if TYPE_CHECKING:
    from skat.table.game_cards import SeatedCard
    from skat.table.game_list import SeriesEntryView
    from skat.table.game_sheet import GameSheetView, SheetCard, SheetCards, SheetHand, SheetTrick
    from skat.table.service import TableService

# The table's list of finished games: `TABLES_PATH/{table_id}` plus this.
TABLE_LIST_SUFFIX: Final = "/list"


class SeriesEntryAnswer(BaseModel):
    kind: Literal["declared"]
    number: int
    declarer_name: str | None
    game: GameToken
    hand: bool
    ouvert: bool
    announcement: AnnouncementToken
    levels: list[Level]
    settled_value: int
    score: int
    declarer_points: int
    kontra_word: Word | None
    bock_factor: int


class RamschSeriesSeatAnswer(BaseModel):
    name: str | None
    score: int


class RamschSeriesEntryAnswer(BaseModel):
    kind: Literal["ramsch"]
    number: int
    seats: list[RamschSeriesSeatAnswer]
    durchmarsch: bool
    jungfrau: bool
    bock_factor: int
    pushes: int
    push_factor: int


class SeriesListAnswer(BaseModel):
    entries: list[Annotated[SeriesEntryAnswer | RamschSeriesEntryAnswer, Field(discriminator="kind")]]


def _entry_answer_of(entry: SeriesEntryView | RamschSeriesEntryView) -> SeriesEntryAnswer | RamschSeriesEntryAnswer:
    if isinstance(entry, RamschSeriesEntryView):
        return RamschSeriesEntryAnswer(
            kind="ramsch",
            number=entry.number,
            seats=[RamschSeriesSeatAnswer(name=seat.name, score=seat.score) for seat in entry.seats],
            durchmarsch=entry.durchmarsch,
            jungfrau=entry.jungfrau,
            bock_factor=entry.bock_factor,
            pushes=entry.pushes,
            push_factor=entry.push_factor,
        )
    declaration = entry.declaration
    return SeriesEntryAnswer(
        kind="declared",
        number=entry.number,
        declarer_name=entry.declarer_name,
        game=GAME_TOKENS[declaration.kind],
        hand=declaration.hand,
        ouvert=declaration.ouvert,
        announcement=ANNOUNCEMENT_TOKENS[declaration.announcement],
        levels=list(entry.levels),
        settled_value=entry.settled_value,
        score=entry.score,
        declarer_points=entry.declarer_points,
        kontra_word=entry.kontra_word,
        bock_factor=entry.bock_factor,
    )


class SheetCardAnswer(BaseModel):
    card: CardAnswer
    state: CardState


class SheetHandAnswer(BaseModel):
    seat: int
    cards: list[SheetCardAnswer]


class SheetTrickAnswer(BaseModel):
    number: int
    cards: list[SeatedCardAnswer]
    taker_seat: int | None
    points: int | None


class SheetCardsAnswer(BaseModel):
    hands: list[SheetHandAnswer]
    skat: list[CardAnswer]
    laid_skat: list[CardAnswer]
    put_away: list[SeatedCardAnswer]
    tricks: list[SheetTrickAnswer]
    skat_takers: list[int]


class DeclaredCountAnswer(BaseModel):
    kind: Literal["declared"]
    declarer_seat: int
    declarer_points: int
    opponents_points: int
    ending: GameEnding
    ended_by_seat: int | None


class RamschCountAnswer(BaseModel):
    kind: Literal["ramsch"]
    seat_points: list[int]
    durchmarsch_seat: int | None


class GameSheetAnswer(BaseModel):
    number: int
    seat_names: list[str | None]
    count: Annotated[DeclaredCountAnswer | RamschCountAnswer, Field(discriminator="kind")]
    cards: SheetCardsAnswer | None


def _seated_answer_of(played: SeatedCard) -> SeatedCardAnswer:
    return SeatedCardAnswer(seat=played.seat, card=card_answer_of(played.card))


def _sheet_card_answer_of(held: SheetCard) -> SheetCardAnswer:
    return SheetCardAnswer(card=card_answer_of(held.card), state=held.state)


def _sheet_hand_answer_of(hand: SheetHand) -> SheetHandAnswer:
    return SheetHandAnswer(seat=hand.seat, cards=[_sheet_card_answer_of(held) for held in hand.cards])


def _sheet_trick_answer_of(trick: SheetTrick) -> SheetTrickAnswer:
    return SheetTrickAnswer(
        number=trick.number,
        cards=[_seated_answer_of(played) for played in trick.cards],
        taker_seat=trick.taker_seat,
        points=trick.points,
    )


def _cards_answer_of(cards: SheetCards) -> SheetCardsAnswer:
    return SheetCardsAnswer(
        hands=[_sheet_hand_answer_of(hand) for hand in cards.hands],
        skat=[card_answer_of(card) for card in cards.skat],
        laid_skat=[card_answer_of(card) for card in cards.laid_skat],
        put_away=[_seated_answer_of(put) for put in cards.put_away],
        tricks=[_sheet_trick_answer_of(trick) for trick in cards.tricks],
        skat_takers=list(cards.skat_takers),
    )


def _sheet_answer_of(sheet: GameSheetView) -> GameSheetAnswer:
    count = sheet.count
    if isinstance(count, DeclaredCount):
        counted = DeclaredCountAnswer(
            kind="declared",
            declarer_seat=count.declarer_seat,
            declarer_points=count.declarer_points,
            opponents_points=count.opponents_points,
            ending=count.ending,
            ended_by_seat=count.ended_by_seat,
        )
    else:
        counted = RamschCountAnswer(
            kind="ramsch", seat_points=list(count.seat_points), durchmarsch_seat=count.durchmarsch_seat
        )
    return GameSheetAnswer(
        number=sheet.number,
        seat_names=list(sheet.seat_names),
        count=counted,
        cards=None if sheet.cards is None else _cards_answer_of(sheet.cards),
    )


def create_game_list_router(tables: TableService) -> APIRouter:
    router = APIRouter()

    @router.get(
        TABLES_PATH + "/{table_id}" + TABLE_LIST_SUFFIX,
        responses={404: {"description": "No table has this id."}},
        openapi_extra=READ_SERIES_LIST_MARK,
    )
    async def read_series_list(table_id: str, response: Response) -> SeriesListAnswer:
        """Read the list of finished games of one Skat table, the same for every caller.

        One entry per game played so far, in the order played, each with its `number` and its `kind`. A `declared`
        entry has the `declarer_name` stored with the game (null for a game stored before names were kept), the
        game, its `levels`, its `settled_value` and the declarer's `score`, which is negative for a lost game, the
        `kontra_word`, the last word said or null, and the `bock_factor`, 1 outside a Bock game. A game with a word
        has its list score doubled once per word said, and a Bock game's `score` is multiplied by its
        `bock_factor`. A `ramsch` entry, played at a table with Ramsch when all three passed, has no declarer: it
        names each seat's stored `name` and list `score` (the seat that lost carries the minus points, a Durchmarsch
        the plus points), whether a seat took all ten tricks and won by it (`durchmarsch`), and whether a seat with
        no trick doubled the loser's score (`jungfrau`). The seats' scores are multiplied by the entry's `bock_factor`,
        1 outside a Bock game, and by its `push_factor`, what the `pushes` (0 to 3) of the skat pushed on unseen made
        of them, 1 without pushes and at a table whose pushes do not double; a Durchmarsch's too unless the table
        scores it flat. A hand everyone passed in at a
        table without Ramsch leaves no entry. A 404 means no table has this id; a table that has ended answers an
        empty list.
        """
        response.headers["Cache-Control"] = "no-store"
        entries = await run_in_threadpool(tables.series_list, table_id)
        if entries is None:
            raise HTTPException(status_code=404, detail="table not found")
        return SeriesListAnswer(entries=[_entry_answer_of(entry) for entry in entries])

    @router.get(
        TABLES_PATH + "/{table_id}" + TABLE_LIST_SUFFIX + "/{number}",
        responses={404: {"description": "No table has this id, or the table's series has no game of this number."}},
        openapi_extra=excluded(Exclusion.GAME_SHEET),
    )
    async def read_game_sheet(table_id: str, number: int, response: Response) -> GameSheetAnswer:
        """Read one finished game of the table's current series, the same for every caller.

        It has its `number` in the list, the `seat_names` stored with the game (null for a game stored before names
        were kept), what it `count`ed (the declarer's and the opponents' card points and how it `ended`, or each
        seat's points in a Ramsch) and its `cards`, or null for a game finished before games kept their cards. The
        cards are every seat's `hands` as dealt with what became of each card (`played`, `put-away` or `unplayed`),
        the `skat` as dealt, the cards `put_away` with the seat that put each away, and the `tricks` in the order
        played, each with its cards from the lead on, its `taker_seat` and its card `points`, both null for a trick an
        early end interrupted. A Ramsch names the seats its skat counted for in `skat_takers`, and the skat as it lay
        when a Schieberamsch's take changed it in `laid_skat`, else empty. A 404 means no table has this id or its
        list has no game of this number; a table that has ended has no game.
        """

        response.headers["Cache-Control"] = "no-store"
        sheet = await run_in_threadpool(tables.game_sheet, table_id, number)
        if sheet is None:
            raise HTTPException(status_code=404, detail="game not found")
        return _sheet_answer_of(sheet)

    return router
