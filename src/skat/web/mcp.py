"""Skat's MCP front: the marked routes served as tools at /mcp for the agents of the fleet.

A route becomes a tool only by carrying `agent_tool` as its `openapi_extra`; every other route carries an exclusion
with its reason, and an undecided route stops the build. A tool calls its route in-process through the whole app, so
every middleware and every check of the route applies to it as to a browser; the actor is the account the bearer
gate admitted, never a name the tool's caller gives. The one tool that is no route is `accept_invitation`, whose
arguments are the agents library's and not a route's body; the front also serves the agent's standing as a resource.
"""

import warnings
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from agents.mcp_server import McpPersonFront, route_tools
from agents.mcp_wire import MCP_ENDPOINT_PATH
from agents.tools import Principal, ToolEffect, agent_tool, not_an_agent_tool
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
    from webauth.ports import AgentFacts, SignInTransaction

    from skat.web.member_place import MemberFront

# The realm's objects for Skat's MCP path: the scope and audience a token carries, the group whose members the gate
# admits, the group of agents' own accounts it admits from any client, and the fleet's client agents sign in with.
MCP_SCOPE: Final = "mcp-skat"
MCP_GROUP: Final = "/apps/skat/mcp"
AGENT_GROUP: Final = "/agents"
MCP_CLIENT_ID: Final = "agents"

READ_TABLE_TOOL: Final = "read_table"
READ_SERIES_LIST_TOOL: Final = "read_series_list"
READ_PAUSED_TABLES_TOOL: Final = "read_paused_tables"
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
AGREE_TO_END_SERIES_TOOL: Final = "agree_to_end_series"
REFUSE_TO_END_SERIES_TOOL: Final = "refuse_to_end_series"
START_NEW_SERIES_TOOL: Final = "start_new_series"
TAKE_SKAT_TOOL: Final = "take_skat"
PUT_BACK_CARDS_TOOL: Final = "put_back_cards"
DECLARE_GAME_TOOL: Final = "declare_game"
RAMSCH_TAKE_SKAT_TOOL: Final = "ramsch_take_skat"
RAMSCH_PUT_BACK_CARDS_TOOL: Final = "ramsch_put_back_cards"
RAMSCH_PUSH_SKAT_TOOL: Final = "ramsch_push_skat"
SAY_KONTRA_TOOL: Final = "say_kontra"
OPEN_TABLE_TOOL: Final = "open_table"
SIT_DOWN_TOOL: Final = "sit_down"
STAND_UP_TOOL: Final = "stand_up"
READ_RULE_SETS_TOOL: Final = "read_rule_sets"
SAVE_RULE_SET_TOOL: Final = "save_rule_set"


class Exclusion(StrEnum):
    """Why a route is no tool; one wording per class, read by whoever reviews what an agent reaches."""

    BROWSER_PAGE = "a page or a redirect that only the browser uses"
    READINESS_PROBE = "the edge's readiness probe, no action of an agent"
    ACCOUNT_NAME = "the page's name for its person; an agent's name is in its token"
    LIVE_STREAM = "a stream the page keeps open; an agent's live view is a resource, not a tool"
    CALL_ORIGIN = "the framed page's call origin; an agent sits in no frame"
    FINAL_DELETION = "a final deletion is not yet a tool"
    PERSON_ACT = "calling an agent is a person's act, no agent's tool"


def excluded(reason: Exclusion) -> dict[str, object]:
    """The route's `openapi_extra` when it is no tool."""
    return not_an_agent_tool(reason=reason.value)


READ_TABLE_MARK: Final = agent_tool(name=READ_TABLE_TOOL, effect=ToolEffect.READ_ONLY)
READ_SERIES_LIST_MARK: Final = agent_tool(name=READ_SERIES_LIST_TOOL, effect=ToolEffect.READ_ONLY)
READ_PAUSED_TABLES_MARK: Final = agent_tool(name=READ_PAUSED_TABLES_TOOL, effect=ToolEffect.READ_ONLY)
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
AGREE_TO_END_SERIES_MARK: Final = agent_tool(name=AGREE_TO_END_SERIES_TOOL, effect=ToolEffect.SIDE_EFFECTING)
REFUSE_TO_END_SERIES_MARK: Final = agent_tool(name=REFUSE_TO_END_SERIES_TOOL, effect=ToolEffect.SIDE_EFFECTING)
START_NEW_SERIES_MARK: Final = agent_tool(name=START_NEW_SERIES_TOOL, effect=ToolEffect.SIDE_EFFECTING)
TAKE_SKAT_MARK: Final = agent_tool(name=TAKE_SKAT_TOOL, effect=ToolEffect.SIDE_EFFECTING)
PUT_BACK_CARDS_MARK: Final = agent_tool(name=PUT_BACK_CARDS_TOOL, effect=ToolEffect.SIDE_EFFECTING)
DECLARE_GAME_MARK: Final = agent_tool(name=DECLARE_GAME_TOOL, effect=ToolEffect.SIDE_EFFECTING)
RAMSCH_TAKE_SKAT_MARK: Final = agent_tool(name=RAMSCH_TAKE_SKAT_TOOL, effect=ToolEffect.SIDE_EFFECTING)
RAMSCH_PUT_BACK_CARDS_MARK: Final = agent_tool(name=RAMSCH_PUT_BACK_CARDS_TOOL, effect=ToolEffect.SIDE_EFFECTING)
RAMSCH_PUSH_SKAT_MARK: Final = agent_tool(name=RAMSCH_PUSH_SKAT_TOOL, effect=ToolEffect.SIDE_EFFECTING)
SAY_KONTRA_MARK: Final = agent_tool(name=SAY_KONTRA_TOOL, effect=ToolEffect.SIDE_EFFECTING)
OPEN_TABLE_MARK: Final = agent_tool(name=OPEN_TABLE_TOOL, effect=ToolEffect.SIDE_EFFECTING)
SIT_DOWN_MARK: Final = agent_tool(name=SIT_DOWN_TOOL, effect=ToolEffect.SIDE_EFFECTING)
STAND_UP_MARK: Final = agent_tool(name=STAND_UP_TOOL, effect=ToolEffect.SIDE_EFFECTING)
READ_RULE_SETS_MARK: Final = agent_tool(name=READ_RULE_SETS_TOOL, effect=ToolEffect.READ_ONLY)
SAVE_RULE_SET_MARK: Final = agent_tool(name=SAVE_RULE_SET_TOOL, effect=ToolEffect.SIDE_EFFECTING)


# The agent facts the admitted call's token carries, None for a person's token; the port that lists and reads resources
# is given only the account, and a stored agent's account also holds a token without them, which is a person's.
token_carries_agent_facts: Final[ContextVar[AgentFacts | None]] = ContextVar("token_carries_agent_facts", default=None)


class _AgentHearingFront:
    """The front, after it tells the host of the agent whose call the gate admitted and hands it what its token carries.

    Every call that reaches here counts, a refusal by the front included: only the token's holder can make one. The
    routes a tool calls in-process do not pass through here, so a request is heard once. A person's token is heard by
    nobody.
    """

    def __init__(self, front: ASGIApp, agent_heard: Callable[[str, AgentFacts], None]) -> None:
        self._front = front
        self._agent_heard = agent_heard

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        person = resource_person(HTTPConnection(scope))
        if person.agent is not None:
            self._agent_heard(person.id, person.agent)
        marker = token_carries_agent_facts.set(person.agent)
        try:
            await self._front(scope, receive, send)
        finally:
            token_carries_agent_facts.reset(marker)


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
    agent_heard: Callable[[str, AgentFacts], None],
    member: MemberFront,
) -> McpAccess:
    """Serve /mcp and the resource's metadata document; call it after the last route of the schema is registered.

    The front serves only inside `running()`, which the host's lifespan enters. `agent_heard(account_id, facts)` hears
    every admitted call of an agent with the facts of its token. Beside the routes' tools the front serves the member's
    accept tool, its standing as a resource and the changes that signal it.
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

    front = McpPersonFront(
        (*tools.tools, member.tool), resolve_person=resolve_person, resources=member.resources, changes=member.changes
    )
    # No methods named, so every method reaches the front, which refuses all but POST itself.
    app.router.routes.append(Route(MCP_ENDPOINT_PATH, endpoint=_AgentHearingFront(front, agent_heard)))
    install_resource_metadata(app, resource, issuer=issuer)
    admission = admission_for(issuer)
    return McpAccess(front, BearerGate(relying_party, admission, resource=resource), resource.public_rule)
