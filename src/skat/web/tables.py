from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Final, Literal

import structlog
from fastapi import APIRouter, HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from webauth.middleware import admitted_user

from skat.engine.cards import Card
from skat.engine.kontra import Word  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.auction import AuctionAction  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.nudging import NudgeRefusal  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.pushing import PushAction  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.reacting import Reaction, ReactionRefusal  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.records import (
    Actor,
    AuctionPlan,
    BidLimit,
    CommandRefusal,
    EndReason,
    OccupantKind,
    PlanMode,
    TableStyle,
)
from skat.table.service import CommandIdReusedError
from skat.web.declaration_tokens import ANNOUNCEMENT_TOKENS, GAME_TOKENS, AnnouncementToken, GameToken
from skat.web.languages import LANGUAGE_VARY, language_of_request
from skat.web.mcp import READ_TABLE_MARK, Exclusion, excluded
from skat.web.result_answer import RamschResultAnswer, ResultAnswer, result_answer_of
from skat.web.routes import READ_METHODS, built_page_response
from skat.web.series_answer import SeriesAnswer, StandingAnswer, series_answer_of, standing_answer_of
from skat.web.table_options import OptionsAnswer, options_answer_of
from skat.web.table_tokens import (
    AWAITING_TOKENS,
    POSITION_TOKENS,
    RANK_TOKENS,
    STAGE_TOKENS,
    SUIT_TOKENS,
    AwaitingToken,
    PositionToken,
    RankToken,
    StageToken,
    SuitToken,
)
from skat.web.turn_state_answer import TurnStateAnswer, turn_state_answer_of

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from webauth.config import WebAuthConfig
    from webauth.ports import AuthenticatedUser, SessionRecordStore

    from skat.table.auction import AuctionView, AuctionWord
    from skat.table.declaring import DeclaringView
    from skat.table.kontra import KontraView
    from skat.table.nudging import NudgeState
    from skat.table.playing import PlayingView
    from skat.table.pushing import PushingView
    from skat.table.service import TableService
    from skat.table.views import AbortedView, ChairHand, CommandResult, EndedView, HandView, PassedInView, TableView
    from skat.web.page_build import PageBuild
    from skat.web.presence import Presence
    from skat.web.reaction_log import Thrown

TABLES_PATH: Final = "/api/tables"
TABLE_PAGE_PREFIX: Final = "/t/"
# The live view of a table: `TABLES_PATH/{table_id}` plus this.
TABLE_EVENTS_SUFFIX: Final = "/events"
# The commands that change a table: `TABLES_PATH/{table_id}` plus one of these.
TABLE_SIT_SUFFIX: Final = "/sit"
TABLE_STAND_SUFFIX: Final = "/stand"
# The browser's `crypto.randomUUID()` writes 36 characters of this alphabet.
COMMAND_ID_PATTERN: Final = r"^[A-Za-z0-9_-]{8,64}$"

# The inputs every move of a table shares. A tool's schema carries these descriptions with it, so they are the one
# place the command id, the table id and the version are explained, and they stay short.
TableIdInPath = Annotated[str, Path(description="From read_table, or the link /t/{id}.")]
CommandId = Annotated[
    str,
    Field(
        pattern=COMMAND_ID_PATTERN,
        description="Names this step: resend it to retry, take a new one after a refusal.",
    ),
]
TableVersion = Annotated[int, Field(strict=True, description="From read_table or your table's view.")]


class CommandRequest(BaseModel):
    """A client names only its retry key: the account and chair come from the session."""

    model_config = ConfigDict(extra="forbid")

    command_id: CommandId


class RefusalAnswer(BaseModel):
    """A command, a nudge or a reaction that changed nothing; `holder_name` names who sits in a chair that was taken."""

    reason: CommandRefusal | NudgeRefusal | ReactionRefusal
    holder_name: str | None


TABLE_READ_REFUSED_EVENT: Final = "table_read.refused"

logger = structlog.get_logger()


class TableReadRefusal(StrEnum):
    """Why a read of a table was refused: the one set of `reason`s of its log line."""

    NO_TABLE = "no-table"


ANNOUNCEMENTS_OF_TOKEN: Final = {token: announcement for announcement, token in ANNOUNCEMENT_TOKENS.items()}


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


class PlanKind(StrEnum):
    LIMIT = "limit"
    PASS = "pass"  # noqa: S105 - the word for dropping out of the auction and no password


class AuctionPlanAnswer(BaseModel):
    """The viewer's own plan for the auction, `value` and `mode` only for a limit; no other viewer is told it."""

    kind: PlanKind
    value: int | None
    mode: PlanMode | None


class HandValueAnswer(BaseModel):
    """A suit game and the value the viewer's own ten cards reach in it without the skat."""

    game: GameToken
    value: int


class AuctionAnswer(BaseModel):
    """`words` is each chair's latest word, `steps` every word in the order it was said; `plan` and `hand_values` are
    the viewer's own.
    """

    turn_seat: int | None
    facing_seat: int | None
    awaiting: AwaitingToken | None
    standing: int | None
    values: list[int]
    words: list[AuctionWordAnswer]
    steps: list[AuctionWordAnswer]
    declared: AuctionDeclaredAnswer | None
    plan: AuctionPlanAnswer | None
    hand_values: list[HandValueAnswer]


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


class TakenAnswer(BaseModel):
    seat: int
    tricks: int


class SidesAnswer(BaseModel):
    declarer: int
    opponents: int


class OpenHandAnswer(BaseModel):
    seat: int
    cards: list[CardAnswer]


class GiveUpAnswer(BaseModel):
    """A give-up the table was asked and has not settled: who asked and which opponent already said no, the same for
    every viewer.
    """

    asking_seat: int
    declined_seat: int | None


class ShorteningAnswer(BaseModel):
    """The declarer's shortening the opponents were asked and have not settled: the level he demands, none by default,
    and the opponent who said yes so far, the same for every viewer.
    """

    asking_seat: int
    claim: AnnouncementToken
    agreed_seat: int | None


class SaidWordAnswer(BaseModel):
    seat: int
    word: Word


class KontraAnswer(BaseModel):
    """The words said in the running hand and their product, with the word the viewer's own chair may say now (null for
    a watcher and for a chair with none open). At a table whose words end with the first card, that card waits on the
    seats it names for a word or a decline, and the seats that declined stand beside them; both are empty otherwise.
    """

    said: list[SaidWordAnswer]
    factor: int
    my_word: Word | None
    my_word_answered: bool
    first_card_waits_on: list[int]
    first_card_declined: list[int]


class PlayingAnswer(BaseModel):
    """`legal_cards` is told only to the seated player on turn; `running_points` is null unless the table shows them,
    and in a Null game and a Ramsch; `shortening_refused_seat` is the opponent whose no left the declarer's cards open
    and stays beside a new request; `open_play_seat` is the opponent whose wrong open play waits for the declarer's
    answer; `kontra` is null at a table without Kontra.
    """

    turn_seat: int
    current_trick: list[SeatedCardAnswer]
    last_trick: LastTrickAnswer | None
    taken: list[TakenAnswer]
    legal_cards: list[CardAnswer]
    running_points: SidesAnswer | None
    give_up: GiveUpAnswer | None
    shortening: ShorteningAnswer | None
    shortening_refused_seat: int | None
    open_play_seat: int | None
    open_hands: list[OpenHandAnswer]
    kontra: KontraAnswer | None


class PushingMoveAnswer(BaseModel):
    seat: int
    action: PushAction


class PushingAnswer(BaseModel):
    """The stage before a Ramsch's first card; only the seat on turn that holds twelve cards is told cards, the ones it
    may put back.
    """

    turn_seat: int
    stage: StageToken
    moves: list[PushingMoveAnswer]
    factor: int
    put_back_cards: list[CardAnswer]


class HandAnswer(BaseModel):
    """`waiting_seat` is the open seat a running hand waits for and `abort` the seats that said yes to aborting it
    (null while no vote stands), the same for every viewer; `pushing` is set while the stage runs, the Ramsch's play
    has none; `pushes` and `push_factor` are how often the skat was pushed on unseen and what that multiplies the
    Ramsch's score by; `abortable` is true when a chair of the hand is open.
    """

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
    push_factor: int
    abort: list[int] | None
    abortable: bool


class NudgeAnswer(BaseModel):
    """What the viewer is shown of the nudges a chair the table waits for has had at this version: how many, whether
    the viewer's seat may nudge it (the cap is not reached; the minute is the server's to judge) and, for the nudged
    seat's own viewer only, the latest nudger's name.
    """

    nudges: int
    may_nudge: bool
    by_name: str | None


class ReactionAnswer(BaseModel):
    """A reaction thrown at the table lately: `number` counts them at the table, so a page plays each one once. A
    watcher's reaction has no seat and no name; a seat that was vacated since has no name.
    """

    number: int
    reaction: Reaction
    by_seat: int | None
    by_name: str | None


class ChairAnswer(BaseModel):
    """`total` is the person's running total: null on a free chair and, in a table's first series, until its first
    result; a later series reads 0 from its first deal. `former_holder_name` names whoever held the chair in the running
    hand and left it, while it stays open; `is_mine_to_return` is true only on the chair of the running hand that the
    viewer stood up from, open or taken since: the one chair they may sit in again; `nudge` is null on every chair the
    table does not wait for.
    """

    seat: int
    occupant_name: str | None
    occupant_kind: OccupantKind | None
    is_mine: bool
    is_away: bool
    ready: bool
    hand: ChairHandAnswer | None
    total: int | None
    former_holder_name: str | None
    is_mine_to_return: bool
    nudge: NudgeAnswer | None
    turn_state: TurnStateAnswer | None = None


class NextDealerAnswer(BaseModel):
    """Who deals next after a hand that ended with no result, passed in or aborted by a vote; named only while three
    chairs are occupied and the series goes on.
    """

    next_dealer_seat: int | None


class EmptyNoGamesAnswer(BaseModel):
    """A table nobody was at for `empty_seconds` whole seconds while no hand was dealt, which finished no game."""

    reason: Literal[EndReason.EMPTY]
    empty_seconds: int
    unplayed_days: None
    closed_by_name: None
    standings: None
    game_count: None


class EmptyWithGamesAnswer(BaseModel):
    """A table nobody was at for `empty_seconds` whole seconds, with the games its last series played and their
    standings.
    """

    reason: Literal[EndReason.EMPTY]
    empty_seconds: int
    unplayed_days: None
    closed_by_name: None
    standings: list[StandingAnswer]
    game_count: int


class UnplayedNoGamesAnswer(BaseModel):
    """A table nobody played at for `unplayed_days` days, which finished no game."""

    reason: Literal[EndReason.UNPLAYED]
    empty_seconds: None
    unplayed_days: int
    closed_by_name: None
    standings: None
    game_count: None


class UnplayedWithGamesAnswer(BaseModel):
    """A table nobody played at for `unplayed_days` days, with the games its last series played and their
    standings.
    """

    reason: Literal[EndReason.UNPLAYED]
    empty_seconds: None
    unplayed_days: int
    closed_by_name: None
    standings: list[StandingAnswer]
    game_count: int


class ClosedNoGamesAnswer(BaseModel):
    """A table that finished no game and was closed: `closed_by_name` is the opener who closed it before „Aufhören“,
    null once the days of the link's reason have passed, and for a table whose series ended by „Aufhören“ or by a
    silent seat, which is a close that names nobody.
    """

    reason: Literal[EndReason.CLOSED]
    empty_seconds: None
    unplayed_days: None
    closed_by_name: str | None
    standings: None
    game_count: None


class ClosedWithGamesAnswer(BaseModel):
    """A table closed after it finished a game: it carries the games its last series played and their standings, and
    names nobody who closed it.
    """

    reason: Literal[EndReason.CLOSED]
    empty_seconds: None
    unplayed_days: None
    closed_by_name: None
    standings: list[StandingAnswer]
    game_count: int


# Why a table ended with the one fact stored when it ended; the six shapes keep every key in this order.
EndedAnswer = (
    EmptyNoGamesAnswer
    | EmptyWithGamesAnswer
    | UnplayedNoGamesAnswer
    | UnplayedWithGamesAnswer
    | ClosedNoGamesAnswer
    | ClosedWithGamesAnswer
)
ENDED_ANSWER_MODELS: dict[tuple[EndReason, bool], type[EndedAnswer]] = {
    (EndReason.EMPTY, False): EmptyNoGamesAnswer,
    (EndReason.EMPTY, True): EmptyWithGamesAnswer,
    (EndReason.UNPLAYED, False): UnplayedNoGamesAnswer,
    (EndReason.UNPLAYED, True): UnplayedWithGamesAnswer,
    (EndReason.CLOSED, False): ClosedNoGamesAnswer,
    (EndReason.CLOSED, True): ClosedWithGamesAnswer,
}


class BockAnswer(BaseModel):
    """The Bock games still to come, the running one included, and what the running or next game's list score is
    multiplied by; the same for every viewer. A table without Bock has none.
    """

    games_left: int
    factor: int


class TableAnswer(BaseModel):
    id: str
    version: int
    chairs: list[ChairAnswer]
    watchers: int
    hand: HandAnswer | None
    passed_in: NextDealerAnswer | None
    aborted: NextDealerAnswer | None
    result: Annotated[ResultAnswer | RamschResultAnswer, Field(discriminator="kind")] | None
    series: SeriesAnswer | None
    options: OptionsAnswer | None
    style: TableStyle | None
    bock: BockAnswer | None
    ended: EndedAnswer | None
    reactions: list[ReactionAnswer]


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


def auction_plan_answer_of(plan: AuctionPlan | None) -> AuctionPlanAnswer | None:
    if plan is None:
        return None
    if isinstance(plan, BidLimit):
        return AuctionPlanAnswer(kind=PlanKind.LIMIT, value=plan.value, mode=plan.mode)
    return AuctionPlanAnswer(kind=PlanKind.PASS, value=None, mode=None)


def _word_answer_of(word: AuctionWord) -> AuctionWordAnswer:
    return AuctionWordAnswer(seat=word.seat, action=word.action, value=word.value)


def auction_answer_of(auction: AuctionView) -> AuctionAnswer:
    declared = auction.declared
    return AuctionAnswer(
        turn_seat=auction.turn_seat,
        facing_seat=auction.facing_seat,
        awaiting=None if auction.awaiting is None else AWAITING_TOKENS[auction.awaiting],
        standing=auction.standing,
        values=list(auction.values),
        words=[_word_answer_of(word) for word in auction.words],
        steps=[_word_answer_of(word) for word in auction.steps],
        declared=None if declared is None else AuctionDeclaredAnswer(seat=declared.seat, value=declared.value),
        plan=auction_plan_answer_of(auction.plan),
        hand_values=[HandValueAnswer(game=GAME_TOKENS[each.kind], value=each.value) for each in auction.hand_values],
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
        put_back_cards=[card_answer_of(card) for card in pushing.put_back_cards],
    )


def kontra_answer_of(kontra: KontraView | None) -> KontraAnswer | None:
    if kontra is None:
        return None
    return KontraAnswer(
        said=[SaidWordAnswer(seat=each.seat, word=each.word) for each in kontra.said],
        factor=kontra.factor,
        my_word=kontra.my_word,
        my_word_answered=kontra.my_word_answered,
        first_card_waits_on=list(kontra.first_card_waits_on),
        first_card_declined=list(kontra.first_card_declined),
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
        taken=[TakenAnswer(seat=each.seat, tricks=each.tricks) for each in playing.taken],
        legal_cards=[card_answer_of(card) for card in playing.legal_cards],
        running_points=None
        if playing.running_points is None
        else SidesAnswer(declarer=playing.running_points.declarer, opponents=playing.running_points.opponents),
        give_up=None
        if playing.give_up is None
        else GiveUpAnswer(asking_seat=playing.give_up.asking_seat, declined_seat=playing.give_up.declined_seat),
        shortening=None
        if playing.shortening is None
        else ShorteningAnswer(
            asking_seat=playing.shortening.asking_seat,
            claim=ANNOUNCEMENT_TOKENS[playing.shortening.claim],
            agreed_seat=playing.shortening.agreed_seat,
        ),
        shortening_refused_seat=playing.shortening_refused_seat,
        open_play_seat=playing.open_play_seat,
        open_hands=[
            OpenHandAnswer(seat=each.seat, cards=[card_answer_of(card) for card in each.cards])
            for each in playing.open_hands
        ],
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
        push_factor=hand.push_factor,
        abort=None if hand.abort is None else list(hand.abort),
        abortable=hand.abortable,
    )


def next_dealer_answer_of(ended: PassedInView | AbortedView | None) -> NextDealerAnswer | None:
    if ended is None:
        return None
    return NextDealerAnswer(next_dealer_seat=ended.next_dealer_seat)


def nudge_answer_of(view: TableView, state: NudgeState | None) -> NudgeAnswer | None:
    if state is None:
        return None
    by_name = None if state.by_seat is None else view.chairs[state.by_seat - 1].occupant_name
    return NudgeAnswer(nudges=state.nudges, may_nudge=state.may_nudge, by_name=by_name)


def ended_answer_of(ended: EndedView | None) -> EndedAnswer | None:
    if ended is None:
        return None
    standings = None if ended.standings is None else [standing_answer_of(each) for each in ended.standings]
    return ENDED_ANSWER_MODELS[ended.reason, standings is not None].model_validate(
        {
            "reason": ended.reason,
            "empty_seconds": ended.empty_seconds,
            "unplayed_days": ended.unplayed_days,
            "closed_by_name": ended.closed_by_name,
            "standings": standings,
            "game_count": ended.game_count,
        }
    )


def reaction_answer_of(view: TableView, thrown: Thrown) -> ReactionAnswer:
    seat = thrown.by_seat
    by_name = None if seat is None else view.chairs[seat - 1].occupant_name
    return ReactionAnswer(number=thrown.number, reaction=thrown.reaction, by_seat=seat, by_name=by_name)


def answer_of(view: TableView, nudges: Mapping[int, NudgeState], reactions: Sequence[Thrown] = ()) -> TableAnswer:
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
                former_holder_name=c.former_holder_name,
                is_mine_to_return=c.is_mine_to_return,
                nudge=nudge_answer_of(view, nudges.get(c.seat)),
                turn_state=turn_state_answer_of(c.turn_state),
            )
            for c in view.chairs
        ],
        watchers=view.watchers,
        hand=hand_answer_of(view.hand),
        passed_in=next_dealer_answer_of(view.passed_in),
        aborted=next_dealer_answer_of(view.aborted),
        result=result_answer_of(view.result),
        series=series_answer_of(view.series),
        options=None if view.options is None else options_answer_of(view.options),
        style=view.style,
        bock=None if view.bock is None else BockAnswer(games_left=view.bock.games_left, factor=view.bock.factor),
        ended=ended_answer_of(view.ended),
        reactions=[reaction_answer_of(view, thrown) for thrown in reactions],
    )


def actor_for(user: AuthenticatedUser) -> Actor:
    """The account behind a request: an agent goes by the name its token carries, a person by the account's."""
    if user.agent is None:
        return Actor(account_id=user.id, display_name=user.username)
    return Actor(
        account_id=user.id, display_name=user.agent.name, kind=OccupantKind.AGENT, owner_account=user.agent.owner
    )


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
    with presence.waits.reading(table_id):
        try:
            result = await run_in_threadpool(command, await presence.connected(table_id))
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
        return answer_of(result.view, presence.waits.nudges_of(result.view), presence.reactions.shown(table_id))


def _create_page_router(page_build: PageBuild, sessions: SessionRecordStore, web_auth: WebAuthConfig) -> APIRouter:
    router = APIRouter()

    # Any id gets the page: it asks the API and shows "Tisch nicht gefunden" for an id that is no table.
    @router.api_route(
        TABLE_PAGE_PREFIX + "{table_id}", methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE)
    )
    def table_page(table_id: str, request: Request) -> Response:  # noqa: ARG001 - the page reads its id from the URL
        response = built_page_response(
            page_build.shell_in(language_of_request(request, sessions=sessions, config=web_auth))
        )
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Vary"] = LANGUAGE_VARY
        return response

    return router


def create_tables_router(
    tables: TableService,
    page_build: PageBuild,
    presence: Presence,
    sessions: SessionRecordStore,
    web_auth: WebAuthConfig,
) -> APIRouter:
    router = APIRouter()

    @router.get(
        TABLES_PATH + "/{table_id}",
        responses={404: {"description": "No table has this id."}},
        openapi_extra=READ_TABLE_MARK,
    )
    async def read_table(table_id: TableIdInPath, request: Request, response: Response) -> TableAnswer:
        """Read one Skat table by its id: what the caller's own chair may see.

        The answer holds the table's version, its chairs, and the caller's own cards and the cards it may play when
        it is its turn. The ids and the version that the caller's moves need come from this answer. A table the
        caller sits at is also a resource of its standing, whose state is this same answer. A result of a declared
        game says how it ended (played-out, given-up or thrown-down) and, for a give-up or a throw-down, the seat that
        did it. `hand.pushes` counts the pushes of a Ramsch's skat and `hand.push_factor` is what they multiply the
        Ramsch's score by, 1 without a push and where the table's pushes do not double; both stay through the Ramsch's
        play. `hand.waiting_seat` is the open seat a running hand waits for, the same for every viewer, or null: while
        it is set every hand command is refused with seat-open, and no card, bid value or word is offered; the hand
        moves again once someone sits in the chair. A chair's `former_holder_name` is the name of whoever held it in
        the running hand and left it, the same for every viewer, or null; it is set only while the chair is open.
        `nudge` on a chair is set for a chair the table waits for: `nudges` is how often it was nudged at this
        version and `may_nudge` whether the caller may nudge it at all, the cap not reached; whether the minute has
        passed is judged by nudge_seat. For the chair's own occupant it also names the latest nudger. `ended` is null
        while the table lives; once it ended it says why: `reason` is `empty` (nobody was there while no hand was
        dealt; `empty_seconds` is the wait), `unplayed` (no hand was dealt or played at for `unplayed_days` days),
        or `closed`: a seat that chose „Aufhören“ at the series' end, or one that stayed silent for the minute after
        the first „Neue Serie“, ends the table as `closed` with `closed_by_name` null; `closed` with a name is an
        opener's close, which only older tables carry, and `closed_by_name` is the opener's name, which the sweep at
        the start and every hour clears once `SKAT_ENDED_TABLE_DAYS` days have passed, so it stays until that next
        sweep. A table that finished a game, of
        whichever reason, carries `game_count` and the `standings` of its last series with that series' own rules, and
        names nobody in `closed_by_name`; one that finished none carries both as null.
        A game can also end shortened or played-open, each with the seat that did it.
        A 404 means no table has this id.
        """
        response.headers["Cache-Control"] = "no-store"
        # Presence belongs to the event loop's thread; only the store read leaves it.
        with presence.waits.reading(table_id):
            view = await run_in_threadpool(tables.view, actor_of(request), table_id, await presence.connected(table_id))
            if view is None:
                logger.info(TABLE_READ_REFUSED_EVENT, reason=TableReadRefusal.NO_TABLE)
                raise HTTPException(status_code=404, detail="table not found")
            return answer_of(view, presence.waits.nudges_of(view), presence.reactions.shown(table_id))

    router.include_router(_create_page_router(page_build, sessions, web_auth))

    return router
