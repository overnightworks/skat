from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Final, Literal

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
from skat.engine.kontra import Word  # noqa: TC001 - pydantic reads the field type at runtime
from skat.engine.value import Level  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.auction import AuctionAction  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.game_list import GameEnding, RamschResultView
from skat.table.pushing import PushAction  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.records import (
    Actor,
    CommandRefusal,
    EndReason,
    OccupantKind,
)
from skat.table.service import CommandIdReusedError
from skat.web.mcp import READ_TABLE_MARK, Exclusion, excluded
from skat.web.routes import READ_METHODS, built_page_response
from skat.web.table_options import OptionsAnswer, options_answer_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from webauth.ports import AuthenticatedUser

    from skat.table.auction import AuctionView
    from skat.table.declaring import DeclaringView
    from skat.table.game_list import ResultView, Standing
    from skat.table.kontra import KontraView
    from skat.table.playing import PlayingView
    from skat.table.pushing import PushingView
    from skat.table.service import CommandResult, TableService
    from skat.table.views import ChairHand, HandView, PassedInView, SeriesView, TableView
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


class CommandRequest(BaseModel):
    """A client names only its retry key: the account and chair come from the session."""

    model_config = ConfigDict(extra="forbid")

    command_id: Annotated[str, Field(pattern=COMMAND_ID_PATTERN)]


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


class GiveUpAnswer(BaseModel):
    asking_seat: int
    declined_seat: int | None


class SaidWordAnswer(BaseModel):
    seat: int
    word: Word


class KontraAnswer(BaseModel):
    said: list[SaidWordAnswer]
    factor: int
    my_word: Word | None


class PlayingAnswer(BaseModel):
    turn_seat: int
    current_trick: list[SeatedCardAnswer]
    last_trick: LastTrickAnswer | None
    legal_cards: list[CardAnswer]
    running_points: SidesAnswer | None
    give_up: GiveUpAnswer | None
    kontra: KontraAnswer | None


class PushingMoveAnswer(BaseModel):
    seat: int
    action: PushAction


class PushingAnswer(BaseModel):
    turn_seat: int
    stage: StageToken
    moves: list[PushingMoveAnswer]
    factor: int


class HandAnswer(BaseModel):
    dealer_seat: int
    own_cards: list[CardAnswer]
    skat_count: int
    auction: AuctionAnswer
    declaring: DeclaringAnswer | None
    playing: PlayingAnswer | None
    ramsch: bool
    waiting_seat: int | None
    pushing: PushingAnswer | None
    pushes: int


class ChairAnswer(BaseModel):
    seat: int
    occupant_name: str | None
    occupant_kind: OccupantKind | None
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


class KontraResultAnswer(BaseModel):
    word: Word
    factor: int


class ResultAnswer(BaseModel):
    kind: Literal["declared"]
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
    multiplier: int | None
    list_bonus: int
    announcement_missed: bool
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
    kontra: KontraResultAnswer | None
    bock_factor: int
    ending: GameEnding
    ended_by_seat: int | None


class RamschSeatAnswer(BaseModel):
    seat: int
    points: int
    score: int


class RamschResultAnswer(BaseModel):
    kind: Literal["ramsch"]
    ordinal: int
    seats: list[RamschSeatAnswer]
    durchmarsch_seat: int | None
    jungfrau: bool
    bock_factor: int
    pushes: int
    push_factor: int


class EndedAnswer(BaseModel):
    reason: EndReason
    empty_seconds: int


class StandingAnswer(BaseModel):
    display_name: str | None
    total: int
    won: int
    lost: int
    place: int


class SeriesEndProposalAnswer(BaseModel):
    proposer_seat: int
    accepter_seat: int | None


class SeriesAnswer(BaseModel):
    game_number: int
    game_count: int
    over: bool
    standings: list[StandingAnswer] | None
    end_proposal: SeriesEndProposalAnswer | None


class BockAnswer(BaseModel):
    games_left: int
    factor: int


class TableAnswer(BaseModel):
    id: str
    version: int
    chairs: list[ChairAnswer]
    watchers: int
    hand: HandAnswer | None
    passed_in: PassedInAnswer | None
    result: Annotated[ResultAnswer | RamschResultAnswer, Field(discriminator="kind")] | None
    series: SeriesAnswer | None
    options: OptionsAnswer | None
    bock: BockAnswer | None
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


def pushing_answer_of(pushing: PushingView | None) -> PushingAnswer | None:
    if pushing is None:
        return None
    return PushingAnswer(
        turn_seat=pushing.turn_seat,
        stage=STAGE_TOKENS[pushing.stage],
        moves=[PushingMoveAnswer(seat=move.seat, action=move.action) for move in pushing.moves],
        factor=pushing.factor,
    )


def kontra_answer_of(kontra: KontraView | None) -> KontraAnswer | None:
    if kontra is None:
        return None
    return KontraAnswer(
        said=[SaidWordAnswer(seat=each.seat, word=each.word) for each in kontra.said],
        factor=kontra.factor,
        my_word=kontra.my_word,
    )


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
        legal_cards=[card_answer_of(card) for card in playing.legal_cards],
        running_points=None
        if playing.running_points is None
        else SidesAnswer(declarer=playing.running_points.declarer, opponents=playing.running_points.opponents),
        give_up=None
        if playing.give_up is None
        else GiveUpAnswer(asking_seat=playing.give_up.asking_seat, declined_seat=playing.give_up.declined_seat),
        kontra=kontra_answer_of(playing.kontra),
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
        ramsch=hand.ramsch,
        waiting_seat=hand.waiting_seat,
        pushing=pushing_answer_of(hand.pushing),
        pushes=hand.pushes,
    )


def passed_in_answer_of(passed_in: PassedInView | None) -> PassedInAnswer | None:
    if passed_in is None:
        return None
    return PassedInAnswer(next_dealer_seat=passed_in.next_dealer_seat)


def standing_answer_of(standing: Standing) -> StandingAnswer:
    return StandingAnswer(
        display_name=standing.display_name,
        total=standing.total,
        won=standing.won,
        lost=standing.lost,
        place=standing.place,
    )


def series_answer_of(series: SeriesView | None) -> SeriesAnswer | None:
    if series is None:
        return None
    return SeriesAnswer(
        game_number=series.game_number,
        game_count=series.game_count,
        over=series.over,
        standings=None if series.standings is None else [standing_answer_of(each) for each in series.standings],
        end_proposal=None
        if series.end_proposal is None
        else SeriesEndProposalAnswer(
            proposer_seat=series.end_proposal.proposer, accepter_seat=series.end_proposal.accepter
        ),
    )


def result_answer_of(result: ResultView | RamschResultView | None) -> ResultAnswer | RamschResultAnswer | None:
    if result is None:
        return None
    if isinstance(result, RamschResultView):
        return RamschResultAnswer(
            kind="ramsch",
            ordinal=result.ordinal,
            seats=[RamschSeatAnswer(seat=each.seat, points=each.points, score=each.score) for each in result.seats],
            durchmarsch_seat=result.durchmarsch_seat,
            jungfrau=result.jungfrau,
            bock_factor=result.bock_factor,
            pushes=result.pushes,
            push_factor=result.push_factor,
        )
    declaration, matadors = result.declaration, result.matadors
    return ResultAnswer(
        kind="declared",
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
        multiplier=result.multiplier,
        list_bonus=result.list_bonus,
        announcement_missed=result.announcement_missed,
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
        kontra=None
        if result.kontra is None
        else KontraResultAnswer(word=result.kontra.word, factor=result.kontra.factor),
        bock_factor=result.bock_factor,
        ending=result.ending,
        ended_by_seat=result.ended_by_seat,
    )


def answer_of(view: TableView) -> TableAnswer:
    return TableAnswer(
        id=view.id,
        version=view.version,
        chairs=[
            ChairAnswer(
                seat=c.seat,
                occupant_name=c.occupant_name,
                occupant_kind=c.occupant_kind,
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
        series=series_answer_of(view.series),
        options=None if view.options is None else options_answer_of(view.options),
        bock=None if view.bock is None else BockAnswer(games_left=view.bock.games_left, factor=view.bock.factor),
        ended=None
        if view.ended is None
        else EndedAnswer(reason=view.ended.reason, empty_seconds=view.ended.empty_seconds),
    )


def actor_for(user: AuthenticatedUser) -> Actor:
    """The account behind a request: an agent goes by the name its token carries, a person by the account's."""
    if user.agent is None:
        return Actor(account_id=user.id, display_name=user.username)
    return Actor(account_id=user.id, display_name=user.agent.name, kind=OccupantKind.AGENT)


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
    """Run a table command off the event loop; once it committed, wake the table's streams and restart the pause."""
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
    if result.seated_when_hand_ended:
        presence.restart_deal_pause(table_id)
    return answer_of(result.view)


def _create_page_router(page_build: PageBuild) -> APIRouter:
    router = APIRouter()

    # Any id gets the page: it asks the API and shows "Tisch nicht gefunden" for an id that is no table.
    @router.api_route(
        TABLE_PAGE_PREFIX + "{table_id}", methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE)
    )
    def table_page(table_id: str) -> Response:  # noqa: ARG001 - the page reads the id from its own address
        response = built_page_response(page_build.shell)
        response.headers["Cache-Control"] = "no-cache"
        return response

    return router


def create_tables_router(tables: TableService, page_build: PageBuild, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.get(
        TABLES_PATH + "/{table_id}",
        responses={404: {"description": "No table has this id."}},
        openapi_extra=READ_TABLE_MARK,
    )
    async def read_table(table_id: str, request: Request, response: Response) -> TableAnswer:
        """Read one Skat table by its id: what the caller's own chair may see.

        The answer holds the table's version, its chairs, and the caller's own cards and the cards it may play when
        it is its turn. The ids and the version that the caller's moves need come from this answer. A table the
        caller sits at is also a resource of its standing, whose state is this same answer. A result of a declared
        game says how it ended (played-out, given-up or thrown-down) and, for a give-up or a throw-down, the seat that
        did it. `hand.waiting_seat` is the open seat a running hand waits for, the same for every viewer, or null: while
        it is set every hand command is refused with seat-open, and no card, bid value or word is offered; the hand
        moves again once someone sits in the chair. A 404 means no table has this id.
        """
        response.headers["Cache-Control"] = "no-store"
        # Presence belongs to the event loop's thread; only the store read leaves it.
        view = await run_in_threadpool(tables.view, actor_of(request), table_id, presence.connected(table_id))
        if view is None:
            raise HTTPException(status_code=404, detail="table not found")
        return answer_of(view)

    router.include_router(_create_page_router(page_build))

    return router
