"""A table is a place an agent is a member of: its standing as a resource, the accept as the front's one tool that is
no route, and the signal that tells a listening agent its standing changed.

The standing is read from `TableService`, which derives it from the chairs an agent holds and the invitations to it;
the agent facts of the request's token decide who may read it, so a token without them, a person's, reads nothing even
for an account stored as an agent's. A listening agent whose lease has lapsed still presents its facts, so the signal
that its hold freed its chair or its table ended reaches it.

Each table in the standing as active is served as a view while the agent's lease runs: the table as `read_table`
answers it for the agent's chair, a revision and whether the table waits for the agent. The revision is the table's
version, the asks due for a seat the table waits for (`skat.table.asking`) and the nudges that seat has had
(`skat.table.nudging`). Only the agent seated there reads it, and
the signal that a table changed tells it after the commit; once the lease has lapsed the view is neither listed nor
read, so an open stream gets no more of it until the agent calls again.

The window beside the view holds the acts of the table's latest hand (`skat.table.acts`), each told as the view
tells it: a seat as its number, a card, a game and a word by the tokens of `skat.web.tables`. The commit that adds
an act tells the window and the view; the revision of the view alone moves with the asks and the nudges.

The asks follow from when the table began to wait, which `AskClock` (`skat.web.waits`) keeps in this process only.
Every touch of it runs on the event loop's thread, in the read of the view, which also schedules the pulses that tell
the awaited agent at each deadline; the signal of a commit, which runs on a worker thread, touches neither.
"""

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final

import anyio.from_thread
import structlog
from agents.mcp_server import PersonRequest, PersonTool, ResourceChanges
from agents.member import (
    ACCEPT_INVITATION_TOOL,
    STANDING_URI,
    AcceptInvitationArguments,
    AcceptInvitationRefusal,
    AcceptInvitationRefused,
    Invitation,
    MemberStanding,
    PlaceEntry,
    PlaceRef,
    PlaceView,
    PlaceWindow,
    Standing,
    StandingState,
    place_ref_from_view_uri,
    place_ref_from_window_uri,
    place_view_uri,
    place_window_uri,
)
from agents.tools import Principal, ToolDeclaration, ToolEffect, ToolOutcome
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from webauth.middleware.bearer_gate import resource_person

from skat.engine.cards import Card
from skat.engine.declaration import Announcement, Declaration
from skat.engine.kontra import Word
from skat.table.acts import Act, ActKind
from skat.table.asking import ASK_AGAIN_AFTER, ASKS_AGAIN, asks_due, revision_of
from skat.table.game_list import RamschResultView, ResultView
from skat.table.member_place import Acceptance, MembershipState
from skat.table.nudging import own_nudges
from skat.web.declaration_tokens import ANNOUNCEMENT_TOKENS, GAME_TOKENS
from skat.web.mcp import token_carries_agent_facts
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS, actor_for, answer_of

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Collection, Iterable

    from agents.mcp_server import MemberResources
    from agents.tools import JsonObject

    from skat.table.member_place import TableStanding
    from skat.table.member_view import MemberActs, MemberView, ViewSignal
    from skat.table.moment import TableMoment
    from skat.table.records import TableId
    from skat.table.service import TableService
    from skat.web.presence import Presence, Scheduler
    from skat.web.waits import AskClock

TABLE_PLACE_KIND: Final = "table"
NOBODY_NAME: Final = "Table"

logger = structlog.get_logger()

ACCEPT_INVITATION_DECLARATION: Final = ToolDeclaration(
    name=ACCEPT_INVITATION_TOOL,
    description=(
        "Accept an invitation from your standing: you take the chair you held in the running hand, or else the "
        "lowest-numbered free chair, at the Skat table and play there under your name. Pass the standing's place and "
        "the invitation's id and epoch. A refusal says why: the invitation no longer stands, the person you work for "
        "is not at the table, or no chair is free for you, the chair you held in the running hand being taken included."
    ),
    parameters=AcceptInvitationArguments.model_json_schema(),
    effect=ToolEffect.SIDE_EFFECTING,
)


def _refused(refusal: AcceptInvitationRefusal) -> ToolOutcome:
    return ToolOutcome(AcceptInvitationRefused(refused=refusal).model_dump_json(), is_error=True)


def _standing_of(standing: TableStanding, lease_runs: bool) -> Standing:
    offer = standing.invitation
    return Standing(
        place=PlaceRef(kind=TABLE_PLACE_KIND, id=standing.table_id.value),
        state=StandingState(standing.state.value),
        invitation=None if offer is None else Invitation(id=offer.id, epoch=offer.epoch, expires_at=offer.expires_at),
        serves_view=lease_runs and standing.state is MembershipState.ACTIVE,
    )


def _listed(standings: Iterable[Standing]) -> tuple[str, ...]:
    """The resources of a standing: the standing, and the window and the view of each place it says it serves one of."""
    served = [each.place for each in standings if each.serves_view]
    return (STANDING_URI, *(place_window_uri(place) for place in served), *(place_view_uri(place) for place in served))


_VALUE_TEXTS: Final = {
    ActKind.DEAL: "deals a new hand, seat {} is the dealer",
    ActKind.BID: "bids {}",
    ActKind.HOLD: "holds {}",
}
_FIXED_TEXTS: Final = {
    ActKind.PASS: "passes",
    ActKind.TAKE_SKAT: "takes the skat",
    ActKind.PUT_BACK: "puts two cards back",
    ActKind.PUSH: "pushes the skat on unseen",
    ActKind.GIVE_UP: "gives up the game",
    ActKind.SHORTEN: "shortens the game",
    ActKind.PLAY_OPEN: "plays open",
    ActKind.THROW_DOWN: "throws the cards down",
    ActKind.PASSED_IN: "ends the hand: all passed",
    ActKind.ABORTED: "ends the hand: the seats voted to abort it",
}


def _card_text(card: Card) -> str:
    return f"{SUIT_TOKENS[card.suit].value} {RANK_TOKENS[card.rank].value}"


def _declaration_text(declaration: Declaration) -> str:
    parts = ["declares", GAME_TOKENS[declaration.kind].value]
    parts += ["hand"] if declaration.hand else []
    parts += ["ouvert"] if declaration.ouvert else []
    if declaration.announcement is not Announcement.NONE:
        parts.append(ANNOUNCEMENT_TOKENS[declaration.announcement].value)
    return " ".join(parts)


def _result_text(result: ResultView | RamschResultView) -> str:
    if isinstance(result, RamschResultView):
        scores = ", ".join(f"seat {each.seat} {each.score:+d}" for each in result.seats)
        return f"ends the Ramsch, the scores are {scores}"
    outcome = "won" if result.won else "lost"
    declared = GAME_TOKENS[result.declaration.kind].value
    return f"ends the game: seat {result.declarer_seat} {outcome} {declared} for {result.score}"


def _text_of(act: Act) -> str:
    """The act in words: by what it adds to its kind when it adds something, else by its kind alone."""
    match act.detail:
        case int():
            return _VALUE_TEXTS[act.kind].format(act.detail)
        case Card():
            return f"plays {_card_text(act.detail)}"
        case Declaration():
            return _declaration_text(act.detail)
        case Word():
            return f"says {act.detail.value}"
        case ResultView() | RamschResultView():
            return _result_text(act.detail)
        case _:
            return _FIXED_TEXTS[act.kind]


def _entry_of(act: Act, member: MemberActs) -> PlaceEntry:
    """The act as a line of the member's window: written, an act, and its own when the member's seat took it."""
    return PlaceEntry(
        seq=act.seq,
        kind=act.kind.value,
        name=NOBODY_NAME if act.seat is None else f"Seat {act.seat}",
        text=_text_of(act),
        own=act.seat == member.own_seat,
        act=True,
    )


def window_of(member: MemberActs, table_id: str) -> PlaceWindow:
    """The window of a table for the member: its acts as lines, the generation being the table."""
    return PlaceWindow(
        generation=table_id,
        starts_at=member.starts_at,
        entries=tuple(_entry_of(act, member) for act in member.acts),
    )


class MemberStandings:
    """What an agent reads: its standing at the tables and the view of each table it sits at, and nothing for a token
    without agent facts.
    """

    def __init__(
        self, tables: TableService, presence: Presence, asks: AskClock, scheduler: Scheduler, changes: ResourceChanges
    ) -> None:
        self._tables = tables
        self._presence = presence
        self._asks = asks
        self._scheduler = scheduler
        self._changes = changes

    async def current(  # NOSONAR(S7503) MemberResources is async
        self,
        principal: Principal,
    ) -> Collection[str]:
        if token_carries_agent_facts.get() is None:
            return ()
        return _listed(await self._standings(principal))

    async def read(  # NOSONAR(S7503) MemberResources is async
        self, principal: Principal, uri: str
    ) -> MemberStanding | PlaceWindow | PlaceView | None:
        if token_carries_agent_facts.get() is None:
            return None
        if uri == STANDING_URI:
            return MemberStanding(standings=await self._standings(principal))
        window_place = place_ref_from_window_uri(uri)
        if window_place is not None and window_place.kind == TABLE_PLACE_KIND:
            return await self._window(principal, window_place)
        place = place_ref_from_view_uri(uri)
        if place is None or place.kind != TABLE_PLACE_KIND:
            return None
        # Presence belongs to the event loop's thread; only the store read leaves it.
        with self._asks.reading(place.id):
            member = await run_in_threadpool(
                self._tables.member_view, principal.sub, place.id, self._presence.connected(place.id)
            )
            if member is None:
                return None
            nudges = self._asks.nudges_of(member.view)
            asks = self._asks_due(principal, uri, place.id, member)
        return PlaceView(
            revision=revision_of(member.view.version, asks + own_nudges(member.view, nudges)),
            awaits_you=member.awaits_you,
            state=answer_of(member.view, nudges).model_dump(mode="json"),
        )

    async def _window(self, principal: Principal, place: PlaceRef) -> PlaceWindow | None:
        """The window of a table the principal holds a chair at: the acts of the table's latest hand."""
        member = await run_in_threadpool(self._tables.member_acts, principal.sub, place.id)
        return None if member is None else window_of(member, place.id)

    def _asks_due(self, principal: Principal, uri: str, table_id: str, member: MemberView) -> int:
        """The asks due for the reader at the version it read, and, on the first read of a version the table waits
        for it at, the pulses for the asks still to come.
        """
        version = member.view.version
        since = self._asks.see(table_id, version)
        if since is None or not member.awaits_you:
            return 0
        if self._asks.claim_pulses(table_id, version, principal.sub):
            self._schedule_pulses(principal, uri, table_id, version, since)
        return asks_due(since, self._asks.now())

    def _schedule_pulses(self, principal: Principal, uri: str, table_id: str, version: int, since: float) -> None:
        now = self._asks.now()
        for ask in range(1, ASKS_AGAIN + 1):
            delay = since + ask * ASK_AGAIN_AFTER - now
            if delay > 0:
                self._scheduler.schedule(delay, partial(self._pulse, principal, uri, table_id, version))

    async def _pulse(
        self, principal: Principal, uri: str, table_id: str, version: int
    ) -> None:  # NOSONAR(S7503) a scheduled action is async
        """Tells the agent its view changed, unless the table has moved on since or no longer waits for the agent:
        what the store holds decides, not what was last read. A failure is logged by its type: the next listen of the
        agent reads today's truth.
        """
        if not self._asks.is_current(table_id, version):
            return
        member = await run_in_threadpool(
            self._tables.member_view, principal.sub, table_id, self._presence.connected(table_id)
        )
        if member is None or not member.awaits_you or member.view.version != version:
            return
        if not self._asks.is_current(table_id, version):
            return
        try:
            self._changes.changed(principal, uri)
        except Exception as failure:
            logger.error("member_signal_failed", error=type(failure).__name__)

    def _lease_runs(self, principal: Principal) -> bool:
        return principal.sub in self._presence.live_leases()

    async def _standings(self, principal: Principal) -> tuple[Standing, ...]:
        held = await run_in_threadpool(self._tables.standings_of, principal.sub)
        lease_runs = self._lease_runs(principal)
        return tuple(_standing_of(each, lease_runs) for each in held)


def accept_invitation_tool(tables: TableService, presence: Presence) -> PersonTool:
    """The accept as a tool of the front: the arguments are the library's, not a route's body, and the owner is read
    from the token's agent facts, never from an argument.
    """

    async def handler(request: PersonRequest, arguments: JsonObject) -> ToolOutcome:
        try:
            accepted = AcceptInvitationArguments.model_validate(arguments)
        except ValidationError:
            return _refused(AcceptInvitationRefusal.STALE_INVITATION)
        if accepted.place.kind != TABLE_PLACE_KIND:
            return _refused(AcceptInvitationRefusal.STALE_INVITATION)
        table_id = accepted.place.id
        user = resource_person(HTTPConnection(request.scope))
        acceptance = Acceptance(table_id, accepted.invitation, accepted.epoch)
        owner_account = None if user.agent is None else user.agent.owner
        result = await run_in_threadpool(
            partial(tables.accept_invitation, actor_for(user), owner_account, acceptance, presence.connected(table_id))
        )
        if result.refusal is not None:
            return _refused(AcceptInvitationRefusal(result.refusal.value))
        presence.wake_table(table_id)
        presence.chair_taken(table_id)
        if result.result_pending:
            await presence.deal_now(table_id)
        seated = Standing(place=accepted.place, state=StandingState(MembershipState.ACTIVE.value))
        return ToolOutcome(seated.model_dump_json(), is_error=False)

    return PersonTool(ACCEPT_INVITATION_DECLARATION, handler)


def _pulse(issuer: str, accounts: frozenset[str], change: Callable[[Principal], None]) -> None:
    """Hands each account's `change` to the front's event loop, where `ResourceChanges` lives, from a worker thread.
    The change has committed, so a failure is logged by its type and never turns the command into an error; the
    listener's next listen reads today's truth.
    """
    for account in accounts:
        try:
            anyio.from_thread.run_sync(change, Principal(iss=issuer, sub=account))
        except Exception as failure:
            logger.error("member_signal_failed", error=type(failure).__name__)


def _pulse_uri(changes: ResourceChanges, issuer: str, accounts: frozenset[str], uri: str) -> None:
    """Tells each account that `uri` changed."""
    _pulse(issuer, accounts, lambda principal: changes.changed(principal, uri))


def standing_signal(changes: ResourceChanges, issuer: str) -> Callable[[frozenset[str]], None]:
    """The signal `TableService` tells after a commit that changed whether an agent is a member of a table."""

    def tell(accounts: frozenset[str]) -> None:
        _pulse_uri(changes, issuer, accounts, STANDING_URI)

    return tell


def tools_signal(changes: ResourceChanges, issuer: str) -> Callable[[frozenset[str]], None]:
    """The signal `TableService` tells after a commit that changed the tools an agent is offered: it sat down, left or
    moved its seat on to another moment.
    """

    def tell(accounts: frozenset[str]) -> None:
        _pulse(issuer, accounts, changes.tools_changed)

    return tell


def nudge_signal(changes: ResourceChanges, issuer: str) -> Callable[[str, str], None]:
    """The signal of a nudge that reached an agent's seat: the agent is told at once on its view's URI. It runs on the
    event loop's thread, where `ResourceChanges` lives, and a failure is logged by its type: the agent's next read
    shows the nudge.
    """

    def tell(table_id: str, account_id: str) -> None:
        place = PlaceRef(kind=TABLE_PLACE_KIND, id=table_id)
        try:
            changes.changed(Principal(iss=issuer, sub=account_id), place_view_uri(place))
        except Exception as failure:
            logger.error("member_signal_failed", error=type(failure).__name__)

    return tell


def view_signal(changes: ResourceChanges, issuer: str) -> ViewSignal:
    """The signal `TableService` tells after a commit that raised a table's version: each agent seated there is told
    on the window's URI and on the view's, both of which the commit has made readable.
    """

    def tell(table_id: TableId, accounts: frozenset[str]) -> None:
        place = PlaceRef(kind=TABLE_PLACE_KIND, id=table_id.value)
        _pulse_uri(changes, issuer, accounts, place_window_uri(place))
        _pulse_uri(changes, issuer, accounts, place_view_uri(place))

    return tell


@dataclass(frozen=True)
class MemberFront:
    """What the person front serves beside the routes' tools: the accept, the standing and the way it is signalled."""

    tool: PersonTool
    resources: MemberResources
    changes: ResourceChanges
    moments_of: Callable[[Principal], Awaitable[frozenset[TableMoment]]]


def member_front(
    tables: TableService, presence: Presence, changes: ResourceChanges, scheduler: Scheduler, asks: AskClock
) -> MemberFront:
    async def moments_of(principal: Principal) -> frozenset[TableMoment]:
        return await run_in_threadpool(tables.moments_of, principal.sub)

    return MemberFront(
        accept_invitation_tool(tables, presence),
        MemberStandings(tables, presence, asks, scheduler, changes),
        changes,
        moments_of,
    )
