"""A person calls an agent to a table: the control's rows, the call, the roster of listening agents and the held answers
of whether a session's person may call.

`skat.table.member_place` decides who may call which agent; this module gathers the facts of a call (who is at the
table, which agents listen, whether the person counts as a member of the calling group), runs that decision through
`TableService` and maps its refusals onto the kit's reason tokens. Every route here is a person's act and no agent's
tool, and every one runs on the event loop, which is also where the roster and the changes' `listens_to` live.

The roster holds an agent exactly while it listens on its standing, under its token's name and owner and a key minted
here, in this process only. The held answers are one yes or no per session, kept in this process only: the display
never reads the issuer per render, and a call reads the person's groups fresh at the act.
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
from skat.table.records import TableId
from skat.web.mcp import Exclusion, excluded, token_carries_agent_facts
from skat.web.tables import TABLES_PATH, actor_of

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

    from agents.mcp_server import ResourceChanges
    from webauth.config import WebAuthConfig
    from webauth.ports import AgentFacts, SessionRecordStore
    from webauth.session_groups import SessionGroups

    from skat.table.member_place import CallOffer
    from skat.table.service import TableService
    from skat.web.presence import Presence

# The control and its call: `TABLES_PATH/{table_id}` plus the first, and plus `/agents/{key}` and the second.
TABLE_AGENTS_SUFFIX: Final = "/agents"
TABLE_AGENT_CALL_SUFFIX: Final = "/call"
# The realm's group whose members may call any owner's agent to a table.
AGENT_ADDERS_GROUP: Final = "/agent-adders"
# How long a read of the groups the issuer refused counts as "not a member" before the next control read asks again.
DISPLAY_REFUSAL_HOLD: Final = timedelta(minutes=5)
ROSTER_KEY_BYTES: Final = 16

type ListeningChanged = Callable[[Principal, str, bool], None]


class CallRefusal(StrEnum):
    """Why a call changed nothing, in the words the kit's control has a sentence for."""

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
    """One agent the person may call; `key` is opaque and the same in every state of the row, and an `inviting` row
    says in whole seconds on the server's clock how long its invitation stays open.
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
    """A call that changed nothing, as one of the control's five reasons."""

    reason: CallRefusal


@dataclass(frozen=True)
class RosterEntry:
    """A listening agent as its token states it, and the key the page holds for it."""

    key: str
    name: str
    owner: str


class AgentRoster:
    """The agents that listen on their standing right now, by account. An entry is made when the agent starts to listen,
    with the name and owner its token carries, and dropped when it has stopped. Only the front's event loop touches it.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RosterEntry] = {}

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

    def _remember(self, account_id: str, facts: AgentFacts) -> None:
        held = self._entries.get(account_id)
        if held is None or (held.name, held.owner) != (facts.name, facts.owner):
            self._entries[account_id] = RosterEntry(secrets.token_urlsafe(ROSTER_KEY_BYTES), facts.name, facts.owner)


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
        for session_id in list(self._held):
            record = self._sessions.load(session_id)
            if record is None or record.expires_at <= now:
                del self._held[session_id]


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


def _row_of(entry: RosterEntry, offer: CallOffer) -> AgentRowAnswer | None:
    if not isinstance(offer.answer, OfferState):
        return None
    return AgentRowAnswer(key=entry.key, name=entry.name, state=offer.answer, ends_in_seconds=offer.ends_in_seconds)


def _table_of(table_id: str) -> TableId:
    parsed = TableId.parse(table_id)
    if parsed is None:
        raise HTTPException(status_code=404, detail="table not found")
    return parsed


class _Calling:
    """The facts, the control and the call of the person routes, over one app's service, presence, roster and
    membership.
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

    def _facts_for(
        self, request: Request, table_id: TableId, *, viewer_is_member: bool
    ) -> list[tuple[RosterEntry, CallFacts]]:
        viewer = actor_of(request).account_id
        present = self._presence.connected(table_id.value)
        return [
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

    async def control_of(self, request: Request, table_id: TableId) -> AgentControlAnswer:
        viewer_present = actor_of(request).account_id in self._presence.connected(table_id.value)
        viewer_is_member = viewer_present and await self._membership.displayed(request)
        calls = self._facts_for(request, table_id, viewer_is_member=viewer_is_member)
        offers = await run_in_threadpool(self._tables.offers_at, table_id, [facts for _, facts in calls])
        if offers is None:
            raise HTTPException(status_code=404, detail="table not found")
        rows = [row for (entry, _), offer in zip(calls, offers, strict=True) if (row := _row_of(entry, offer))]
        shown = control_shown(viewer_present=viewer_present, viewer_is_member=viewer_is_member)
        return AgentControlAnswer(shown=shown, rows=rows)

    async def call_of(self, request: Request, table_id: TableId, key: str) -> CallRefusal | None:
        """What the call comes to. The cheap checks run first with the person counted a member, so a double tap, a full
        table or an absent owner cost no read of the issuer; the membership that grants the write is the fresh one.
        """
        chosen = [
            facts for entry, facts in self._facts_for(request, table_id, viewer_is_member=True) if entry.key == key
        ]
        offers = await run_in_threadpool(self._tables.offers_at, table_id, chosen)
        if offers is None:
            raise HTTPException(status_code=404, detail="table not found")
        if not chosen:
            return CallRefusal.AGENT_UNAVAILABLE
        answer = offers[0].answer
        if answer is OfferState.INVITING:
            return None
        if isinstance(answer, InviteRefusal):
            return REFUSAL_TOKENS[answer]
        fresh = await self._membership.fresh(request)
        if isinstance(fresh, AccessTokenRefusal):
            return CallRefusal.TRY_AGAIN
        written = await run_in_threadpool(
            self._tables.invite_agent,
            table_id,
            replace(chosen[0], viewer_is_member=fresh),
            timedelta(seconds=INVITATION_SECONDS),
        )
        if written is InviteRefusal.NO_TABLE:
            raise HTTPException(status_code=404, detail="table not found")
        return REFUSAL_TOKENS[written] if isinstance(written, InviteRefusal) else None


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
        response_model=AgentControlAnswer,
        responses={404: {"description": "No table has this id."}},
        openapi_extra=excluded(Exclusion.PERSON_ACT),
    )
    async def read_agents(table_id: str, request: Request, response: Response) -> AgentControlAnswer:
        """The viewer's control for calling agents: whether it is shown, and a row for each agent the viewer may call or
        has called and is waiting for.
        """
        response.headers["Cache-Control"] = "no-store"
        return await calling.control_of(request, _table_of(table_id))

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
        refusal = await calling.call_of(request, parsed, key)
        if refusal is not None:
            answer = CallRefusalAnswer(reason=refusal)
            return JSONResponse(answer.model_dump(mode="json"), status_code=409, headers={"Cache-Control": "no-store"})
        return await calling.control_of(request, parsed)

    return router
