"""A table is a place an agent is a member of: its standing as a resource, the accept as the front's one tool that is
no route, and the signal that tells a listening agent its standing changed.

The standing is read from `TableService`, which derives it from the chairs an agent holds and the invitations to it;
the agent facts of the request's token decide who may read it, so a token without them, a person's, reads nothing even
for an account stored as an agent's. A listening agent whose lease has lapsed still presents its facts, so the signal
that its hold freed its chair or its table ended reaches it.

Each table in the standing as active is served as a view while the agent's lease runs: the table as `read_table`
answers it for the agent's chair, its version as the revision and whether the table waits for the agent. Only the agent
seated there reads it, and the signal that a table changed tells it after the commit; once the lease has lapsed the view
is neither listed nor read, so an open stream gets no more of it until the agent calls again.
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

from skat.table.member_place import Acceptance, MembershipState
from skat.web.mcp import token_carries_agent_facts
from skat.web.tables import actor_for, answer_of

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable

    from agents.mcp_server import MemberResources
    from agents.member import PlaceWindow
    from agents.tools import JsonObject

    from skat.table.member_place import TableStanding
    from skat.table.member_view import ViewSignal
    from skat.table.records import TableId
    from skat.table.service import TableService
    from skat.web.presence import Presence

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


class MemberStandings:
    """What an agent reads: its standing at the tables and the view of each table it sits at, and nothing for a token
    without agent facts.
    """

    def __init__(self, tables: TableService, presence: Presence) -> None:
        self._tables = tables
        self._presence = presence

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
        connected = self._presence.connected(place.id)
        member = await run_in_threadpool(self._tables.member_view, principal.sub, place.id, connected)
        if member is None:
            return None
        return PlaceView(
            revision=member.view.version,
            awaits_you=member.awaits_you,
            state=answer_of(member.view).model_dump(mode="json"),
        )

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


def member_front(tables: TableService, presence: Presence, changes: ResourceChanges) -> MemberFront:
    return MemberFront(accept_invitation_tool(tables, presence), MemberStandings(tables, presence), changes)
