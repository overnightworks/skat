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
from webauth.admission import AdmissionConfig, NoAdmins
from webauth.middleware.bearer_gate import (
    BearerGate,
    MarkedRoute,
    ProtectedResource,
    install_resource_metadata,
    resource_person,
)
from webauth.policies import AuthorizedParties

from skat.web.constants import LOGIN_GROUP

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.types import Scope
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
PLAY_CARD_TOOL: Final = "play_card"


class Exclusion(StrEnum):
    """Why a route is no tool; one wording per class, read by whoever reviews what an agent reaches."""

    BROWSER_PAGE = "a page or a redirect that only the browser uses"
    READINESS_PROBE = "the edge's readiness probe, no action of an agent"
    ACCOUNT_NAME = "the page's name for its person; an agent's name is in its token"
    LIVE_STREAM = "a stream the page keeps open; an agent's live view is a resource, not a tool"
    NEXT_HAND = "the next hand comes only once an agent's presence counts"
    UNION_BODY = "its body has several shapes that no tool can express as one"
    OPENING = "opening a table waits for the ruling on who may open one"
    SEATING = "an agent's chair comes by invitation"


def excluded(reason: Exclusion) -> dict[str, object]:
    """The route's `openapi_extra` when it is no tool."""
    return not_an_agent_tool(reason=reason.value)


READ_TABLE_MARK: Final = agent_tool(name=READ_TABLE_TOOL, effect=ToolEffect.READ_ONLY)
PLAY_CARD_MARK: Final = agent_tool(name=PLAY_CARD_TOOL, effect=ToolEffect.SIDE_EFFECTING)


@dataclass(frozen=True)
class McpAccess:
    """What the host installs for /mcp: the front its lifespan runs, and the gate and public rule that admit it."""

    front: McpPersonFront
    bearer_gate: BearerGate
    public_rule: PublicRule


def mount_mcp(
    app: FastAPI, relying_party: OidcRelyingParty, transaction: SignInTransaction, public_origin: str
) -> McpAccess:
    """Serve /mcp and the resource's metadata document; call it after the last route of the schema is registered.

    The front serves only inside `running()`, which the host's lifespan enters.
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
    app.router.add_route(MCP_ENDPOINT_PATH, front, include_in_schema=False)
    install_resource_metadata(app, resource, issuer=issuer)
    admission = AdmissionConfig(bound_issuer=issuer, login_group=LOGIN_GROUP, admin_group=NoAdmins.IN_THIS_APP)
    return McpAccess(front, BearerGate(relying_party, admission, resource=resource), resource.public_rule)
