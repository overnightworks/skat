from enum import StrEnum
from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from webauth.middleware import admitted_user

from skat.engine.bidding import Awaiting
from skat.engine.cards import Card, Rank, Suit
from skat.engine.deal import Position
from skat.engine.declaration import Announcement, Stage
from skat.engine.games import GameKind
from skat.engine.value import Level  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.auction import AuctionAction  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.records import Actor, CommandRefusal, CreateTable, EndReason, SitDown, StandUp
from skat.table.rules import CHAIRS_PER_TABLE
from skat.table.service import CommandIdReusedError
from skat.web.mcp import READ_TABLE_MARK, Exclusion, excluded
from skat.web.routes import READ_METHODS, built_page_response

if TYPE_CHECKING:
    from collections.abc import Callable

    from webauth.ports import AuthenticatedUser

    from skat.engine.tricks import Sides
    from skat.table.auction import AuctionView
    from skat.table.declaring import DeclaringView
    from skat.table.game_list import ResultView
    from skat.table.playing import PlayingView
    from skat.table.service import CommandResult, TableService
    from skat.table.views import ChairHand, HandView, PassedInView, TableView
    from skat.web.page_build import PageBuild
    from skat.web.presence import Presence

TABLES_PATH: Final = "/api/tables"
TABLE_PAGE_PREFIX: Final = "/t/"
# The live view of a table: `TABLES_PATH/{table_id}` plus this.
TABLE_EVENTS_SUFFIX: Final = "/events"
# The commands that change a table: `TABLES_PATH/{table_id}` plus one of these.
TABLE_SIT_SUFFIX: Final = "/sit"
TABLE_STAND_SUFFIX: Final = "/stand"
# The browser's `crypto.randomUUID()` writes 36 characters of this alphabet.
COMMAND_ID_PATTERN: Final = r"^[A-Za-z0-9_-]{8,64}$"


class CreateTableRequest(BaseModel):
    """A client names only its retry key: the opener's account and chair come from the session."""

    model_config = ConfigDict(extra="forbid")

    command_id: Annotated[str, Field(pattern=COMMAND_ID_PATTERN)]


class SitDownRequest(CreateTableRequest):
    seat: Annotated[int, Field(strict=True, ge=1, le=CHAIRS_PER_TABLE)]


class RefusalAnswer(BaseModel):
    """A command that changed nothing; `holder_name` names who sits in a chair that was taken."""

    reason: CommandRefusal
    holder_name: str | None


class SuitToken(StrEnum):
    KREUZ = "kreuz"
    PIK = "pik"
    HERZ = "herz"
    KARO = "karo"


class RankToken(StrEnum):
    SEVEN = "seven"
    EIGHT = "eight"
    NINE = "nine"
    TEN = "ten"
    JACK = "jack"
    QUEEN = "queen"
    KING = "king"
    ACE = "ace"


class PositionToken(StrEnum):
    FOREHAND = "forehand"
    MIDDLEHAND = "middlehand"
    REARHAND = "rearhand"


class AwaitingToken(StrEnum):
    BID = "bid"
    ANSWER = "answer"
    PLAY = "play"


class StageToken(StrEnum):
    CHOOSING = "choosing"
    DISCARDING = "discarding"
    PICKED = "picked"
    DECLARED = "declared"


class GameToken(StrEnum):
    KARO = "karo"
    HERZ = "herz"
    PIK = "pik"
    KREUZ = "kreuz"
    GRAND = "grand"
    NULL = "null"


class AnnouncementToken(StrEnum):
    NONE = "none"
    SCHNEIDER = "schneider"
    SCHWARZ = "schwarz"


# The engine orders cards by number; the wire names them by word, so that order is no public contract.
SUIT_TOKENS: Final = {
    Suit.KREUZ: SuitToken.KREUZ,
    Suit.PIK: SuitToken.PIK,
    Suit.HERZ: SuitToken.HERZ,
    Suit.KARO: SuitToken.KARO,
}
RANK_TOKENS: Final = {
    Rank.SEVEN: RankToken.SEVEN,
    Rank.EIGHT: RankToken.EIGHT,
    Rank.NINE: RankToken.NINE,
    Rank.TEN: RankToken.TEN,
    Rank.JACK: RankToken.JACK,
    Rank.QUEEN: RankToken.QUEEN,
    Rank.KING: RankToken.KING,
    Rank.ACE: RankToken.ACE,
}
POSITION_TOKENS: Final = {
    Position.FOREHAND: PositionToken.FOREHAND,
    Position.MIDDLEHAND: PositionToken.MIDDLEHAND,
    Position.REARHAND: PositionToken.REARHAND,
}
AWAITING_TOKENS: Final = {
    Awaiting.BID: AwaitingToken.BID,
    Awaiting.ANSWER: AwaitingToken.ANSWER,
    Awaiting.PLAY: AwaitingToken.PLAY,
}
STAGE_TOKENS: Final = {
    Stage.CHOOSING: StageToken.CHOOSING,
    Stage.DISCARDING: StageToken.DISCARDING,
    Stage.PICKED: StageToken.PICKED,
    Stage.DECLARED: StageToken.DECLARED,
}
GAME_TOKENS: Final = {
    GameKind.KARO: GameToken.KARO,
    GameKind.HERZ: GameToken.HERZ,
    GameKind.PIK: GameToken.PIK,
    GameKind.KREUZ: GameToken.KREUZ,
    GameKind.GRAND: GameToken.GRAND,
    GameKind.NULL: GameToken.NULL,
}
ANNOUNCEMENT_TOKENS: Final = {
    Announcement.NONE: AnnouncementToken.NONE,
    Announcement.SCHNEIDER: AnnouncementToken.SCHNEIDER,
    Announcement.SCHWARZ: AnnouncementToken.SCHWARZ,
}


class CardAnswer(BaseModel):
    suit: SuitToken
    rank: RankToken


class ChairHandAnswer(BaseModel):
    position: PositionToken
    card_count: int


class AuctionWordAnswer(BaseModel):
    seat: int
    action: AuctionAction
    value: int | None


class AuctionDeclaredAnswer(BaseModel):
    seat: int
    value: int


class AuctionAnswer(BaseModel):
    turn_seat: int | None
    facing_seat: int | None
    awaiting: AwaitingToken | None
    standing: int | None
    values: list[int]
    words: list[AuctionWordAnswer]
    declared: AuctionDeclaredAnswer | None


class DeclarationAnswer(BaseModel):
    game: GameToken
    hand: bool
    ouvert: bool
    announcement: AnnouncementToken


class DeclaringAnswer(BaseModel):
    declarer_seat: int
    stage: StageToken
    declaration: DeclarationAnswer | None
    open_cards: list[CardAnswer]


class SeatedCardAnswer(BaseModel):
    seat: int
    card: CardAnswer


class LastTrickAnswer(BaseModel):
    cards: list[CardAnswer]
    leader_seat: int
    taker_seat: int


class SidesAnswer(BaseModel):
    declarer: int
    opponents: int


class PlayingAnswer(BaseModel):
    turn_seat: int
    current_trick: list[SeatedCardAnswer]
    last_trick: LastTrickAnswer | None
    tricks_won: SidesAnswer
    trick_points: SidesAnswer
    legal_cards: list[CardAnswer]


class HandAnswer(BaseModel):
    dealer_seat: int
    own_cards: list[CardAnswer]
    skat_count: int
    auction: AuctionAnswer
    declaring: DeclaringAnswer | None
    playing: PlayingAnswer | None


class ChairAnswer(BaseModel):
    seat: int
    occupant_name: str | None
    is_mine: bool
    is_away: bool
    ready: bool
    hand: ChairHandAnswer | None
    total: int | None


class PassedInAnswer(BaseModel):
    next_dealer_seat: int | None


class MatadorsAnswer(BaseModel):
    mit: bool
    count: int


class SeatGainAnswer(BaseModel):
    seat: int
    gain: int
    won: bool


class ResultAnswer(BaseModel):
    ordinal: int
    declarer_seat: int
    game: GameToken
    hand: bool
    ouvert: bool
    announcement: AnnouncementToken
    schneider: bool
    schwarz: bool
    matadors: MatadorsAnswer | None
    base_value: int | None
    levels: list[Level]
    won: bool
    doubled: bool
    overbid: bool
    bid: int
    game_value: int
    settled_value: int
    score: int
    declarer_points: int
    opponents_points: int
    gains: list[SeatGainAnswer]


class EndedAnswer(BaseModel):
    reason: EndReason
    empty_seconds: int


class TableAnswer(BaseModel):
    id: str
    version: int
    chairs: list[ChairAnswer]
    watchers: int
    hand: HandAnswer | None
    passed_in: PassedInAnswer | None
    result: ResultAnswer | None
    ended: EndedAnswer | None


class CardChoice(CardAnswer):
    """A card a client names; a field it should not send is refused."""

    model_config = ConfigDict(extra="forbid")


_SUITS: Final = {token: suit for suit, token in SUIT_TOKENS.items()}
_RANKS: Final = {token: rank for rank, token in RANK_TOKENS.items()}


def card_answer_of(card: Card) -> CardAnswer:
    return CardAnswer(suit=SUIT_TOKENS[card.suit], rank=RANK_TOKENS[card.rank])


def card_of(choice: CardChoice) -> Card:
    return Card(_SUITS[choice.suit], _RANKS[choice.rank])


def chair_hand_answer_of(hand: ChairHand | None) -> ChairHandAnswer | None:
    if hand is None:
        return None
    return ChairHandAnswer(position=POSITION_TOKENS[hand.position], card_count=hand.card_count)


def auction_answer_of(auction: AuctionView) -> AuctionAnswer:
    declared = auction.declared
    return AuctionAnswer(
        turn_seat=auction.turn_seat,
        facing_seat=auction.facing_seat,
        awaiting=None if auction.awaiting is None else AWAITING_TOKENS[auction.awaiting],
        standing=auction.standing,
        values=list(auction.values),
        words=[AuctionWordAnswer(seat=word.seat, action=word.action, value=word.value) for word in auction.words],
        declared=None if declared is None else AuctionDeclaredAnswer(seat=declared.seat, value=declared.value),
    )


def declaring_answer_of(declaring: DeclaringView | None) -> DeclaringAnswer | None:
    if declaring is None:
        return None
    declaration = declaring.declaration
    return DeclaringAnswer(
        declarer_seat=declaring.declarer_seat,
        stage=STAGE_TOKENS[declaring.stage],
        declaration=None
        if declaration is None
        else DeclarationAnswer(
            game=GAME_TOKENS[declaration.kind],
            hand=declaration.hand,
            ouvert=declaration.ouvert,
            announcement=ANNOUNCEMENT_TOKENS[declaration.announcement],
        ),
        open_cards=[card_answer_of(card) for card in declaring.open_cards],
    )


def sides_answer_of(sides: Sides) -> SidesAnswer:
    return SidesAnswer(declarer=sides.declarer, opponents=sides.opponents)


def playing_answer_of(playing: PlayingView | None) -> PlayingAnswer | None:
    if playing is None:
        return None
    last = playing.last_trick
    return PlayingAnswer(
        turn_seat=playing.turn_seat,
        current_trick=[
            SeatedCardAnswer(seat=played.seat, card=card_answer_of(played.card)) for played in playing.current_trick
        ],
        last_trick=None
        if last is None
        else LastTrickAnswer(
            cards=[card_answer_of(card) for card in last.cards],
            leader_seat=last.leader_seat,
            taker_seat=last.taker_seat,
        ),
        tricks_won=sides_answer_of(playing.tricks_won),
        trick_points=sides_answer_of(playing.trick_points),
        legal_cards=[card_answer_of(card) for card in playing.legal_cards],
    )


def hand_answer_of(hand: HandView | None) -> HandAnswer | None:
    if hand is None:
        return None
    return HandAnswer(
        dealer_seat=hand.dealer_seat,
        own_cards=[card_answer_of(card) for card in hand.own_cards],
        skat_count=hand.skat_count,
        auction=auction_answer_of(hand.auction),
        declaring=declaring_answer_of(hand.declaring),
        playing=playing_answer_of(hand.playing),
    )


def passed_in_answer_of(passed_in: PassedInView | None) -> PassedInAnswer | None:
    if passed_in is None:
        return None
    return PassedInAnswer(next_dealer_seat=passed_in.next_dealer_seat)


def result_answer_of(result: ResultView | None) -> ResultAnswer | None:
    if result is None:
        return None
    declaration, matadors = result.declaration, result.matadors
    return ResultAnswer(
        ordinal=result.ordinal,
        declarer_seat=result.declarer_seat,
        game=GAME_TOKENS[declaration.kind],
        hand=declaration.hand,
        ouvert=declaration.ouvert,
        announcement=ANNOUNCEMENT_TOKENS[declaration.announcement],
        schneider=result.schneider,
        schwarz=result.schwarz,
        matadors=None if matadors is None else MatadorsAnswer(mit=matadors.mit, count=matadors.count),
        base_value=result.base_value,
        levels=list(result.levels),
        won=result.won,
        doubled=result.doubled,
        overbid=result.overbid,
        bid=result.bid,
        game_value=result.game_value,
        settled_value=result.settled_value,
        score=result.score,
        declarer_points=result.declarer_points,
        opponents_points=result.opponents_points,
        gains=[SeatGainAnswer(seat=gain.seat, gain=gain.gain, won=gain.won) for gain in result.gains],
    )


def answer_of(view: TableView) -> TableAnswer:
    return TableAnswer(
        id=view.id,
        version=view.version,
        chairs=[
            ChairAnswer(
                seat=c.seat,
                occupant_name=c.occupant_name,
                is_mine=c.is_mine,
                is_away=c.is_away,
                ready=c.ready,
                hand=chair_hand_answer_of(c.hand),
                total=c.total,
            )
            for c in view.chairs
        ],
        watchers=view.watchers,
        hand=hand_answer_of(view.hand),
        passed_in=passed_in_answer_of(view.passed_in),
        result=result_answer_of(view.result),
        ended=None
        if view.ended is None
        else EndedAnswer(reason=view.ended.reason, empty_seconds=view.ended.empty_seconds),
    )


def actor_for(user: AuthenticatedUser) -> Actor:
    return Actor(account_id=user.id, display_name=user.username)


def actor_of(request: Request) -> Actor:
    user = admitted_user(request)
    # The gate refuses a request without a session before the route runs, so a missing user is a wiring fault.
    if user is None:  # pragma: no cover
        message = "A table route ran without an admitted user."
        raise RuntimeError(message)
    return actor_for(user)


COMMAND_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    404: {"description": "No table has this id."},
    409: {
        "model": RefusalAnswer,
        "description": "The command changed nothing, or its id came back with another request.",
    },
}


async def command_answer(
    command: Callable[[frozenset[str]], CommandResult | None], presence: Presence, table_id: str, response: Response
) -> Response | TableAnswer:
    """Run a table command off the event loop; once it committed, wake the table's streams and restart the holds."""
    response.headers["Cache-Control"] = "no-store"
    try:
        result = await run_in_threadpool(command, presence.connected(table_id))
    except CommandIdReusedError:
        raise HTTPException(status_code=409, detail="command id reused with another request") from None
    if result is None:
        raise HTTPException(status_code=404, detail="table not found")
    if result.refusal is not None:
        refusal = RefusalAnswer(reason=result.refusal, holder_name=result.holder)
        return JSONResponse(refusal.model_dump(mode="json"), status_code=409, headers={"Cache-Control": "no-store"})
    presence.wake_table(table_id)
    # A hold frees the chair when it expires, so a member with a connected stream gets none.
    away = result.away_when_hand_ended - presence.connected(table_id)
    presence.hold_chairs((table_id, account_id) for account_id in away)
    if result.seated_when_hand_ended:
        presence.restart_deal_pause(table_id)
    return answer_of(result.view)


def _create_seating_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_SIT_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=excluded(Exclusion.SEATING),
    )
    async def sit_down(
        table_id: str, body: SitDownRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        command = SitDown(command_id=body.command_id, table_id=table_id, seat=body.seat)
        answer = await command_answer(partial(tables.sit, actor_of(request), command), presence, table_id, response)
        # A sit while a result is pending marks the sitter ready, which may complete the marks.
        if isinstance(answer, TableAnswer) and answer.result is not None:
            await presence.deal_now(table_id)
        return answer

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_STAND_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=excluded(Exclusion.SEATING),
    )
    async def stand_up(
        table_id: str, body: CreateTableRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        command = StandUp(command_id=body.command_id, table_id=table_id)
        return await command_answer(partial(tables.stand, actor_of(request), command), presence, table_id, response)

    return router


def create_tables_router(tables: TableService, page_build: PageBuild, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH,
        responses={409: {"description": "The command id came back with another request."}},
        openapi_extra=excluded(Exclusion.OPENING),
    )
    async def create_table(body: CreateTableRequest, request: Request, response: Response) -> TableAnswer:
        # The answer names people, so no cache may keep it past the gate.
        response.headers["Cache-Control"] = "no-store"
        try:
            view = await run_in_threadpool(tables.create, actor_of(request), CreateTable(command_id=body.command_id))
        except CommandIdReusedError:
            raise HTTPException(status_code=409, detail="command id reused with another request") from None
        # Presence belongs to the event loop's thread, so the wait starts here and not on the worker.
        if view.ended is None:
            presence.watch_empty_table(view.id)
        return answer_of(view)

    router.include_router(_create_seating_router(tables, presence))

    @router.get(
        TABLES_PATH + "/{table_id}",
        responses={404: {"description": "No table has this id."}},
        openapi_extra=READ_TABLE_MARK,
    )
    async def read_table(table_id: str, request: Request, response: Response) -> TableAnswer:
        """Read one Skat table by its id: what the caller's own chair may see.

        The answer holds the table's version, its chairs, and the caller's own cards and the cards it may play when
        it is its turn. The ids and the version that the caller's moves need come from this answer. A 404 means no
        table has this id.
        """
        response.headers["Cache-Control"] = "no-store"
        # Presence belongs to the event loop's thread; only the store read leaves it.
        view = await run_in_threadpool(tables.view, actor_of(request), table_id, presence.connected(table_id))
        if view is None:
            raise HTTPException(status_code=404, detail="table not found")
        return answer_of(view)

    # Any id gets the page: it asks the API and shows "Tisch nicht gefunden" for an id that is no table.
    @router.api_route(
        TABLE_PAGE_PREFIX + "{table_id}", methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE)
    )
    def table_page(table_id: str) -> Response:  # noqa: ARG001 - the page reads the id from its own address
        response = built_page_response(page_build.shell)
        response.headers["Cache-Control"] = "no-cache"
        return response

    return router
