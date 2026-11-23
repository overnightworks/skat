"""The steps the server takes on its own account, with no actor, command id or receipt: storing, clearing and
freeing a chair hold, the next deal and its pause, a table's end for being empty and the presence's bookkeeping. Each
is one transaction, over the table's row lock where it decides; `TableService` forwards to them.
"""

from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from skat.table.member_place import agents_seated_at, ended_by_owner_leaving
from skat.table.member_view import view_recipients
from skat.table.records import Ending, TableRecord
from skat.table.rules import (
    NEXT_DEAL_PAUSE_SECONDS,
    PresenceStep,
    dealt_next,
    decide_free_chair,
    drawn_hand,
    empty_step,
    hold_frees_chair,
    next_deal_due,
    presence_step,
    present_at,
    seat_of,
    seated_accounts,
)
from skat.table.series_end import (
    answer_left,
    decide_end_answer_lapse,
    end_answer_left,
    new_series_lapsed,
)
from skat.table.transactions import save_traced

if TYPE_CHECKING:
    import random
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from datetime import datetime

    from skat.table.member_view import ViewSignal
    from skat.table.records import TableId
    from skat.table.rules import EmptyWait
    from skat.table.transactions import HeldChair, TableTransaction, TableTransactions

# The most due holds, pauses or waits one sweep acts on; the rest wait for the next.
DUE_PER_SWEEP: Final = 100


@dataclass(frozen=True)
class EndAnswerLapse:
    """What a lapse found: the seconds the answers it still waits for have left, None when none stand, and whether it
    ended the table because a seated seat stayed silent at the series' end.
    """

    seconds_left: float | None
    table_stopped: bool = False


def members_of(transaction: TableTransaction, table: TableRecord) -> frozenset[str]:
    """The agents whose standing the table's end changes: those that hold a chair and those invited."""
    return agents_seated_at(table) | transaction.book_accounts_at(table.id)


class ServerSteps:
    """The server's own steps over the table's transactions; `live_leases` is read under a table's row lock and has no
    side effect, `tell` names the agents that sat down or left in a commit and `tell_view` the table and the agents
    whose view it changed, each after the commit and on the thread the step ran on. `trace` is read on that thread when
    a step saves a table, for the traces the save enters in.
    """

    def __init__(
        self,
        transactions: TableTransactions,
        live_leases: Callable[[], frozenset[str]],
        now: Callable[[], datetime],
        random_source: random.Random,
        tell: Callable[[frozenset[str]], None],
        tell_view: ViewSignal,
        trace: Callable[[], str | None],
    ) -> None:
        self._transactions = transactions
        self._live_leases = live_leases
        self._now = now
        self._random_source = random_source
        self._tell = tell
        self._tell_view = tell_view
        self._trace = trace

    def note_leave(self, table_id: TableId, account_id: str, hold_seconds: float, *, newest_wins: bool) -> None:
        """Store the account's chair hold as due `hold_seconds` from now: when `newest_wins` in place of an earlier
        one, the newest leave on any pod winning, else only where the account has no hold at the table. A watcher, an
        ended table or a forgotten one stores nothing. A watcher has no chair to hold, so its leave is the last
        stream's end and ends the invitations bound to it at once; a seated account's are ended when its hold frees.
        """
        ended: frozenset[str] = frozenset()
        with self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is not None and seat_of(table, account_id) is None:
                ended = self._end_invitations_of(transaction, table_id, account_id)
            transaction.store_leave(table_id, account_id, hold_seconds, newest_wins=newest_wins)
        self._tell(ended)

    def _end_invitations_of(
        self, transaction: TableTransaction, table_id: TableId, owner_account: str
    ) -> frozenset[str]:
        """End each open invitation at the table bound to the owner as owner away, in the caller's transaction; the
        agents to tell.
        """
        ended = ended_by_owner_leaving(transaction.locked_book_entries_at(table_id), owner_account, self._now())
        for entry in ended:
            transaction.save_book_entry(entry)
        return frozenset(entry.agent_account for entry in ended)

    def clear_hold(self, table_id: TableId, account_id: str) -> None:
        """Drop the account's chair hold, as it arrived; a freeing in flight makes this wait for its commit."""
        with self._transactions.begin() as transaction:
            transaction.delete_hold(table_id, account_id)

    def due_holds(self) -> tuple[HeldChair, ...]:
        """The chair holds due now, the earliest first and at most `DUE_PER_SWEEP`: a candidate list."""
        with self._transactions.begin() as transaction:
            return transaction.due_holds(DUE_PER_SWEEP)

    def free_held_chair(self, table_id: TableId, account_id: str, absent: AbstractContextManager[bool | None]) -> bool:
        """Free the chair of an account whose stored hold is due, on the server's own account, with no actor, command
        id or receipt, and drop the hold in the same transaction, so it frees once.

        The table's row is locked first, then the hold's. A hold not due, or gone, changes nothing. `absent` is entered
        then and left after the commit: None frees nothing and keeps the hold for another pod, False keeps the chair
        and drops the hold, True frees the chair where the rules let a hold free it, and the hold is dropped either
        way; a guard that raises rolls everything back. The hold of an ended or forgotten table is dropped. An account
        found absent has left the table, so each open invitation bound to it ends as owner away in the same
        transaction, whether or not the rules let the hold free its chair. True when it freed the chair.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                transaction.delete_hold(table_id, account_id)
                return False
            if not transaction.locked_hold_due(table_id, account_id):
                return False
            is_absent = after_commit.enter_context(absent)
            if is_absent is None:
                return False
            transaction.delete_hold(table_id, account_id)
            if not is_absent:
                return False
            ended = self._end_invitations_of(transaction, table_id, account_id)
            decision = decide_free_chair(table, account_id) if hold_frees_chair(table) else None
            if decision is None or decision.refusal is not None:
                decision = None
            else:
                save_traced(transaction, table, decision.table, self._trace(), played_at=None)
        if decision is None:
            self._tell(ended)
            return False
        self._tell(ended | agents_seated_at(table) - agents_seated_at(decision.table))
        self._tell_view(table_id, view_recipients(table, decision.table))
        return True

    def deal_next(self, table_id: TableId, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        """Deal the next hand at once, whether or not a pause is pending, on the server's own account, with no actor,
        command id or receipt; the pause of a table that dealt is dropped.

        `connected_accounts` is entered once the row is locked and left after the commit; it yields who holds an open
        stream then, or None once the presence cannot tell, which deals nothing; a live lease counts for its occupant.
        The decision re-reads the table under the row lock, so a repeat, or a table that changed meanwhile, changes
        nothing. True when it dealt.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return False
            dealt = self._dealt_if_due(table, after_commit.enter_context(connected_accounts))
            if dealt is None:
                return False
            transaction.delete_next_deal(table_id)
            save_traced(transaction, table, dealt, self._trace(), played_at=self._now())
        self._tell_view(table_id, view_recipients(table, dealt))
        return True

    def pause_next_deal(self, table_id: TableId) -> None:
        """Start the table's pause before its next deal, from now on the store's clock, where it has none: a request
        during a pending pause neither cuts nor stretches it. A table that was not dealt on or has ended gets none.
        """
        with self._transactions.begin() as transaction:
            transaction.store_next_deal(table_id, NEXT_DEAL_PAUSE_SECONDS, replace=False)

    def deal_next_soon(self, table_id: TableId) -> None:
        """Make the table's next deal due now, for the sweep to ask for again after a deal that failed."""
        with self._transactions.begin() as transaction:
            transaction.store_next_deal(table_id, 0, replace=True)

    def due_next_deals(self) -> tuple[TableId, ...]:
        """The tables whose pause is over, the earliest first and at most `DUE_PER_SWEEP`: a candidate list."""
        with self._transactions.begin() as transaction:
            return transaction.due_next_deals(DUE_PER_SWEEP)

    def deal_after_pause(
        self,
        table_id: TableId,
        connected_accounts: Callable[[frozenset[str]], AbstractContextManager[frozenset[str] | None]],
    ) -> bool:
        """Deal the next hand of a table whose pause is over, on the server's own account, with no actor, command id
        or receipt, and drop the pause in the same transaction, so it deals once.

        The table's row is locked first, then the pause's. A pause not over, or gone, changes nothing. A pause that is
        over is dropped whether or not the table is dealt: its deal is due only while the three are connected, and a
        player who comes back starts the next pause. `connected_accounts` is called with the accounts seated at the
        table and its result entered then, as for `deal_next`; None keeps the pause for another pod, and a guard
        that raises, as for a roster that cannot say whether those seated are gone, rolls everything back and keeps
        it. The pause of an ended or forgotten table is dropped. True when it dealt.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                transaction.delete_next_deal(table_id)
                return False
            if not transaction.locked_next_deal_due(table_id):
                return False
            connected = after_commit.enter_context(connected_accounts(seated_accounts(table)))
            if connected is None:
                return False
            transaction.delete_next_deal(table_id)
            dealt = self._dealt_if_due(table, connected)
            if dealt is None:
                return False
            save_traced(transaction, table, dealt, self._trace(), played_at=self._now())
        self._tell_view(table_id, view_recipients(table, dealt))
        return True

    def _dealt_if_due(self, table: TableRecord, connected_accounts: frozenset[str] | None) -> TableRecord | None:
        """The table with its next hand when the rules make it due for those connected, else None."""
        connected = present_at(table, connected_accounts, self._live_leases())
        if connected is None or not next_deal_due(table, connected):
            return None
        return dealt_next(table, drawn_hand(table, self._random_source))

    def due_empty_tables(self, empty_seconds: int) -> tuple[TableId, ...]:
        """The tables whose wait for somebody is up, the longest waiting first and at most `DUE_PER_SWEEP`: a
        candidate list.
        """
        with self._transactions.begin() as transaction:
            return transaction.due_empty_tables(empty_seconds, DUE_PER_SWEEP)

    def end_empty_table(
        self,
        table_id: TableId,
        connected_accounts: AbstractContextManager[frozenset[str] | None],
        empty_seconds: int,
    ) -> bool:
        """Settle a table whose wait for somebody looked up, on the server's own account, with no actor, command id or
        receipt: end it when nobody is connected and its wait is up on the store's clock, and clear the time since when
        nobody was there when somebody is, which never ends it.

        `connected_accounts` is entered once the row is locked and left after the commit; it yields who holds an open
        stream then, or None once the presence cannot tell. The decision reads who is present and the wait under the
        row lock, so a repeat, a table that ended meanwhile, or a stream that opened since ends nothing twice.
        `empty_seconds` is the wait the answer will name. True when it ended the table.
        """
        return self._settle_presence(table_id, connected_accounts, empty_seconds, empty_step)

    def note_presence(
        self,
        table_id: TableId,
        connected_accounts: AbstractContextManager[frozenset[str] | None],
        empty_seconds: int,
    ) -> bool:
        """Bring the time since when nobody has been at the table in line with who is present, on the server's own
        account, with no actor, command id, receipt or version change.

        `connected_accounts` is entered once the row is locked and left after the commit, as for `end_empty_table`,
        so the last write after any change reflects the latest truth. A table someone arrives at after its wait was
        up ends instead of reviving. True when it ended the table.
        """
        return self._settle_presence(table_id, connected_accounts, empty_seconds, presence_step)

    def _settle_presence(
        self,
        table_id: TableId,
        connected_accounts: AbstractContextManager[frozenset[str] | None],
        empty_seconds: int,
        decide: Callable[[TableRecord, frozenset[str] | None, EmptyWait], PresenceStep],
    ) -> bool:
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return False
            present = present_at(table, after_commit.enter_context(connected_accounts), self._live_leases())
            step = decide(table, present, transaction.empty_wait(table_id, empty_seconds))
            members: frozenset[str] = members_of(transaction, table) if step is PresenceStep.END else frozenset()
            if step is PresenceStep.END:
                transaction.end_table(table_id, self._now(), Ending.empty(empty_seconds))
            elif step is PresenceStep.STAMP:
                transaction.stamp_empty_since(table_id)
            elif step is PresenceStep.CLEAR:
                transaction.clear_empty_since(table_id)
        self._tell(members)
        return step is PresenceStep.END

    def lapse_end_answers(self, table_id: TableId) -> EndAnswerLapse:
        """End what the table's minute of answers decides once it is over, on the server's own account, with no actor,
        command id or receipt: a proposal to end the series ends, and at the series' end a seated seat that never chose
        „Neue Serie“ ends the table in the same transaction. The decision re-reads the table under the row lock, so a
        repeat, an answer that came meanwhile or a table that ended changes nothing. The seconds an ask that still
        stands has left, None when none stands any more.
        """
        now = self._now()
        with self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return EndAnswerLapse(None)
            members: frozenset[str] = frozenset()
            decided = decide_end_answer_lapse(table, now).table
            stops = new_series_lapsed(decided, now)
            if stops:
                members = members_of(transaction, table)
                transaction.end_table(table_id, now, Ending.stopped())
            else:
                left = end_answer_left(decided, now)
                if decided.version == table.version:
                    return EndAnswerLapse(None if left is None else max(0.0, left.total_seconds()))
                save_traced(transaction, table, decided, self._trace(), played_at=None)
        if stops:
            self._tell(members)
            return EndAnswerLapse(None, table_stopped=True)
        self._tell_view(table_id, view_recipients(table, decided))
        return EndAnswerLapse(None)

    def pending_end_answers(self) -> dict[str, float]:
        """At the server's start: the seconds each live table's standing proposal still waits for its answers, zero
        for one whose minute is over.
        """
        now = self._now()
        with self._transactions.begin() as transaction:
            asks = transaction.live_end_asks()
        return {ask.table_id.value: max(0.0, answer_left(ask.asked_at, now).total_seconds()) for ask in asks}
