"""A table is a member place: an agent is a member of it exactly while it holds a chair there or an invitation to it
is open, so the book stores the invitations, the open ones and the ended ones until their outcome was told, and each
pair's epoch, never the membership itself.
"""

import math
from dataclasses import dataclass, replace
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, Protocol, cast

from agents import calling as core
from agents.member import (
    AcceptInvitationArguments,
    AcceptInvitationRefusal,
    Invitation,
    PlaceRef,
    Standing,
    StandingState,
)

from skat.table.auction_plans import sit_with_plans
from skat.table.records import Chair, Occupant, OpaqueId, TableId, TableRecord, TurnStatement
from skat.table.rules import free_seat_for, seat_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from datetime import datetime

    from skat.table.records import Actor, NewHand
    from skat.table.transactions import TableTransactions

__all__ = [
    "ENDED_CALL_KEPT",
    "TABLE_PLACE_KIND",
    "AcceptDecision",
    "AcceptResult",
    "Acceptance",
    "BookEntry",
    "CallFacts",
    "CallOffer",
    "CallOutcome",
    "InvitationId",
    "InviteRefusal",
    "MemberBook",
    "OfferState",
    "OpenInvitation",
    "SeatedAccounts",
    "SeatedAgent",
    "SeatedOffer",
    "TableOffers",
    "agent_in_chair",
    "agents_seated_at",
    "book_after_send_away",
    "call_offer_of",
    "control_shown",
    "decide_accept",
    "decide_invite",
    "ended_by_owner_leaving",
    "forgotten_if_expired",
    "keep_turn_state",
    "may_send_away",
    "offer_of",
    "offers_at",
    "seated_accounts_of",
    "seated_agents",
    "seated_call_facts",
    "standings_among",
    "standings_of",
    "table_offers_of",
]


# How long a book row keeps an invitation that ended, so the person who called is told how the call ended; the row
# forgets its two people at the first read after.
ENDED_CALL_KEPT: Final = timedelta(seconds=30)

TABLE_PLACE_KIND: Final = "table"

# The id core is asked about when a read only shows what a call comes to: a call is never stored under it.
_DISPLAY_INVITATION_ID: Final = "display"


class InviteRefusal(StrEnum):
    """Why a person's call offers an agent nothing: the one vocabulary of a row's absence and a call's refusal."""

    NO_TABLE = "no-table"
    NOT_PRESENT = "not-present"
    NOT_A_MEMBER = "not-a-member"
    NOT_OFFERED = "not-offered"
    OWNER_ABSENT = "owner-absent"
    NO_FREE_CHAIR = "no-free-chair"


class CallOutcome(StrEnum):
    """How a call ended without a seat, in the tokens the page hands the kit: the invitation ran out unanswered, the
    accept found no free chair, or the accept found the owner away.
    """

    NO_ANSWER = "no-answer"
    BUSY = "busy"
    OWNER_ABSENT = "owner-absent"


class OfferState(StrEnum):
    """What an agent is to the person who may call it: free to call, called by that person and not yet answered, or
    seated at the table, where the person may send it away.
    """

    AVAILABLE = "available"
    INVITING = "inviting"
    HERE = "here"


# The answers of a row whose caller may tell the outcome of the last call.
_CALLABLE_AGAIN: Final = frozenset({OfferState.AVAILABLE, InviteRefusal.OWNER_ABSENT, InviteRefusal.NO_FREE_CHAIR})


class InvitationId(OpaqueId):
    """The id of an invitation."""


@dataclass(frozen=True)
class OpenInvitation:
    """An invitation as stored: its owner and inviter are the people it is bound to and go once its outcome was kept.
    It stands until `expires_at`, which an accept that ended it moves to the moment of that accept, and `ended` says
    how such an accept ended it; one that ran out has none.
    """

    id: str
    expires_at: datetime
    owner_account: str
    inviter_account: str
    ended: CallOutcome | None = None


@dataclass(frozen=True)
class BookEntry:
    """The book's row of one agent at one table: the table's epoch for it, and the invitation if one is open."""

    table_id: TableId
    agent_account: str
    epoch: int = 0
    invitation: OpenInvitation | None = None


@dataclass(frozen=True)
class CallFacts:
    """What the host gathered for one person's call to one agent: the person, whether it is at the table and counts as
    a member of the group that may call agents, and the agent with whether it listens and who it works for, if known.
    """

    viewer_account: str
    viewer_present: bool
    viewer_is_member: bool
    agent_account: str
    agent_listens: bool
    owner_account: str | None
    owner_present: bool


@dataclass(frozen=True)
class CallOffer:
    """What a call to one agent comes to now; `ends_in_seconds` is the whole seconds an open invitation still stands,
    and `outcome` how the caller's last call ended, while it is told.
    """

    answer: OfferState | InviteRefusal
    ends_in_seconds: int | None = None
    outcome: CallOutcome | None = None


@dataclass(frozen=True)
class SeatedAgent:
    """An agent that holds a chair at a table, by account and the name its chair shows."""

    account: str
    name: str


@dataclass(frozen=True)
class SeatedOffer:
    """The offer of a seated agent that no call named."""

    account: str
    name: str
    offer: CallOffer


@dataclass(frozen=True)
class TableOffers:
    """The offers of the named calls, in their order, and those of the seated agents no call named."""

    listed: tuple[CallOffer, ...]
    seated: tuple[SeatedOffer, ...]


@dataclass(frozen=True)
class Acceptance:
    """What an agent's accept names: the place's id as the agent wrote it, and the invitation's id and epoch."""

    table_id: str
    invitation_id: str
    epoch: int


@dataclass(frozen=True)
class AcceptDecision:
    """The table and the agent's book row after an accept; a refusal other than stale ends the invitation."""

    table: TableRecord
    entry: BookEntry
    refusal: AcceptInvitationRefusal | None = None


@dataclass(frozen=True)
class AcceptResult:
    """What an accept did: why it seated nobody, and whether the table shows a game's result, for which the seated
    agent counts as ready, which may complete the marks for the next deal.
    """

    refusal: AcceptInvitationRefusal | None = None
    result_pending: bool = False


class MemberBook(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def locked_book_entry(self, table_id: TableId, agent_account: str) -> BookEntry | None:
        """The agent's row at the table, locked for the transaction, or None when the book holds none."""
        ...

    def locked_book_entries_of(self, agent_account: str) -> tuple[BookEntry, ...]:
        """Every row of the agent, each locked for the transaction, in table id order."""
        ...

    def locked_book_entries_at(self, table_id: TableId) -> tuple[BookEntry, ...]:
        """Every row the book holds at the table, each locked for the transaction, in agent account order."""
        ...

    def save_book_entry(self, entry: BookEntry) -> None:
        """Write the row, adding it when the book holds none for the pair."""
        ...

    def book_accounts_at(self, table_id: TableId) -> frozenset[str]:
        """Every agent the book holds a row of at the table."""
        ...


_OUTCOMES: Final = {
    core.CallOutcome.NO_ANSWER: CallOutcome.NO_ANSWER,
    core.CallOutcome.BUSY: CallOutcome.BUSY,
    core.CallOutcome.OWNER_AWAY: CallOutcome.OWNER_ABSENT,
}
_CORE_OUTCOMES: Final = {kept: outcome for outcome, kept in _OUTCOMES.items()}

_REFUSALS: Final = {
    core.InviteRefusal.NOT_PRESENT: InviteRefusal.NOT_PRESENT,
    core.InviteRefusal.NOT_A_MEMBER: InviteRefusal.NOT_A_MEMBER,
    core.InviteRefusal.ALREADY_THERE: InviteRefusal.NOT_OFFERED,
    core.InviteRefusal.NOT_LISTENING: InviteRefusal.NOT_OFFERED,
    core.InviteRefusal.INVITED_BY_ANOTHER: InviteRefusal.NOT_OFFERED,
    core.InviteRefusal.OWNER_ABSENT: InviteRefusal.OWNER_ABSENT,
    core.InviteRefusal.OWNER_AWAY: InviteRefusal.OWNER_ABSENT,
    core.InviteRefusal.OWNER_ELSEWHERE: InviteRefusal.OWNER_ABSENT,
    core.InviteRefusal.NO_FREE_SEAT: InviteRefusal.NO_FREE_CHAIR,
}


def _core_entry(entry: BookEntry) -> core.BookEntry:
    """The row as core reads it. An invitation that ended with an outcome is a kept call, not an invitation: core must
    not read it as one that ran out.
    """
    stored = entry.invitation
    if stored is None or stored.ended is not None:
        return core.BookEntry(epoch=entry.epoch)
    invitation = core.OpenInvitation(
        id=stored.id,
        expires_at=stored.expires_at,
        owner=stored.owner_account,
        bound_to=entry.table_id.value,
        inviter=stored.inviter_account,
    )
    return core.BookEntry(epoch=entry.epoch, invitation=invitation)


def _row_of(table_id: TableId, agent_account: str, entry: core.BookEntry) -> BookEntry:
    invitation = entry.invitation
    stored = (
        None
        if invitation is None
        else OpenInvitation(invitation.id, invitation.expires_at, invitation.owner, invitation.inviter)
    )
    return BookEntry(table_id, agent_account, entry.epoch, stored)


def _kept_row(row: BookEntry, ended_invitation: core.OpenInvitation, ended: core.Ended) -> BookEntry:
    """The row that keeps the call `ended` closed, for its caller to be told how it ended until `ENDED_CALL_KEPT`
    has passed.
    """
    kept = OpenInvitation(
        ended_invitation.id, ended.at, ended_invitation.owner, ended.inviter, _OUTCOMES[ended.outcome]
    )
    return BookEntry(row.table_id, row.agent_account, ended.entry.epoch, kept)


def ended_by_owner_leaving(entries: Iterable[BookEntry], owner_account: str, now: datetime) -> tuple[BookEntry, ...]:
    """The entries whose open invitation is bound to the owner, each with that invitation ended as of now with the
    outcome owner away, to keep for its caller to be told how it ended; the others are left out.
    """
    ended: list[BookEntry] = []
    for entry in entries:
        read = _core_entry(entry)
        left = core.owner_left(read, now=now)
        if left is not None and read.invitation is not None and read.invitation.owner == owner_account:
            ended.append(_kept_row(entry, read.invitation, left))
    return tuple(ended)


def _ended_call(entry: BookEntry, now: datetime) -> core.Ended | None:
    """The call the entry keeps as ended: one an accept or the owner's leaving closed, or one that ran out."""
    stored = entry.invitation
    if stored is None or stored.ended is None:
        return core.expired(_core_entry(entry), now=now)
    return core.Ended(
        entry=core.BookEntry(epoch=entry.epoch),
        inviter=stored.inviter_account,
        outcome=_CORE_OUTCOMES[stored.ended],
        at=stored.expires_at,
    )


def forgotten_if_expired(entry: BookEntry, now: datetime) -> BookEntry:
    """The entry without an invitation that ended and whose outcome was kept long enough, so its two people's ids are
    not kept.
    """
    ended = _ended_call(entry, now)
    if ended is None or now < ended.at + ENDED_CALL_KEPT:
        return entry
    return BookEntry(table_id=entry.table_id, agent_account=entry.agent_account, epoch=entry.epoch)


def ended_outcome(entry: BookEntry | None, viewer_account: str, now: datetime) -> CallOutcome | None:
    """How the viewer's last call to the agent ended, while the entry keeps it; only the one who called is told."""
    ended = None if entry is None else _ended_call(entry, now)
    if ended is None or ended.inviter != viewer_account or not ended.at <= now < ended.at + ENDED_CALL_KEPT:
        return None
    return _OUTCOMES[ended.outcome]


def _agent_of(chair: Chair) -> Occupant | None:
    """The occupant of the chair when it is an agent; None for a person and a free chair."""
    return chair.occupant if chair.occupant is not None and chair.occupant.is_agent else None


def seated_agents(table: TableRecord) -> tuple[SeatedAgent, ...]:
    """The agents that hold a chair at the table, in chair order."""
    return tuple(
        SeatedAgent(agent.account_id, agent.display_name) for chair in table.chairs if (agent := _agent_of(chair))
    )


def agent_in_chair(table: TableRecord, seat: int) -> str | None:
    """The account of the agent that holds the chair `seat`; None for a person, a free chair and a seat not there."""
    return next(
        (agent.account_id for chair in table.chairs if chair.seat == seat and (agent := _agent_of(chair))), None
    )


def agents_seated_at(table: TableRecord) -> frozenset[str]:
    """The accounts of the agents that hold a chair at the table."""
    return frozenset(agent.account for agent in seated_agents(table))


def at_the_table(table: TableRecord, connected_accounts: frozenset[str]) -> frozenset[str]:
    """Who counts as at the table for a person's call: whoever holds an open stream on it and whoever holds a chair."""
    return connected_accounts | {chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}


@dataclass(frozen=True)
class SeatedAccounts:
    """Who holds each occupied chair of a live table, with the version of the table that read them."""

    version: int
    account_by_seat: Mapping[int, str]


def seated_accounts_of(table: TableRecord) -> SeatedAccounts:
    return SeatedAccounts(
        table.version, {chair.seat: chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}
    )


def control_shown(*, viewer_present: bool, viewer_is_member: bool, sends_agent_away: bool) -> bool:
    """Whether the person sees the control that calls agents: at the table and either a member of the calling group or
    one who may send an agent away.
    """
    return viewer_present and (viewer_is_member or sends_agent_away)


def may_send_away(
    table: TableRecord, agent_account: str, *, viewer_account: str, viewer_present: bool, viewer_is_member: bool
) -> bool:
    """Whether the person may send the agent away from the table: present and a member of the calling group, or the
    owner its chair stores for the agent.
    """
    seated = seat_of(table, agent_account)
    owner = None if seated is None or seated.occupant is None else seated.occupant.owner_account
    return core.send_away_allowed(
        sender_present=viewer_present,
        sender_is_member=viewer_is_member,
        sender_is_owner=owner == viewer_account,
        place_right=False,
    )


def _decided(
    facts: CallFacts, table: TableRecord, entry: BookEntry | None, invitation_id: str, now: datetime
) -> core.Invited | Literal[OfferState.HERE] | InviteRefusal:
    """What the call to the agent at the live table comes to, in this order: the agent holds a chair there, which the
    person may send it away from or not; then core's order of refusals, ending in the invitation the call writes.
    """
    if seat_of(table, facts.agent_account) is not None:
        if may_send_away(
            table,
            facts.agent_account,
            viewer_account=facts.viewer_account,
            viewer_present=facts.viewer_present,
            viewer_is_member=facts.viewer_is_member,
        ):
            return OfferState.HERE
        return InviteRefusal.NOT_A_MEMBER if facts.viewer_present else InviteRefusal.NOT_PRESENT
    if facts.owner_account is None:
        return InviteRefusal.NOT_OFFERED
    called = core.invite(
        None if entry is None else _core_entry(entry),
        core.CallFacts(
            inviter=facts.viewer_account,
            inviter_present=facts.viewer_present,
            inviter_is_member=facts.viewer_is_member,
            agent_listens=facts.agent_listens,
            agent_seated=False,
            owner=facts.owner_account,
            owner_at=core.OwnerAt.AT_BINDING if facts.owner_present else core.OwnerAt.ABSENT,
            bound_to=table.id.value,
            seat_free=free_seat_for(table, facts.agent_account) is not None,
        ),
        invitation_id=invitation_id,
        now=now,
    )
    return _REFUSALS[called] if isinstance(called, core.InviteRefusal) else called


def _offered(
    facts: CallFacts, table: TableRecord | None, entry: BookEntry | None, now: datetime
) -> tuple[OfferState | InviteRefusal, datetime | None]:
    """What the person's call to the agent comes to, and when the open invitation of an inviting answer ends."""
    if table is None:
        return InviteRefusal.NO_TABLE, None
    decided = _decided(facts, table, entry, _DISPLAY_INVITATION_ID, now)
    if not isinstance(decided, core.Invited):
        return decided, None
    standing = None if entry is None else _core_entry(entry).invitation
    if standing is not None and standing.id == decided.invitation.id:
        return OfferState.INVITING, decided.invitation.expires_at
    return OfferState.AVAILABLE, None


def offer_of(
    facts: CallFacts, table: TableRecord | None, entry: BookEntry | None, now: datetime
) -> OfferState | InviteRefusal:
    """What the person's call to the agent comes to, which `core.invite` decides but for the agent that holds a chair:
    the table is not live; the agent holds a chair there, which the person may send it away from, whether it listens
    or its owner is present; then core's order, with a chair left open by a hand that waits for a sitter free, but an
    agent that left a chair of that hand offered that chair only.
    """
    return _offered(facts, table, entry, now)[0]


def seated_call_facts(
    agent_account: str, *, viewer_account: str, viewer_present: bool, viewer_is_member: bool
) -> CallFacts:
    """The facts of a person's call to an agent that holds a chair at the table: no token states its owner and it does
    not listen, which `offer_of` does not ask of a seated agent.
    """
    return CallFacts(
        viewer_account=viewer_account,
        viewer_present=viewer_present,
        viewer_is_member=viewer_is_member,
        agent_account=agent_account,
        agent_listens=False,
        owner_account=None,
        owner_present=False,
    )


def call_offer_of(facts: CallFacts, table: TableRecord | None, entry: BookEntry | None, now: datetime) -> CallOffer:
    """`offer_of`, with how long the invitation of an inviting row stands, in whole seconds on the same clock, and how
    the caller's last call ended. The outcome is told wherever the person could call the agent again and where only the
    room or the owner stands in the way, which are the two reasons an accept ends a call with.
    """
    answer, ends_at = _offered(facts, table, entry, now)
    ends_in_seconds = None if ends_at is None else math.ceil((ends_at - now).total_seconds())
    outcome = (
        None if entry is None or answer not in _CALLABLE_AGAIN else ended_outcome(entry, facts.viewer_account, now)
    )
    return CallOffer(answer, ends_in_seconds, outcome)


def table_offers_of(
    table: TableRecord,
    calls: Sequence[CallFacts],
    entries: Sequence[BookEntry | None],
    seated_facts: Callable[[str], CallFacts],
    now: datetime,
) -> TableOffers:
    """Each call's offer from the agent's book row, and the offer of each seated agent no call names, on the facts
    `seated_facts` gives for its account.
    """
    named = {call.agent_account for call in calls}
    return TableOffers(
        tuple(call_offer_of(call, table, entry, now) for call, entry in zip(calls, entries, strict=True)),
        tuple(
            SeatedOffer(agent.account, agent.name, call_offer_of(seated_facts(agent.account), table, None, now))
            for agent in seated_agents(table)
            if agent.account not in named
        ),
    )


def offers_at(
    transactions: TableTransactions,
    table_id: TableId,
    calls: Sequence[CallFacts],
    seated_facts: Callable[[str], CallFacts],
    now: datetime,
) -> TableOffers | None:
    """Each call's offer and, from the same read of the table and the agents' rows, the offer of each seated agent no
    call names, on the facts `seated_facts` gives for its account; None when no live table has the id.
    """
    with transactions.begin() as transaction:
        if not isinstance(table := transaction.table(table_id), TableRecord):
            return None
        entries = [transaction.locked_book_entry(table_id, call.agent_account) for call in calls]
    return table_offers_of(table, calls, entries, seated_facts, now)


def decide_invite(
    table: TableRecord | None, entry: BookEntry | None, facts: CallFacts, invitation_id: InvitationId, now: datetime
) -> tuple[BookEntry, Invitation] | InviteRefusal:
    """The agent's row with the new invitation, which expires after core's `INVITATION_SECONDS` from `now`, and what
    the agent is shown of it; or, for a person who already invited the agent, the row as it is; or why the person's
    call offers nothing.
    """
    if table is None:
        return InviteRefusal.NO_TABLE
    decided = _decided(facts, table, entry, invitation_id.value, now)
    if isinstance(decided, core.Invited):
        return _row_of(table.id, facts.agent_account, decided.entry), decided.invitation
    return InviteRefusal.NOT_OFFERED if decided is OfferState.HERE else decided


def decide_accept(
    table: TableRecord,
    entry: BookEntry,
    agent: Actor,
    owner_account: str | None,
    acceptance: Acceptance,
    *,
    owner_present: bool,
    now: datetime,
    new_hand: NewHand | None,
) -> AcceptDecision:
    """Seat the agent at the chair it held in the running hand, or at the lowest free chair when it holds no mark of
    the running hand, through the sit decision, or refuse; core decides which.

    Stale changes nothing, a token that names no owner included. Without the owner at the table the accept is
    `sponsor_away`, and with no free chair for the agent (the chair it held in the running hand being taken
    included) `busy`; both end the invitation as of now and keep it for its caller to be told how it ended. Skat
    checks no lease at an accept.
    """
    stale = AcceptDecision(table, entry, AcceptInvitationRefusal.STALE_INVITATION)
    if owner_account is None:
        return stale
    seat = free_seat_for(table, agent.account_id)
    read = _core_entry(entry)
    decided = core.check_accept(
        read,
        AcceptInvitationArguments(
            place=PlaceRef(kind=TABLE_PLACE_KIND, id=acceptance.table_id),
            invitation=acceptance.invitation_id,
            epoch=acceptance.epoch,
        ),
        core.AcceptFacts(
            holds_lease=True,
            owner=owner_account,
            owner_at=core.OwnerAt.AT_BINDING if owner_present else core.OwnerAt.ABSENT,
            agent_seated=seat_of(table, agent.account_id) is not None,
            seat_free=seat is not None,
        ),
        now=now,
    )
    if isinstance(decided, core.AcceptRefused):
        if decided.ended is None or read.invitation is None:
            return AcceptDecision(table, entry, decided.refusal)
        return AcceptDecision(table, _kept_row(entry, read.invitation, decided.ended), decided.refusal)
    # Core accepts only where a chair is free for the agent.
    sat = sit_with_plans(table, agent, cast("int", seat), new_hand, now).table
    return AcceptDecision(sat, _row_of(entry.table_id, entry.agent_account, decided.entry))


def standings_among(
    entries: Iterable[BookEntry], held: Iterable[TableId], *, serves_view: bool, now: datetime
) -> tuple[Standing, ...]:
    """An agent's standing: every table it holds a chair at as active, and every table with an open invitation it
    holds no chair at as invited, in table id order; `serves_view` is whether the agent's lease runs, which counts for
    the tables it holds a chair at.
    """
    active = frozenset(held)
    read = {entry.table_id: _core_entry(entry) for entry in entries}
    standings = (
        core.standing(
            read.get(table_id),
            PlaceRef(kind=TABLE_PLACE_KIND, id=table_id.value),
            held=StandingState.ACTIVE if table_id in active else None,
            serves_view=serves_view and table_id in active,
            parent=None,
            now=now,
        )
        for table_id in sorted(active | read.keys(), key=lambda table_id: table_id.value)
    )
    return tuple(standing for standing in standings if standing is not None)


def standings_of(
    transactions: TableTransactions, agent_account: str, *, serves_view: bool, now: datetime
) -> tuple[Standing, ...]:
    """Every table the agent holds a chair at or has an open invitation to, from one read; the read forgets an
    invitation of the agent that ran out and was told long enough by `now`.
    """
    with transactions.begin() as transaction:
        entries = transaction.locked_book_entries_of(agent_account)
        kept = tuple(forgotten_if_expired(entry, now) for entry in entries)
        for before, after in zip(entries, kept, strict=True):
            if after != before:
                transaction.save_book_entry(after)
        held = [each.table_id for each in transaction.tables_of(agent_account)]
    return standings_among(kept, held, serves_view=serves_view, now=now)


def book_after_send_away(entry: BookEntry | None, table_id: TableId, agent_account: str) -> BookEntry:
    """The agent's row once it was sent away: the epoch raised and any invitation to this table cleared, so an accept
    of an older epoch is stale and the standing no longer offers the place; a missing row counts as epoch 0.
    """
    return _row_of(table_id, agent_account, core.after_send_away(None if entry is None else _core_entry(entry)))


def keep_turn_state(
    transactions: TableTransactions,
    account_id: str,
    table_id: str,
    stopped: str | None,
    thinking: bool,
    now: datetime,
) -> bool:
    """Keep what the account states about its turns at the table for the chair it sits at, in place of its last
    statement, under the table's row lock and without raising the version; False, and nothing kept, when the account
    holds no chair at a live table with that id.
    """
    if (identifier := TableId.parse(table_id)) is None:
        return False
    with transactions.begin() as transaction:
        table = transaction.locked_table(identifier)
        own = None if table is None else seat_of(table, account_id)
        if own is None:
            return False
        transaction.save_turn_state(identifier, replace(own, turn_state=TurnStatement(stopped, thinking, now)))
    return True
