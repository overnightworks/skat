"""A table is a place an agent is a member of: its standing as a resource, the accept as the front's one tool that is
no route, and the signal that tells a listening agent its standing changed.

The standing is read from `TableService`, which derives it from the chairs an agent holds and the invitations to it;
the agent facts of the request's token decide who may read it, so a token without them, a person's, reads nothing even
for an account stored as an agent's. A listening agent whose lease has lapsed still presents its facts, so the signal
that its hold freed its chair or its table ended reaches it.

Each table in the standing as active is served as a view while the agent's lease runs: the table as `read_table`
answers it for the agent's chair, a revision and whether the table waits for the agent. The revision is the table's
version and the asks due for a seat the table waits for (`skat.table.asking`). Only the agent seated there reads it, and
the signal that a table changed tells it after the commit; once the lease has lapsed the view is neither listed nor
read, so an open stream gets no more of it until the agent calls again.

The asks follow from when the table began to wait, which `AskClock` keeps in this process only. Every touch of it runs
on the event loop's thread, in the read of the view, which also schedules the pulses that tell the awaited agent at
each deadline; the signal of a commit, which runs on a worker thread, touches neither.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
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
    PlaceRef,
    PlaceView,
    Standing,
    StandingState,
    place_ref_from_view_uri,
    place_view_uri,
)
from agents.tools import Principal, ToolDeclaration, ToolEffect, ToolOutcome
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from webauth.middleware.bearer_gate import resource_person

from skat.table.asking import ASK_AGAIN_AFTER, ASKS_AGAIN, asks_due, revision_of
from skat.table.member_place import Acceptance, MembershipState
from skat.web.mcp import token_carries_agent_facts
from skat.web.tables import actor_for, answer_of

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Generator, Iterable

    from agents.mcp_server import MemberResources
    from agents.member import PlaceWindow
    from agents.tools import JsonObject

    from skat.table.member_place import TableStanding
    from skat.table.member_view import MemberView, ViewSignal
    from skat.table.records import TableId
    from skat.table.service import TableService
    from skat.web.presence import Presence, Scheduler

TABLE_PLACE_KIND: Final = "table"

logger = structlog.get_logger()

ACCEPT_INVITATION_DECLARATION: Final = ToolDeclaration(
    name=ACCEPT_INVITATION_TOOL,
    description=(
        "Accept an invitation from your standing: you take the lowest-numbered free chair at the Skat table and play "
        "there under your name. Pass the standing's place and the invitation's id and epoch. A refusal says why: the "
        "invitation no longer stands, the person you work for is not at the table, or no chair is free."
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
    """The resources of a standing: the standing, and the view of each place it says it serves one of."""
    return (STANDING_URI, *(place_view_uri(each.place) for each in standings if each.serves_view))


@dataclass
class _Wait:
    version: int
    since: float
    pulsed: set[str] = field(default_factory=set[str])


class AskClock:
    """When each table began to wait at its latest version, in this process only, and for whom its pulses are
    scheduled. A restart starts every wait afresh at its first read. Only the event loop's thread touches it.

    Only a higher version replaces a table's entry; a version already seen keeps the earliest time, and a lower one,
    read by a transaction that began before a newer commit, changes nothing and has no wait. A table that ends while
    one of its views is being read gets no entry from that read, so an entry never outlives its table.
    """

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._waits: dict[str, _Wait] = {}
        self._reading: dict[str, int] = {}
        self._ended_while_reading: set[str] = set()

    def now(self) -> float:
        return self._clock()

    @contextmanager
    def reading(self, table_id: str) -> Generator[None]:
        """Around the read of a table's view, from before the store is read until the version is seen."""
        self._reading[table_id] = self._reading.get(table_id, 0) + 1
        try:
            yield
        finally:
            self._reading[table_id] -= 1
            if not self._reading[table_id]:
                del self._reading[table_id]
                self._ended_while_reading.discard(table_id)

    def see(self, table_id: str, version: int) -> float | None:
        """Since when the table has been at `version`, noting it first; None when the entry holds a higher one or
        the table ended while it was being read.
        """
        if table_id in self._ended_while_reading:
            return None
        wait = self._waits.get(table_id)
        if wait is None or version > wait.version:
            wait = self._waits[table_id] = _Wait(version, self._clock())
        return wait.since if wait.version == version else None

    def claim_pulses(self, table_id: str, version: int, account_id: str) -> bool:
        """True once for an account at the entry's version: the caller schedules its pulses."""
        wait = self._waits.get(table_id)
        if wait is None or wait.version != version or account_id in wait.pulsed:
            return False
        wait.pulsed.add(account_id)
        return True

    def is_current(self, table_id: str, version: int) -> bool:
        wait = self._waits.get(table_id)
        return wait is not None and wait.version == version

    def drop(self, table_id: str) -> None:
        self._waits.pop(table_id, None)
        if table_id in self._reading:
            self._ended_while_reading.add(table_id)


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
        if not token_carries_agent_facts.get():
            return ()
        return _listed(await self._standings(principal))

    async def read(  # NOSONAR(S7503) MemberResources is async
        self, principal: Principal, uri: str
    ) -> MemberStanding | PlaceWindow | PlaceView | None:
        if not token_carries_agent_facts.get():
            return None
        if uri == STANDING_URI:
            return MemberStanding(standings=await self._standings(principal))
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
            asks = self._asks_due(principal, uri, place.id, member)
        return PlaceView(
            revision=revision_of(member.view.version, asks),
            awaits_you=member.awaits_you,
            state=answer_of(member.view).model_dump(mode="json"),
        )

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


def _pulse(changes: ResourceChanges, issuer: str, accounts: frozenset[str], uri: str) -> None:
    """Tells each account that `uri` changed. It runs on a worker thread, so it hands each change to the front's event
    loop, where `ResourceChanges` lives. The change has committed, so a failure is logged by its type and never turns
    the command into an error; the listener's next listen reads today's truth.
    """
    for account in accounts:
        try:
            anyio.from_thread.run_sync(changes.changed, Principal(iss=issuer, sub=account), uri)
        except Exception as failure:
            logger.error("member_signal_failed", error=type(failure).__name__)


def standing_signal(changes: ResourceChanges, issuer: str) -> Callable[[frozenset[str]], None]:
    """The signal `TableService` tells after a commit that changed whether an agent is a member of a table."""

    def tell(accounts: frozenset[str]) -> None:
        _pulse(changes, issuer, accounts, STANDING_URI)

    return tell


def view_signal(changes: ResourceChanges, issuer: str) -> ViewSignal:
    """The signal `TableService` tells after a commit that raised a table's version: each agent seated there is told
    on the view's URI.
    """

    def tell(table_id: TableId, accounts: frozenset[str]) -> None:
        place = PlaceRef(kind=TABLE_PLACE_KIND, id=table_id.value)
        _pulse(changes, issuer, accounts, place_view_uri(place))

    return tell


@dataclass(frozen=True)
class MemberFront:
    """What the person front serves beside the routes' tools: the accept, the standing and the way it is signalled."""

    tool: PersonTool
    resources: MemberResources
    changes: ResourceChanges


def member_front(
    tables: TableService, presence: Presence, changes: ResourceChanges, scheduler: Scheduler, asks: AskClock
) -> MemberFront:
    return MemberFront(
        accept_invitation_tool(tables, presence),
        MemberStandings(tables, presence, asks, scheduler, changes),
        changes,
    )
