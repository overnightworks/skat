"""A table is a member place: an agent is a member of it exactly while it holds a chair there or an invitation to it
is open, so the book stores only the open invitations and each pair's epoch, never the membership itself.
"""

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from skat.table.records import OccupantKind, OpaqueId, TableId, TableRecord
from skat.table.rules import decide_sit, seat_of

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from skat.table.records import Actor, NewHand

__all__ = [
    "AcceptDecision",
    "AcceptResult",
    "Acceptance",
    "BookEntry",
    "InvitationId",
    "InvitationOffer",
    "InvitationRequest",
    "InviteRefusal",
    "MemberBook",
    "MemberRefusal",
    "MembershipState",
    "OpenInvitation",
    "TableStanding",
    "agents_seated_at",
    "decide_accept",
    "decide_invite",
    "forgotten_if_expired",
    "open_invitation",
    "standings_among",
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
    """Why an invitation was not written."""

    NO_TABLE = "no-table"
    INVITATION_OPEN = "invitation-open"
    ALREADY_SEATED = "already-seated"


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
class InvitationRequest:
    """The invitation a caller asks for: the agent, the people it is bound to, and the instant it expires."""

    agent_account: str
    owner_account: str
    inviter_account: str
    expires_at: datetime


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


def agents_seated_at(table: TableRecord) -> frozenset[str]:
    """The agents that hold a chair at the table."""
    return frozenset(
        chair.occupant.account_id
        for chair in table.chairs
        if chair.occupant is not None and chair.occupant.kind is OccupantKind.AGENT
    )


def decide_invite(
    table: TableRecord | None,
    entry: BookEntry | None,
    request: InvitationRequest,
    invitation_id: InvitationId,
    now: datetime,
) -> tuple[BookEntry, InvitationOffer] | InviteRefusal:
    """The agent's row with the new invitation and what the agent is shown of it, or why none is written: the table is
    not live, an invitation to the agent is open, or the agent holds a chair there. Room at the table and the owner's
    presence are the caller's.
    """
    if table is None:
        return InviteRefusal.NO_TABLE
    if open_invitation(entry, now) is not None:
        return InviteRefusal.INVITATION_OPEN
    if seat_of(table, request.agent_account) is not None:
        return InviteRefusal.ALREADY_SEATED
    invitation = OpenInvitation(invitation_id.value, request.expires_at, request.owner_account, request.inviter_account)
    epoch = 0 if entry is None else entry.epoch
    return BookEntry(table.id, request.agent_account, epoch, invitation), invitation.offered(epoch)


def lowest_free_seat(table: TableRecord) -> int | None:
    return next((chair.seat for chair in table.chairs if chair.occupant is None), None)


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
    """Seat the agent at the lowest free chair through the sit decision, or refuse; the decisions run in this order.

    Stale changes nothing: no invitation stands (none, expired, another id or epoch, another owner than the one it is
    bound to, a chair the agent already holds). Without the owner at the table the accept is `sponsor_away`, and with no
    free chair `busy`; both end the invitation.
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
    seat = lowest_free_seat(table)
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
