"""A table is a member place: an agent is a member of it exactly while it holds a chair there or an invitation to it
is open, so the book stores only the open invitations and each pair's epoch, never the membership itself.
"""

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from skat.table.records import Chair, Occupant, OccupantKind, OpaqueId, TableId, TableRecord
from skat.table.rules import decide_sit, free_seat_for, seat_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from datetime import datetime, timedelta

    from skat.table.records import Actor, NewHand
    from skat.table.transactions import TableTransactions

__all__ = [
    "AcceptDecision",
    "AcceptResult",
    "Acceptance",
    "BookEntry",
    "CallFacts",
    "CallOffer",
    "InvitationId",
    "InvitationOffer",
    "InviteRefusal",
    "MemberBook",
    "MemberRefusal",
    "MembershipState",
    "OfferState",
    "OpenInvitation",
    "SeatedAgent",
    "SeatedOffer",
    "TableOffers",
    "TableStanding",
    "agent_in_chair",
    "agents_seated_at",
    "call_offer_of",
    "control_shown",
    "decide_accept",
    "decide_invite",
    "forgotten_if_expired",
    "offer_of",
    "open_invitation",
    "seated_agents",
    "seated_call_facts",
    "standings_among",
    "standings_of",
    "table_offers_of",
]


class MembershipState(StrEnum):
    """What a table is to an agent: one it holds a chair at, or one it is invited to."""

    INVITED = "invited"
    ACTIVE = "active"


class MemberRefusal(StrEnum):
    """Why an accept seated nobody."""

    STALE_INVITATION = "stale_invitation"
    SPONSOR_AWAY = "sponsor_away"
    BUSY = "busy"


class InviteRefusal(StrEnum):
    """Why a person's call offers an agent nothing: the one vocabulary of a row's absence and a call's refusal."""

    NO_TABLE = "no-table"
    NOT_PRESENT = "not-present"
    NOT_A_MEMBER = "not-a-member"
    NOT_OFFERED = "not-offered"
    OWNER_ABSENT = "owner-absent"
    NO_FREE_CHAIR = "no-free-chair"


class OfferState(StrEnum):
    """What an agent is to the person who may call it: free to call, called by that person and not yet answered, or
    seated at the table, where the person may send it away.
    """

    AVAILABLE = "available"
    INVITING = "inviting"
    HERE = "here"


class InvitationId(OpaqueId):
    """The id of an invitation."""


@dataclass(frozen=True)
class OpenInvitation:
    """An invitation as stored: its owner and inviter are the people it is bound to and go when it ends."""

    id: str
    expires_at: datetime
    owner_account: str
    inviter_account: str

    def offered(self, epoch: int) -> InvitationOffer:
        return InvitationOffer(self.id, epoch, self.expires_at)


@dataclass(frozen=True)
class BookEntry:
    """The book's row of one agent at one table: the table's epoch for it, and the invitation if one is open."""

    table_id: TableId
    agent_account: str
    epoch: int = 0
    invitation: OpenInvitation | None = None


@dataclass(frozen=True)
class InvitationOffer:
    """What an agent is shown of its invitation; no person is named."""

    id: str
    epoch: int
    expires_at: datetime


@dataclass(frozen=True)
class TableStanding:
    """A table in an agent's standing, with its invitation exactly when the state is invited."""

    table_id: TableId
    state: MembershipState
    invitation: InvitationOffer | None = None


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
    """What a call to one agent comes to now; `ends_in_seconds` is the whole seconds an open invitation still stands."""

    answer: OfferState | InviteRefusal
    ends_in_seconds: int | None = None


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
    refusal: MemberRefusal | None = None


@dataclass(frozen=True)
class AcceptResult:
    """What an accept did: why it seated nobody, and whether the table shows a game's result, for which the seated
    agent counts as ready, which may complete the marks for the next deal.
    """

    refusal: MemberRefusal | None = None
    result_pending: bool = False


class MemberBook(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def locked_book_entry(self, table_id: TableId, agent_account: str) -> BookEntry | None:
        """The agent's row at the table, locked for the transaction, or None when the book holds none."""
        ...

    def locked_book_entries_of(self, agent_account: str) -> tuple[BookEntry, ...]:
        """Every row of the agent, each locked for the transaction, in table id order."""
        ...

    def save_book_entry(self, entry: BookEntry) -> None:
        """Write the row, adding it when the book holds none for the pair."""
        ...

    def book_accounts_at(self, table_id: TableId) -> frozenset[str]:
        """Every agent the book holds a row of at the table."""
        ...


def open_invitation(entry: BookEntry | None, now: datetime) -> OpenInvitation | None:
    """The invitation the entry holds while it has not expired; an expiry is read on the service's clock."""
    if entry is None or entry.invitation is None or entry.invitation.expires_at <= now:
        return None
    return entry.invitation


def forgotten_if_expired(entry: BookEntry, now: datetime) -> BookEntry:
    """The entry without an invitation that ran out, so its two people's ids are not kept."""
    if entry.invitation is None or open_invitation(entry, now) is not None:
        return entry
    return BookEntry(table_id=entry.table_id, agent_account=entry.agent_account, epoch=entry.epoch)


def _agent_of(chair: Chair) -> Occupant | None:
    """The occupant of the chair when it is an agent; None for a person and a free chair."""
    return chair.occupant if chair.occupant is not None and chair.occupant.kind is OccupantKind.AGENT else None


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


def control_shown(*, viewer_present: bool, viewer_is_member: bool, sends_agent_away: bool) -> bool:
    """Whether the person sees the control that calls agents: at the table and either a member of the calling group or
    one who may send an agent away.
    """
    return viewer_present and (viewer_is_member or sends_agent_away)


def offer_of(
    facts: CallFacts, table: TableRecord | None, entry: BookEntry | None, now: datetime
) -> OfferState | InviteRefusal:
    """What the person's call to the agent comes to, decided in this order: the table is not live; the person is not
    at it; neither a member nor the owner its chair stores for the agent; the agent holds a chair there, which the
    person may send it away from, whether it listens or its owner is present; the agent does not listen or is invited
    there by someone else; the agent is invited by this person already; the owner is not at the table; no chair is free
    for the agent. A chair left open by a hand that waits for a sitter is free, but an agent that left a chair of that
    hand is offered that chair only.
    """
    if table is None:
        return InviteRefusal.NO_TABLE
    seated = seat_of(table, facts.agent_account)
    owns_the_chair = bool(seated and seated.occupant and seated.occupant.owner_account == facts.viewer_account)
    if not control_shown(
        viewer_present=facts.viewer_present, viewer_is_member=facts.viewer_is_member, sends_agent_away=owns_the_chair
    ):
        return InviteRefusal.NOT_PRESENT if not facts.viewer_present else InviteRefusal.NOT_A_MEMBER
    if seated is not None:
        return OfferState.HERE
    invitation = open_invitation(entry, now)
    invited_by_someone_else = invitation is not None and invitation.inviter_account != facts.viewer_account
    if not facts.agent_listens or invited_by_someone_else:
        return InviteRefusal.NOT_OFFERED
    if invitation is not None:
        return OfferState.INVITING
    if not facts.owner_present:
        return InviteRefusal.OWNER_ABSENT
    if free_seat_for(table, facts.agent_account) is None:
        return InviteRefusal.NO_FREE_CHAIR
    return OfferState.AVAILABLE


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
    """`offer_of`, with how long the invitation of an inviting row stands, in whole seconds on the same clock."""
    answer = offer_of(facts, table, entry, now)
    invitation = open_invitation(entry, now) if answer is OfferState.INVITING else None
    return CallOffer(answer, None if invitation is None else math.ceil((invitation.expires_at - now).total_seconds()))


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


def decide_invite(
    table: TableRecord | None,
    entry: BookEntry | None,
    facts: CallFacts,
    invitation_id: InvitationId,
    now: datetime,
    lasting: timedelta,
) -> tuple[BookEntry, InvitationOffer] | InviteRefusal:
    """The agent's row with the new invitation, which expires `lasting` after `now`, and what the agent is shown of it;
    or, for a person who already invited the agent, the row as it is; or why the person's call offers nothing.
    """
    if table is None:
        return InviteRefusal.NO_TABLE
    state = offer_of(facts, table, entry, now)
    if isinstance(state, InviteRefusal):
        return state
    if state is OfferState.HERE or facts.owner_account is None:
        return InviteRefusal.NOT_OFFERED
    standing = open_invitation(entry, now)
    if entry is not None and standing is not None:
        return entry, standing.offered(entry.epoch)
    invitation = OpenInvitation(invitation_id.value, now + lasting, facts.owner_account, facts.viewer_account)
    epoch = 0 if entry is None else entry.epoch
    return BookEntry(table.id, facts.agent_account, epoch, invitation), invitation.offered(epoch)


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
    the running hand, through the sit decision, or refuse; the decisions run in this order.

    Stale changes nothing: no invitation stands (none, expired, another id or epoch, another owner than the one it is
    bound to, a chair the agent already holds). Without the owner at the table the accept is `sponsor_away`, and with no
    free chair for the agent (the chair it held in the running hand being taken included) `busy`; both end the
    invitation.
    """
    invitation = open_invitation(entry, now)
    stale = (
        invitation is None
        or invitation.id != acceptance.invitation_id
        or entry.epoch != acceptance.epoch
        or invitation.owner_account != owner_account
        or seat_of(table, agent.account_id) is not None
    )
    if stale:
        return AcceptDecision(table, entry, MemberRefusal.STALE_INVITATION)
    ended = replace(entry, invitation=None)
    if not owner_present:
        return AcceptDecision(table, ended, MemberRefusal.SPONSOR_AWAY)
    seat = free_seat_for(table, agent.account_id)
    if seat is None:
        return AcceptDecision(table, ended, MemberRefusal.BUSY)
    return AcceptDecision(decide_sit(table, agent, seat, new_hand).table, ended)


def standings_among(entries: Iterable[BookEntry], held: Iterable[TableId], now: datetime) -> tuple[TableStanding, ...]:
    """An agent's standing: every table it holds a chair at as active, and every table with an open invitation it
    holds no chair at as invited, in table id order.
    """
    active = frozenset(held)
    standings = [TableStanding(table_id, MembershipState.ACTIVE) for table_id in active]
    for entry in entries:
        invitation = open_invitation(entry, now)
        if invitation is not None and entry.table_id not in active:
            standings.append(TableStanding(entry.table_id, MembershipState.INVITED, invitation.offered(entry.epoch)))
    return tuple(sorted(standings, key=lambda standing: standing.table_id.value))


def standings_of(transactions: TableTransactions, agent_account: str, now: datetime) -> tuple[TableStanding, ...]:
    """Every table the agent holds a chair at or has an open invitation to, from one read; the read forgets an
    invitation of the agent that ran out by `now`.
    """
    with transactions.begin() as transaction:
        entries = transaction.locked_book_entries_of(agent_account)
        kept = tuple(forgotten_if_expired(entry, now) for entry in entries)
        for before, after in zip(entries, kept, strict=True):
            if after != before:
                transaction.save_book_entry(after)
        held = [each.table_id for each in transaction.tables_of(agent_account)]
    return standings_among(kept, held, now)
