"""A table is a place an agent is a member of: its standing as a resource, the accept as the front's one tool that is
no route, and the signal that tells a listening agent its standing changed.

The standing is read from `TableService`, which derives it from the chairs an agent holds and the invitations to it;
the lease table of `Presence` decides which accounts are agents with a running lease.
"""

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final

import anyio.from_thread
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
    Standing,
    StandingState,
)
from agents.tools import Principal, ToolDeclaration, ToolEffect, ToolOutcome
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from webauth.middleware.bearer_gate import resource_person

from skat.table.member_place import Acceptance, MembershipState
from skat.web.tables import actor_for

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

    from agents.mcp_server import MemberResources
    from agents.member import PlaceWindow
    from agents.tools import JsonObject

    from skat.table.member_place import TableStanding
    from skat.table.service import TableService
    from skat.web.presence import Presence

TABLE_PLACE_KIND: Final = "table"

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


def _standing_of(standing: TableStanding) -> Standing:
    offer = standing.invitation
    return Standing(
        place=PlaceRef(kind=TABLE_PLACE_KIND, id=standing.table_id.value),
        state=StandingState(standing.state.value),
        invitation=None if offer is None else Invitation(id=offer.id, epoch=offer.epoch, expires_at=offer.expires_at),
    )


class MemberStandings:
    """What an agent with a running lease reads: its standing at the tables, and nothing for any other account."""

    def __init__(self, tables: TableService, live_leases: Callable[[], frozenset[str]]) -> None:
        self._tables = tables
        self._live_leases = live_leases

    async def current(self, principal: Principal) -> Collection[str]:  # NOSONAR(S7503) MemberResources is async
        return (STANDING_URI,) if principal.sub in self._live_leases() else ()

    async def read(  # NOSONAR(S7503) MemberResources is async
        self, principal: Principal, uri: str
    ) -> MemberStanding | PlaceWindow | None:
        if uri != STANDING_URI or principal.sub not in self._live_leases():
            return None
        standings = await run_in_threadpool(self._tables.standings_of, principal.sub)
        return MemberStanding(standings=tuple(map(_standing_of, standings)))


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


def standing_signal(changes: ResourceChanges, issuer: str) -> Callable[[frozenset[str]], None]:
    """The signal `TableService` tells after a commit: it runs on a worker thread, so it hands each change to the
    front's event loop, where `ResourceChanges` lives.
    """

    def tell(accounts: frozenset[str]) -> None:
        for account in accounts:
            anyio.from_thread.run_sync(changes.changed, Principal(iss=issuer, sub=account), STANDING_URI)

    return tell


@dataclass(frozen=True)
class MemberFront:
    """What the person front serves beside the routes' tools: the accept, the standing and the way it is signalled."""

    tool: PersonTool
    resources: MemberResources
    changes: ResourceChanges


def member_front(tables: TableService, presence: Presence, changes: ResourceChanges) -> MemberFront:
    return MemberFront(accept_invitation_tool(tables, presence), MemberStandings(tables, presence.live_leases), changes)
