"""A person calls an agent to a table or sends one away: the control's rows, the call, the send-away, the roster of
listening agents and the held answers of whether a session's person may call.

`skat.table.member_place` decides who may call which agent and which agent is here; this module gathers the facts of a
call (who is at the table, which agents listen, whether the person counts as a member of the calling group), runs that
decision through `TableService` and maps its refusals onto the kit's reason tokens. Every route here is a person's act
and no agent's tool, and every one runs on the event loop.

The roster is read from what every pod shares, at each control: an agent is listed while the place store says it
listens on its standing under the issuer, which holds it until the library's `LISTEN_ALLOWANCE_SECONDS` after its last
listen ended, and the record of its name and owner stands, which is written at each call of the agent and expires a
lease after the last. Two agents of one owner with one name are two rows. A row's key is derived from the session
secret and the agent's account, so every pod gives and accepts the same key whether or not the agent listens. The held
answers are one yes or no per session, kept in this process only: the display never reads the issuer per render, and a
call or a send-away reads the person's groups fresh at the act.
"""

import base64
import hashlib
import hmac
from dataclasses import dataclass, replace
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, Protocol

import structlog
from agents.member import INVITATION_SECONDS, STANDING_URI
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from webauth.admission import AdmissionConfig, GroupPath, NoAdmins, app_role
from webauth.dependencies import session_id_from_request
from webauth.oidc_login import AccessTokenRefusal

from skat.table.member_place import (
    CallFacts,
    CallOutcome,
    InviteRefusal,
    OfferState,
    control_shown,
    seated_call_facts,
)
from skat.table.records import SendAway, TableId
from skat.table.service import CommandIdReusedError
from skat.web.mcp import Exclusion, excluded
from skat.web.tables import TABLES_PATH, CommandRequest, actor_of

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Collection, Mapping

    from agents.tools import Principal
    from webauth.config import WebAuthConfig
    from webauth.ports import AgentFacts
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
# Domain separation of the row keys from webauth's own signatures with the same secret.
ROW_KEY_LABEL: Final = b"skat-agent-row-key\x00"
ROW_KEY_BYTES: Final = 16
NO_TABLE_DETAIL: Final = "table not found"

LISTENING_READ_FAILED_EVENT: Final = "agent_listening_read.failed"
AGENT_RECORD_WRITE_FAILED_EVENT: Final = "agent_record_write.failed"

logger = structlog.get_logger()


class CallRefusal(StrEnum):
    """Why a call or a send-away changed nothing, in the words the kit's control has a sentence for."""

    NOT_ALLOWED = "not-allowed"
    OWNER_ABSENT = "owner-absent"
    PLACE_FULL = "place-full"
    AGENT_UNAVAILABLE = "agent-unavailable"
    TRY_AGAIN = "try-again"


# Many reasons are one token, so the page tells no more than the call's person may know. Only what `offer_of` decides
# maps here; `try-again` is this module's own answer to a read of the issuer or a command id it cannot use.
REFUSAL_TOKENS: Final = {
    InviteRefusal.NOT_PRESENT: CallRefusal.NOT_ALLOWED,
    InviteRefusal.NOT_A_MEMBER: CallRefusal.NOT_ALLOWED,
    InviteRefusal.OWNER_ABSENT: CallRefusal.OWNER_ABSENT,
    InviteRefusal.NO_FREE_CHAIR: CallRefusal.PLACE_FULL,
    InviteRefusal.NOT_OFFERED: CallRefusal.AGENT_UNAVAILABLE,
}


class AgentRowAnswer(BaseModel):
    """One agent the person may call or send away; `key` is opaque and the same in every state of the row, an
    `inviting` row says in whole seconds on the server's clock how long its invitation stays open, and an `ended` row
    is the person's own call that ended without a seat, with how it ended.
    """

    key: str
    name: str
    state: OfferState | Literal["ended"]
    outcome: CallOutcome | None
    ends_in_seconds: int | None


class AgentControlAnswer(BaseModel):
    """The person's control: whether it is shown at all, whether the table has no free chair for an agent the person
    could otherwise call, and its rows.
    """

    shown: bool
    full: bool
    rows: list[AgentRowAnswer]


class CallRefusalAnswer(BaseModel):
    """A call or a send-away that changed nothing, as one of the control's five reasons."""

    reason: CallRefusal


class SendAwayRequest(CommandRequest):
    """The body of a send-away: only its retry key."""


class AgentRecords(Protocol):  # pragma: no cover - a port's method bodies are signatures; `RedisAgentRecords` runs
    """One short-lived record per agent account, which every pod writes and reads: what the agent's signed token said
    of its name and its owner. A call that fails raises, whatever the store raises.
    """

    async def write(self, account_id: str, facts: AgentFacts) -> None:
        """Keeps the facts for the account from now on, in place of any earlier record."""
        ...

    async def read(self, account_ids: Collection[str]) -> Mapping[str, AgentFacts]:
        """The record of each account that has a readable one; an account without one is left out."""
        ...


@dataclass(frozen=True)
class RosterEntry:
    """A listening agent as its record states it, and the key the page holds for it."""

    key: str
    name: str
    owner: str


class AgentRoster:
    """The agents that listen on their standing right now, by account, read from the place store and the record store
    every pod shares; nothing of it is kept in this process.
    """

    def __init__(
        self,
        listeners: Callable[[str], Awaitable[frozenset[Principal]]],
        issuer: str,
        records: AgentRecords,
        signing_key: bytes,
    ) -> None:
        self._listeners = listeners
        self._issuer = issuer
        self._records = records
        self._signing_key = signing_key

    async def heard(self, account_id: str, facts: AgentFacts) -> None:
        """An admitted call of the agent: its record follows its token. A write that fails is logged and the call goes
        on. An agent without a record stays unlisted until a write succeeds, and an earlier record stands until its
        `LEASE_SECONDS` life ends, so a changed name or owner can show stale for at most that long.
        """
        try:
            await self._records.write(account_id, facts)
        except Exception as failure:
            logger.warning(AGENT_RECORD_WRITE_FAILED_EVENT, error_type=type(failure).__name__)

    async def entries(self) -> dict[str, RosterEntry]:
        """One entry per listening agent that has a record; none while a store cannot answer."""
        try:
            listening = await self._listeners(STANDING_URI)
            accounts = sorted(principal.sub for principal in listening if principal.iss == self._issuer)
            records = await self._records.read(accounts)
        except Exception as failure:
            # An agent whose listen or record cannot be read is not offered, and the next control read asks again.
            logger.warning(LISTENING_READ_FAILED_EVENT, error_type=type(failure).__name__)
            return {}
        return {
            account: RosterEntry(self.key_of(account), facts.name, facts.owner) for account, facts in records.items()
        }

    def key_of(self, account_id: str) -> str:
        """The agent's key: the same on every pod that has the session secret, and the account's own at every state of
        its row.
        """
        digest = hmac.digest(self._signing_key, ROW_KEY_LABEL + account_id.encode(), hashlib.sha256)
        return base64.urlsafe_b64encode(digest[:ROW_KEY_BYTES]).rstrip(b"=").decode()


@dataclass(frozen=True)
class _Held:
    """A session's answer, and until when it holds on the membership clock: a read's answer for as long as a session can
    stand, a refusal's for the refusal's hold.
    """

    is_member: bool
    until: float


class CallerMembership:
    """Whether a session's person counts as a member of the calling group: one held answer per session for the display,
    and a fresh read of the issuer at each call, which replaces what is held. An answer is held for the session cap,
    the longest a session stands. A read the issuer refused is held as "no" for `DISPLAY_REFUSAL_HOLD` at the display
    and replaces nothing at a call.
    """

    def __init__(
        self,
        groups: SessionGroups,
        web_auth: WebAuthConfig,
        admission_issuer: str,
        clock: Callable[[], float],
    ) -> None:
        self._groups = groups
        self._web_auth = web_auth
        self._admission = AdmissionConfig(
            bound_issuer=admission_issuer, login_group=GroupPath(AGENT_ADDERS_GROUP), admin_group=NoAdmins.IN_THIS_APP
        )
        self._clock = clock
        self._held: dict[str, _Held] = {}

    async def displayed(self, request: Request) -> bool:
        """The held answer, read once for the session when none is held; also drops every answer held out."""
        self._drop_held_out_answers()
        session_id = self._session_id(request)
        held = self._held.get(session_id)
        if held is not None:
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
        session_cap = self._web_auth.session_lifetime.absolute_max_age_seconds
        self._held[session_id] = _Held(is_member, self._clock() + session_cap)
        return is_member

    def _session_id(self, request: Request) -> str:
        session_id = session_id_from_request(request, self._web_auth)
        # The session gate refuses a request without a session before a route runs, so a missing id is a wiring fault.
        if session_id is None:  # pragma: no cover
            message = "A calling route ran without a session."
            raise RuntimeError(message)
        return session_id

    def _drop_held_out_answers(self) -> None:
        """Drops the answers whose hold has run out. A session cannot outlive the cap its answer was held for, so no
        session is read to tell an ended one.
        """
        now = self._clock()
        self._held = {session_id: held for session_id, held in self._held.items() if now < held.until}


def _facts_of(
    account: str,
    entry: RosterEntry,
    *,
    viewer: str,
    viewer_present: bool,
    streams: frozenset[str],
    viewer_is_member: bool,
) -> CallFacts:
    return CallFacts(
        viewer_account=viewer,
        viewer_present=viewer_present,
        viewer_is_member=viewer_is_member,
        agent_account=account,
        agent_listens=True,
        owner_account=entry.owner,
        owner_present=entry.owner in streams,
    )


@dataclass(frozen=True)
class _Offered:
    """An agent of the control with the key of its row, the facts of the person's call to it and what that comes to."""

    account: str
    key: str
    name: str
    facts: CallFacts
    offer: CallOffer


def _row_of(offered: _Offered) -> AgentRowAnswer | None:
    offer = offered.offer
    if offer.outcome is not None:
        return AgentRowAnswer(
            key=offered.key, name=offered.name, state="ended", outcome=offer.outcome, ends_in_seconds=None
        )
    if not isinstance(offer.answer, OfferState):
        return None
    return AgentRowAnswer(
        key=offered.key, name=offered.name, state=offer.answer, outcome=None, ends_in_seconds=offer.ends_in_seconds
    )


def _table_of(table_id: str) -> TableId:
    parsed = TableId.parse(table_id)
    if parsed is None:
        raise HTTPException(status_code=404, detail=NO_TABLE_DETAIL)
    return parsed


@dataclass(frozen=True)
class _Calling:
    """The facts, the control, the call and the send-away of the person routes, over one app's service, presence,
    roster and membership.
    """

    tables: TableService
    presence: Presence
    roster: AgentRoster
    membership: CallerMembership

    async def _at_the_table(self, table_id: TableId) -> frozenset[str]:
        return await run_in_threadpool(
            self.tables.accounts_at_the_table, table_id, await self.presence.connected(table_id.value)
        )

    async def _offered(self, request: Request, table_id: TableId, *, viewer_is_member: bool) -> list[_Offered]:
        """Every agent of the control, the roster's first and then the seated agents it does not hold, from one read of
        the table.
        """
        viewer = actor_of(request).account_id
        streams = await self.presence.connected(table_id.value)
        viewer_present = viewer in await self._at_the_table(table_id)
        calls = [
            (
                account,
                entry,
                _facts_of(
                    account,
                    entry,
                    viewer=viewer,
                    viewer_present=viewer_present,
                    streams=streams,
                    viewer_is_member=viewer_is_member,
                ),
            )
            for account, entry in (await self.roster.entries()).items()
        ]

        def seated_facts(account: str) -> CallFacts:
            return seated_call_facts(
                account, viewer_account=viewer, viewer_present=viewer_present, viewer_is_member=viewer_is_member
            )

        offers = await run_in_threadpool(
            self.tables.offers_at, table_id, [facts for _, _, facts in calls], seated_facts
        )
        if offers is None:
            raise HTTPException(status_code=404, detail=NO_TABLE_DETAIL)
        listed = [
            _Offered(account, entry.key, entry.name, facts, offer)
            for (account, entry, facts), offer in zip(calls, offers.listed, strict=True)
        ]
        seated = [
            _Offered(
                seated.account,
                self.roster.key_of(seated.account),
                seated.name,
                seated_facts(seated.account),
                seated.offer,
            )
            for seated in offers.seated
        ]
        return listed + seated

    async def control_of(self, request: Request, table_id: TableId) -> AgentControlAnswer:
        viewer_present = actor_of(request).account_id in await self._at_the_table(table_id)
        viewer_is_member = viewer_present and await self.membership.displayed(request)
        offered = await self._offered(request, table_id, viewer_is_member=viewer_is_member)
        rows = [row for agent in offered if (row := _row_of(agent))]
        sends_agent_away = any(row.state is OfferState.HERE for row in rows)
        shown = control_shown(
            viewer_present=viewer_present, viewer_is_member=viewer_is_member, sends_agent_away=sends_agent_away
        )
        full = any(agent.offer.answer is InviteRefusal.NO_FREE_CHAIR for agent in offered)
        return AgentControlAnswer(shown=shown, full=full, rows=rows)

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
        fresh = await self.membership.fresh(request)
        if isinstance(fresh, AccessTokenRefusal):
            return CallRefusal.TRY_AGAIN
        written = await run_in_threadpool(
            self.tables.invite_agent,
            table_id,
            replace(chosen.facts, viewer_is_member=fresh),
            timedelta(seconds=INVITATION_SECONDS),
        )
        if written is InviteRefusal.NO_TABLE:
            raise HTTPException(status_code=404, detail=NO_TABLE_DETAIL)
        return REFUSAL_TOKENS[written] if isinstance(written, InviteRefusal) else None

    async def send_away_of(self, request: Request, table_id: TableId, key: str, command_id: str) -> CallRefusal | None:
        """What the send-away comes to. `offer_of` decides it as it decides the row: a `here` answer with the person
        counted a member, then the same answer with the groups read fresh, and the service decides under the table's
        lock whether the agent still holds a chair and the person may send it away. The owner its chair stores for the
        agent may, whether or not the issuer answers the read. An agent that is not here is no new act, but a command
        id the person used for it already replays its answer, as long as no other request used the id.
        """
        sendable = await self._sendable(request, table_id, key, viewer_is_member=True)
        is_member = True
        if isinstance(sendable, _Offered):
            fresh = await self.membership.fresh(request)
            is_member = fresh is True
            sendable = await self._sendable(request, table_id, key, viewer_is_member=is_member)
            if sendable is CallRefusal.NOT_ALLOWED and isinstance(fresh, AccessTokenRefusal):
                return CallRefusal.TRY_AGAIN
        if sendable is CallRefusal.AGENT_UNAVAILABLE:
            return await self._replayed_send_away(request, table_id, key, command_id)
        if not isinstance(sendable, _Offered):
            return sendable
        command = SendAway(command_id, table_id.value, sendable.account)
        connected = await self.presence.connected(table_id.value)
        try:
            sent = await run_in_threadpool(self.tables.send_away, actor_of(request), command, connected, is_member)
        except CommandIdReusedError:
            return CallRefusal.TRY_AGAIN
        if sent is None:
            raise HTTPException(status_code=404, detail=NO_TABLE_DETAIL)
        if sent.refusal is not None:
            return CallRefusal.AGENT_UNAVAILABLE
        self.presence.wake_table(table_id.value)
        return None

    async def _sendable(
        self, request: Request, table_id: TableId, key: str, *, viewer_is_member: bool
    ) -> _Offered | CallRefusal:
        """The agent of the key exactly when `offer_of` answers `here` for it; the person's own refusals keep their
        tokens and any other answer, an agent that holds no chair here, is `agent-unavailable`, never a call's reason.
        """
        chosen = next(
            (
                agent
                for agent in await self._offered(request, table_id, viewer_is_member=viewer_is_member)
                if agent.key == key
            ),
            None,
        )
        if chosen is None:
            return CallRefusal.AGENT_UNAVAILABLE
        answer = chosen.offer.answer
        if answer is OfferState.HERE:
            return chosen
        if answer is InviteRefusal.NOT_PRESENT or answer is InviteRefusal.NOT_A_MEMBER:
            return REFUSAL_TOKENS[answer]
        return CallRefusal.AGENT_UNAVAILABLE

    async def _replayed_send_away(
        self, request: Request, table_id: TableId, key: str, command_id: str
    ) -> CallRefusal | None:
        try:
            replayed = await run_in_threadpool(
                self.tables.replayed_send_away,
                actor_of(request),
                command_id,
                table_id.value,
                lambda account: self.roster.key_of(account) == key,
            )
        except CommandIdReusedError:
            return CallRefusal.TRY_AGAIN
        if replayed is None or replayed.refusal is not None:
            return CallRefusal.AGENT_UNAVAILABLE
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
    tables: TableService, presence: Presence, roster: AgentRoster, membership: CallerMembership
) -> APIRouter:
    calling = _Calling(tables, presence, roster, membership)
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
