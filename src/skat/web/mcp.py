"""Skat's MCP front: the marked routes served as tools at /mcp for the agents of the fleet.

A route becomes a tool only by carrying `agent_tool` as its `openapi_extra`; every other route carries an exclusion
with its reason, and an undecided route stops the build. A tool calls its route in-process through the whole app, so
every middleware and every check of the route applies to it as to a browser; the actor is the account the bearer
gate admitted, never a name the tool's caller gives.
"""

import warnings
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from agent_runtime_client.mcp_server import McpPersonFront, route_tools
from agent_runtime_client.mcp_wire import MCP_ENDPOINT_PATH
from agent_runtime_client.tools import Principal, ToolEffect, agent_tool, not_an_agent_tool
from starlette.requests import HTTPConnection
from starlette.routing import Route
from webauth.middleware.bearer_gate import (
    BearerGate,
    MarkedRoute,
    ProtectedResource,
    install_resource_metadata,
    resource_person,
)
from webauth.policies import AuthorizedParties

from skat.web.gate import admission_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send
    from webauth.oidc import OidcRelyingParty
    from webauth.policies import PublicRule
    from webauth.ports import SignInTransaction

# The realm's objects for Skat's MCP path: the scope and audience a token carries, the group whose members the gate
# admits, the group of agents' own accounts it admits from any client, and the fleet's client agents sign in with.
MCP_SCOPE: Final = "mcp-skat"
MCP_GROUP: Final = "/apps/skat/mcp"
AGENT_GROUP: Final = "/agents"
MCP_CLIENT_ID: Final = "agents"

READ_TABLE_TOOL: Final = "read_table"
READ_SERIES_LIST_TOOL: Final = "read_series_list"
PLAY_CARD_TOOL: Final = "play_card"
# The `auction_` prefix keeps the forehand's "Spielen" apart from `play_card`.
AUCTION_BID_TOOL: Final = "auction_bid"
AUCTION_HOLD_TOOL: Final = "auction_hold"
AUCTION_PASS_TOOL: Final = "auction_pass"  # noqa: S105 - the word for dropping out of the auction and no password
AUCTION_PLAY_TOOL: Final = "auction_play"
GIVE_UP_GAME_TOOL: Final = "give_up_game"
THROW_DOWN_CARDS_TOOL: Final = "throw_down_cards"
AGREE_TO_GIVE_UP_TOOL: Final = "agree_to_give_up"
DECLINE_GIVE_UP_TOOL: Final = "decline_give_up"
CONTINUE_AFTER_RESULT_TOOL: Final = "continue_after_result"
START_NEW_SERIES_TOOL: Final = "start_new_series"
TAKE_SKAT_TOOL: Final = "take_skat"
PUT_BACK_CARDS_TOOL: Final = "put_back_cards"
DECLARE_GAME_TOOL: Final = "declare_game"
SAY_KONTRA_TOOL: Final = "say_kontra"


class Exclusion(StrEnum):
    """Why a route is no tool; one wording per class, read by whoever reviews what an agent reaches."""

    BROWSER_PAGE = "a page or a redirect that only the browser uses"
    READINESS_PROBE = "the edge's readiness probe, no action of an agent"
    ACCOUNT_NAME = "the page's name for its person; an agent's name is in its token"
    LIVE_STREAM = "a stream the page keeps open; an agent's live view is a resource, not a tool"
    OPENING = "opening a table is not yet a tool"
    SEATING = "taking a chair is not yet a tool"
    CALL_ORIGIN = "the framed page's call origin; an agent sits in no frame"


def excluded(reason: Exclusion) -> dict[str, object]:
    """The route's `openapi_extra` when it is no tool."""
    return not_an_agent_tool(reason=reason.value)


READ_TABLE_MARK: Final = agent_tool(name=READ_TABLE_TOOL, effect=ToolEffect.READ_ONLY)
READ_SERIES_LIST_MARK: Final = agent_tool(name=READ_SERIES_LIST_TOOL, effect=ToolEffect.READ_ONLY)
PLAY_CARD_MARK: Final = agent_tool(name=PLAY_CARD_TOOL, effect=ToolEffect.SIDE_EFFECTING)
AUCTION_BID_MARK: Final = agent_tool(name=AUCTION_BID_TOOL, effect=ToolEffect.SIDE_EFFECTING)
AUCTION_HOLD_MARK: Final = agent_tool(name=AUCTION_HOLD_TOOL, effect=ToolEffect.SIDE_EFFECTING)
AUCTION_PASS_MARK: Final = agent_tool(name=AUCTION_PASS_TOOL, effect=ToolEffect.SIDE_EFFECTING)
AUCTION_PLAY_MARK: Final = agent_tool(name=AUCTION_PLAY_TOOL, effect=ToolEffect.SIDE_EFFECTING)
GIVE_UP_GAME_MARK: Final = agent_tool(name=GIVE_UP_GAME_TOOL, effect=ToolEffect.SIDE_EFFECTING)
THROW_DOWN_CARDS_MARK: Final = agent_tool(name=THROW_DOWN_CARDS_TOOL, effect=ToolEffect.SIDE_EFFECTING)
AGREE_TO_GIVE_UP_MARK: Final = agent_tool(name=AGREE_TO_GIVE_UP_TOOL, effect=ToolEffect.SIDE_EFFECTING)
DECLINE_GIVE_UP_MARK: Final = agent_tool(name=DECLINE_GIVE_UP_TOOL, effect=ToolEffect.SIDE_EFFECTING)
CONTINUE_AFTER_RESULT_MARK: Final = agent_tool(name=CONTINUE_AFTER_RESULT_TOOL, effect=ToolEffect.SIDE_EFFECTING)
START_NEW_SERIES_MARK: Final = agent_tool(name=START_NEW_SERIES_TOOL, effect=ToolEffect.SIDE_EFFECTING)
TAKE_SKAT_MARK: Final = agent_tool(name=TAKE_SKAT_TOOL, effect=ToolEffect.SIDE_EFFECTING)
PUT_BACK_CARDS_MARK: Final = agent_tool(name=PUT_BACK_CARDS_TOOL, effect=ToolEffect.SIDE_EFFECTING)
DECLARE_GAME_MARK: Final = agent_tool(name=DECLARE_GAME_TOOL, effect=ToolEffect.SIDE_EFFECTING)
SAY_KONTRA_MARK: Final = agent_tool(name=SAY_KONTRA_TOOL, effect=ToolEffect.SIDE_EFFECTING)


class _LeaseRenewingFront:
    """The front, after it renews the lease of the agent whose call the gate admitted.

    Every call that reaches here counts, a refusal by the front included: only the token's holder can make one. The
    routes a tool calls in-process do not pass through here, so a request renews once. A person's token renews
    nothing.
    """

    def __init__(self, front: ASGIApp, renew_lease: Callable[[str], None]) -> None:
        self._front = front
        self._renew_lease = renew_lease

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        person = resource_person(HTTPConnection(scope))
        if person.agent is not None:
            self._renew_lease(person.id)
        await self._front(scope, receive, send)


@dataclass(frozen=True)
class McpAccess:
    """What the host installs for /mcp: the front its lifespan runs, and the gate and public rule that admit it."""

    front: McpPersonFront
    bearer_gate: BearerGate
    public_rule: PublicRule


def mount_mcp(
    app: FastAPI,
    relying_party: OidcRelyingParty,
    transaction: SignInTransaction,
    public_origin: str,
    renew_lease: Callable[[str], None],
) -> McpAccess:
    """Serve /mcp and the resource's metadata document; call it after the last route of the schema is registered.

    The front serves only inside `running()`, which the host's lifespan enters. `renew_lease(account_id)` hears every
    admitted call of an agent.
    """
    with warnings.catch_warnings():
        # A route for GET and HEAD gives both operations one id, which the tool generator never reads.
        warnings.filterwarnings("ignore", message="Duplicate Operation ID", category=UserWarning)
        document = app.openapi()
    tools = route_tools(document, app, mark_route=MarkedRoute)
    resource = ProtectedResource(
        url=f"{public_origin}{MCP_ENDPOINT_PATH}",
        scope=MCP_SCOPE,
        required_group=MCP_GROUP,
        agent_group=AGENT_GROUP,
        authorized_parties=AuthorizedParties(frozenset({MCP_CLIENT_ID})),
        transaction=transaction,
        marked_routes=tools.marks,
    )
    issuer = relying_party.issuer

    def resolve_person(scope: Scope) -> Principal:
        return Principal(iss=issuer, sub=resource_person(HTTPConnection(scope)).id)

    front = McpPersonFront(tools.tools, resolve_person=resolve_person)
    # No methods named, so every method reaches the front, which refuses all but POST itself.
    app.router.routes.append(Route(MCP_ENDPOINT_PATH, endpoint=_LeaseRenewingFront(front, renew_lease)))
    install_resource_metadata(app, resource, issuer=issuer)
    admission = admission_for(issuer)
    return McpAccess(front, BearerGate(relying_party, admission, resource=resource), resource.public_rule)
