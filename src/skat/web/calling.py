"""A person calls an agent to a table or sends one away: the control's rows, the call, the send-away, the roster of
listening agents and the held answers of whether a session's person may call.

`skat.table.member_place` decides who may call which agent and which agent is here; this module gathers the facts of a
call (who is at the table, which agents listen, whether the person counts as a member of the calling group), runs that
decision through `TableService` and maps its refusals onto the kit's reason tokens. Every route here is a person's act
and no agent's tool, and every one runs on the event loop, which is also where the roster and the changes'
`listens_to` live.

The roster holds an agent exactly while it listens on its standing, under its token's name and owner, and a key per
agent account, minted here at first need and kept in this process only, so a row keeps its key from the call to the
seat, whether or not the agent listens. The held answers are one yes or no per session, kept in this process only: the
display never reads the issuer per render, and a call or a send-away reads the person's groups fresh at the act.
"""

import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from agents.member import INVITATION_SECONDS, STANDING_URI
from agents.tools import Principal
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from webauth.admission import AdmissionConfig, NoAdmins, app_role
from webauth.dependencies import session_id_from_request
from webauth.oidc_login import AccessTokenRefusal

from skat.table.member_place import CallFacts, InviteRefusal, OfferState, control_shown
from skat.table.records import SendAway, TableId
from skat.table.service import CommandIdReusedError
from skat.web.mcp import Exclusion, excluded, token_carries_agent_facts
from skat.web.tables import TABLES_PATH, CommandRequest, actor_of

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

    from agents.mcp_server import ResourceChanges
    from webauth.config import WebAuthConfig
    from webauth.ports import AgentFacts, SessionRecordStore
    from webauth.session_groups import SessionGroups

    from skat.table.member_place import CallOffer
    from skat.table.service import TableService
    from skat.web.presence import Presence

# The control, its call and its send-away: `TABLES_PATH/{table_id}` plus the first, and plus `/agents/{key}` and the
# second or the third.
TABLE_AGENTS_SUFFIX: Final = "/agents"
TABLE_AGENT_CALL_SUFFIX: Final = "/call"
TABLE_AGENT_SEND_AWAY_SUFFIX: Final = "/send-away"
# The realm's group whose members may call any owner's agent to a table.
AGENT_ADDERS_GROUP: Final = "/agent-adders"
# How long a read of the groups the issuer refused counts as "not a member" before the next control read asks again.
DISPLAY_REFUSAL_HOLD: Final = timedelta(minutes=5)
ROSTER_KEY_BYTES: Final = 16
NO_TABLE_DETAIL: Final = "table not found"

type ListeningChanged = Callable[[Principal, str, bool], None]


class CallRefusal(StrEnum):
    """Why a call or a send-away changed nothing, in the words the kit's control has a sentence for."""

    NOT_ALLOWED = "not-allowed"
    OWNER_ABSENT = "owner-absent"
    PLACE_FULL = "place-full"
    AGENT_UNAVAILABLE = "agent-unavailable"
    TRY_AGAIN = "try-again"


# Many reasons are one token, so the page tells no more than the call's person may know.
REFUSAL_TOKENS: Final = {
    InviteRefusal.NOT_A_MEMBER: CallRefusal.NOT_ALLOWED,
    InviteRefusal.OWNER_ABSENT: CallRefusal.OWNER_ABSENT,
    InviteRefusal.NO_FREE_CHAIR: CallRefusal.PLACE_FULL,
    InviteRefusal.NOT_OFFERED: CallRefusal.AGENT_UNAVAILABLE,
    InviteRefusal.NOT_PRESENT: CallRefusal.TRY_AGAIN,
}


class AgentRowAnswer(BaseModel):
    """One agent the person may call or send away; `key` is opaque and the same in every state of the row, and an
    `inviting` row says in whole seconds on the server's clock how long its invitation stays open.
    """

    key: str
    name: str
    state: OfferState
    ends_in_seconds: int | None


class AgentControlAnswer(BaseModel):
    """The person's control: whether it is shown at all, and its rows."""

    shown: bool
    rows: list[AgentRowAnswer]


class CallRefusalAnswer(BaseModel):
    """A call or a send-away that changed nothing, as one of the control's five reasons."""

    reason: CallRefusal


class SendAwayRequest(CommandRequest):
    """The body of a send-away: only its retry key."""


@dataclass(frozen=True)
class RosterEntry:
    """A listening agent as its token states it, and the key the page holds for it."""

    key: str
    name: str
    owner: str


class AgentRoster:
    """The agents that listen on their standing right now, by account. An entry is made when the agent starts to listen,
    with the name and owner its token carries, and dropped when it has stopped. Every agent account the page has seen
    has one key for good. Only the front's event loop touches it.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RosterEntry] = {}
        self._keys: dict[str, str] = {}

    def listening_changed(self, principal: Principal, uri: str, listens: bool) -> None:
        """The callback `ResourceChanges` calls when the answer of `listens_to` changes; it does not block."""
        if uri != STANDING_URI:
            return
        if not listens:
            self._entries.pop(principal.sub, None)
            return
        facts = token_carries_agent_facts.get()
        if facts is not None:
            self._remember(principal.sub, facts)

    def heard(self, account_id: str, facts: AgentFacts) -> None:
        """An admitted call of the agent: a listening agent's name and owner follow its token; a silent agent gets no
        entry from it.
        """
        if account_id in self._entries:
            self._remember(account_id, facts)

    def entries(self) -> dict[str, RosterEntry]:
        return dict(self._entries)

    def key_of(self, account_id: str) -> str:
        """The agent's key, made when it is first asked for."""
        key = self._keys.get(account_id)
        if key is None:
            key = secrets.token_urlsafe(ROSTER_KEY_BYTES)
            self._keys[account_id] = key
        return key

    def _remember(self, account_id: str, facts: AgentFacts) -> None:
        self._entries[account_id] = RosterEntry(self.key_of(account_id), facts.name, facts.owner)


@dataclass(frozen=True)
class _Held:
    """A session's answer, and until when it holds: for ever while the session stands, or the refusal's hold."""

    is_member: bool
    until: float | None = None


class CallerMembership:
    """Whether a session's person counts as a member of the calling group: one held answer per session for the display,
    and a fresh read of the issuer at each call, which replaces what is held. A read the issuer refused is held as
    "no" for `DISPLAY_REFUSAL_HOLD` at the display and replaces nothing at a call.
    """

    def __init__(
        self,
        groups: SessionGroups,
        sessions: SessionRecordStore,
        web_auth: WebAuthConfig,
        admission_issuer: str,
        clock: Callable[[], float],
    ) -> None:
        self._groups = groups
        self._sessions = sessions
        self._web_auth = web_auth
        self._admission = AdmissionConfig(
            bound_issuer=admission_issuer, login_group=AGENT_ADDERS_GROUP, admin_group=NoAdmins.IN_THIS_APP
        )
        self._clock = clock
        self._held: dict[str, _Held] = {}

    async def displayed(self, request: Request) -> bool:
        """The held answer, read once for the session when none is held; also drops every answer whose session ended."""
        self._drop_ended_sessions()
        session_id = self._session_id(request)
        held = self._held.get(session_id)
        if held is not None and (held.until is None or self._clock() < held.until):
            return held.is_member
        answer = await self._groups.of_session(session_id)
        if isinstance(answer, AccessTokenRefusal):
            self._held[session_id] = _Held(False, self._clock() + DISPLAY_REFUSAL_HOLD.total_seconds())
            return False
        return self._hold(session_id, answer)

    async def fresh(self, request: Request) -> bool | AccessTokenRefusal:
        """The issuer's answer now; a membership read replaces the held answer, a refusal leaves it as it is."""
        session_id = self._session_id(request)
        answer = await self._groups.of_session(session_id)
        return answer if isinstance(answer, AccessTokenRefusal) else self._hold(session_id, answer)

    def _hold(self, session_id: str, groups: Collection[str]) -> bool:
        is_member = app_role(groups, self._admission) is not None
        self._held[session_id] = _Held(is_member)
        return is_member

    def _session_id(self, request: Request) -> str:
        session_id = session_id_from_request(request, self._web_auth)
        # The session gate refuses a request without a session before a route runs, so a missing id is a wiring fault.
        if session_id is None:  # pragma: no cover
            message = "A calling route ran without a session."
            raise RuntimeError(message)
        return session_id

    def _drop_ended_sessions(self) -> None:
        now = datetime.fromtimestamp(self._web_auth.wall_clock(), UTC)
        self._held = {
            session_id: held
            for session_id, held in self._held.items()
            if (record := self._sessions.load(session_id)) is not None and record.expires_at > now
        }


def _facts_of(
    account: str,
    entry: RosterEntry,
    *,
    viewer: str,
    present: frozenset[str],
    listens: bool,
    viewer_is_member: bool,
) -> CallFacts:
    return CallFacts(
        viewer_account=viewer,
        viewer_present=viewer in present,
        viewer_is_member=viewer_is_member,
        agent_account=account,
        agent_listens=listens,
        owner_account=entry.owner,
        owner_present=entry.owner in present,
    )


def _seated_facts_of(account: str, *, viewer: str, present: frozenset[str], viewer_is_member: bool) -> CallFacts:
    """The facts of a seated agent the roster does not hold: no token states its owner, and it does not listen."""
    return CallFacts(
        viewer_account=viewer,
        viewer_present=viewer in present,
        viewer_is_member=viewer_is_member,
        agent_account=account,
        agent_listens=False,
        owner_account=None,
        owner_present=False,
    )


@dataclass(frozen=True)
class _Offered:
    """An agent of the control with the key of its row, the facts of the person's call to it and what that comes to."""

    key: str
    name: str
    facts: CallFacts
    offer: CallOffer


def _row_of(offered: _Offered) -> AgentRowAnswer | None:
    if not isinstance(offered.offer.answer, OfferState):
        return None
    return AgentRowAnswer(
        key=offered.key, name=offered.name, state=offered.offer.answer, ends_in_seconds=offered.offer.ends_in_seconds
    )


def _table_of(table_id: str) -> TableId:
    parsed = TableId.parse(table_id)
    if parsed is None:
        raise HTTPException(status_code=404, detail=NO_TABLE_DETAIL)
    return parsed


class _Calling:
    """The facts, the control, the call and the send-away of the person routes, over one app's service, presence,
    roster and membership.
    """

    def __init__(
        self,
        tables: TableService,
        presence: Presence,
        roster: AgentRoster,
        listens: Callable[[str], bool],
        membership: CallerMembership,
    ) -> None:
        self._tables = tables
        self._presence = presence
        self._roster = roster
        self._listens = listens
        self._membership = membership

    async def _offered(self, request: Request, table_id: TableId, *, viewer_is_member: bool) -> list[_Offered]:
        """Every agent of the control, the roster's first and then the seated agents it does not hold, from one read of
        the table.
        """
        viewer = actor_of(request).account_id
        present = self._presence.connected(table_id.value)
        calls = [
            (
                entry,
                _facts_of(
                    account,
                    entry,
                    viewer=viewer,
                    present=present,
                    listens=self._listens(account),
                    viewer_is_member=viewer_is_member,
                ),
            )
            for account, entry in self._roster.entries().items()
        ]

        def seated_facts(account: str) -> CallFacts:
            return _seated_facts_of(account, viewer=viewer, present=present, viewer_is_member=viewer_is_member)

        offers = await run_in_threadpool(self._tables.offers_at, table_id, [facts for _, facts in calls], seated_facts)
        if offers is None:
            raise HTTPException(status_code=404, detail=NO_TABLE_DETAIL)
        listed = [
            _Offered(entry.key, entry.name, facts, offer)
            for (entry, facts), offer in zip(calls, offers.listed, strict=True)
        ]
        seated = [
            _Offered(self._roster.key_of(seated.account), seated.name, seated_facts(seated.account), seated.offer)
            for seated in offers.seated
        ]
        return listed + seated

    async def control_of(self, request: Request, table_id: TableId) -> AgentControlAnswer:
        viewer_present = actor_of(request).account_id in self._presence.connected(table_id.value)
        viewer_is_member = viewer_present and await self._membership.displayed(request)
        offered = await self._offered(request, table_id, viewer_is_member=viewer_is_member)
        rows = [row for agent in offered if (row := _row_of(agent))]
        shown = control_shown(viewer_present=viewer_present, viewer_is_member=viewer_is_member)
        return AgentControlAnswer(shown=shown, rows=rows)

    async def call_of(self, request: Request, table_id: TableId, key: str) -> CallRefusal | None:
        """What the call comes to. The cheap checks run first with the person counted a member, so a double tap, a full
        table or an absent owner cost no read of the issuer; the membership that grants the write is the fresh one.
        """
        chosen = next(
            (agent for agent in await self._offered(request, table_id, viewer_is_member=True) if agent.key == key), None
        )
        if chosen is None:
            return CallRefusal.AGENT_UNAVAILABLE
        answer = chosen.offer.answer
        if answer is OfferState.INVITING:
            return None
        if answer is OfferState.HERE:
            return CallRefusal.AGENT_UNAVAILABLE
        if isinstance(answer, InviteRefusal):
            return REFUSAL_TOKENS[answer]
        fresh = await self._membership.fresh(request)
        if isinstance(fresh, AccessTokenRefusal):
            return CallRefusal.TRY_AGAIN
        written = await run_in_threadpool(
            self._tables.invite_agent,
            table_id,
            replace(chosen.facts, viewer_is_member=fresh),
            timedelta(seconds=INVITATION_SECONDS),
        )
        if written is InviteRefusal.NO_TABLE:
            raise HTTPException(status_code=404, detail=NO_TABLE_DETAIL)
        return REFUSAL_TOKENS[written] if isinstance(written, InviteRefusal) else None

    async def send_away_of(self, request: Request, table_id: TableId, key: str, command_id: str) -> CallRefusal | None:
        """What the send-away comes to. The cheap checks run with the person counted a member; a person at the table
        then has the groups read fresh, and a member's act goes to the service, which decides under the table's lock
        whether the agent holds a chair and replays a command id it has seen. A retry of a tap that succeeded finds the
        agent no longer here and still answers as the first tap did.
        """
        chosen = next(
            (agent for agent in await self._offered(request, table_id, viewer_is_member=True) if agent.key == key), None
        )
        if chosen is None:
            return CallRefusal.AGENT_UNAVAILABLE
        if chosen.offer.answer is InviteRefusal.NOT_PRESENT:
            return CallRefusal.TRY_AGAIN
        fresh = await self._membership.fresh(request)
        if isinstance(fresh, AccessTokenRefusal):
            return CallRefusal.TRY_AGAIN
        if not fresh:
            return CallRefusal.NOT_ALLOWED
        command = SendAway(command_id, table_id.value, chosen.facts.agent_account)
        connected = self._presence.connected(table_id.value)
        try:
            sent = await run_in_threadpool(self._tables.send_away, actor_of(request), command, connected)
        except CommandIdReusedError:
            return CallRefusal.TRY_AGAIN
        if sent is None:
            raise HTTPException(status_code=404, detail=NO_TABLE_DETAIL)
        if sent.refusal is not None:
            return CallRefusal.AGENT_UNAVAILABLE
        self._presence.wake_table(table_id.value)
        return None


async def _answered(
    calling: _Calling, request: Request, table_id: TableId, refusal: CallRefusal | None
) -> Response | AgentControlAnswer:
    """The viewer's control after an act that changed something, or the refusal of one that changed nothing."""
    if refusal is None:
        return await calling.control_of(request, table_id)
    answer = CallRefusalAnswer(reason=refusal)
    return JSONResponse(answer.model_dump(mode="json"), status_code=409, headers={"Cache-Control": "no-store"})


def _create_acts_router(calling: _Calling) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_AGENTS_SUFFIX + "/{key}" + TABLE_AGENT_CALL_SUFFIX,
        response_model=AgentControlAnswer,
        responses={
            404: {"description": "No table has this id."},
            409: {"model": CallRefusalAnswer, "description": "The call changed nothing."},
        },
        openapi_extra=excluded(Exclusion.PERSON_ACT),
    )
    async def call_agent(
        table_id: str, key: str, request: Request, response: Response
    ) -> Response | AgentControlAnswer:
        """Call the agent of the row `key` to the table; the same call again changes nothing twice."""
        response.headers["Cache-Control"] = "no-store"
        parsed = _table_of(table_id)
        return await _answered(calling, request, parsed, await calling.call_of(request, parsed, key))

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_AGENTS_SUFFIX + "/{key}" + TABLE_AGENT_SEND_AWAY_SUFFIX,
        response_model=AgentControlAnswer,
        responses={
            404: {"description": "No table has this id."},
            409: {"model": CallRefusalAnswer, "description": "The send-away changed nothing."},
        },
        openapi_extra=excluded(Exclusion.PERSON_ACT),
    )
    async def send_agent_away(
        table_id: str, key: str, body: SendAwayRequest, request: Request, response: Response
    ) -> Response | AgentControlAnswer:
        """Ask the agent of the row `key` to leave the table: its chair opens at once, in every phase of a hand, and
        the hand waits for a sitter. The same command id again changes nothing twice.
        """
        response.headers["Cache-Control"] = "no-store"
        parsed = _table_of(table_id)
        return await _answered(
            calling, request, parsed, await calling.send_away_of(request, parsed, key, body.command_id)
        )

    return router


def create_calling_router(
    tables: TableService,
    presence: Presence,
    roster: AgentRoster,
    changes: ResourceChanges,
    issuer: str,
    membership: CallerMembership,
) -> APIRouter:
    def listens(account_id: str) -> bool:
        return changes.listens_to(Principal(iss=issuer, sub=account_id), STANDING_URI)

    calling = _Calling(tables, presence, roster, listens, membership)
    router = APIRouter()

    @router.get(
        TABLES_PATH + "/{table_id}" + TABLE_AGENTS_SUFFIX,
        responses={404: {"description": "No table has this id."}},
        openapi_extra=excluded(Exclusion.PERSON_ACT),
    )
    async def read_agents(table_id: str, request: Request, response: Response) -> AgentControlAnswer:
        """The viewer's control for calling agents: whether it is shown, and a row for each agent the viewer may call,
        has called and is waiting for, or may send away.
        """
        response.headers["Cache-Control"] = "no-store"
        return await calling.control_of(request, _table_of(table_id))

    router.include_router(_create_acts_router(calling))
    return router
