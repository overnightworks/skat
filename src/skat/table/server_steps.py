"""The steps the server takes on its own account, with no actor, command id or receipt: freeing a chair its holder
left, the next deal, a table's end for being empty and the presence's bookkeeping. Each is one transaction over the
table's row lock; `TableService` forwards to them.
"""

from contextlib import ExitStack, nullcontext
from typing import TYPE_CHECKING

from skat.table.member_place import agents_seated_at
from skat.table.member_view import moment_recipients, view_recipients
from skat.table.records import Ending
from skat.table.rules import (
    PresenceStep,
    ResumeStep,
    dealt_next,
    decide_free_chair,
    drawn_hand,
    ends_empty,
    hold_frees_chair,
    next_deal_due,
    presence_step,
    present_at,
    resume_step,
)

if TYPE_CHECKING:
    import random
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from datetime import datetime

    from skat.table.member_view import ViewSignal
    from skat.table.records import TableId, TableRecord
    from skat.table.transactions import TableTransaction, TableTransactions


def members_of(transaction: TableTransaction, table: TableRecord) -> frozenset[str]:
    """The agents whose standing the table's end changes: those that hold a chair and those invited."""
    return agents_seated_at(table) | transaction.book_accounts_at(table.id)


class ServerSteps:
    """The server's own steps over the table's transactions; `live_leases` is read under a table's row lock and has no
    side effect, `tell` names the agents that sat down or left in a commit, `tell_view` the table and the agents whose
    view it changed and `tell_moments` the agents whose moment it changed, each after the commit and on the thread the
    step ran on.
    """

    def __init__(
        self,
        transactions: TableTransactions,
        live_leases: Callable[[], frozenset[str]],
        now: Callable[[], datetime],
        random_source: random.Random,
        tell: Callable[[frozenset[str]], None],
        tell_view: ViewSignal,
        tell_moments: Callable[[frozenset[str]], None],
    ) -> None:
        self._transactions = transactions
        self._live_leases = live_leases
        self._now = now
        self._random_source = random_source
        self._tell = tell
        self._tell_view = tell_view
        self._tell_moments = tell_moments

    def free_chair(self, table_id: TableId, account_id: str, due: AbstractContextManager[bool]) -> bool:
        """Free the account's chair on the server's own account, with no actor, command id or receipt.

        `due` is entered once the row is locked, so a command that committed meanwhile has had its say, and left
        after the commit; it yields whether the caller still wants the chair freed, and False changes nothing.
        A table on which a hand was dealt frees no chair this way, and the refusal writes nothing. The decision
        re-reads the chair under the row lock, so a repeat, or a chair the account left in the meantime, changes
        nothing either. True when it freed the chair.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None or not after_commit.enter_context(due) or not hold_frees_chair(table):
                return False
            decision = decide_free_chair(table, account_id)
            if decision.refusal is not None:
                return False
            transaction.save_table(decision.table, played_at=None)
        self._tell(agents_seated_at(table) - agents_seated_at(decision.table))
        self._tell_view(table_id, view_recipients(table, decision.table))
        self._tell_moments(moment_recipients(table, decision.table))
        return True

    def deal_next(self, table_id: TableId, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        """Deal the next hand on the server's own account, with no actor, command id or receipt.

        `connected_accounts` is entered once the row is locked and left after the commit; it yields who holds an open
        stream then, or None once the presence cannot tell, which deals nothing; a live lease counts for its occupant.
        The decision re-reads the table under the row lock, so a repeat, or a table that changed meanwhile, changes
        nothing. True when it dealt.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return False
            connected = present_at(table, after_commit.enter_context(connected_accounts), self._live_leases())
            if connected is None or not next_deal_due(table, connected):
                return False
            dealt = dealt_next(table, drawn_hand(table, self._random_source))
            transaction.save_table(dealt, played_at=self._now())
        self._tell_view(table_id, view_recipients(table, dealt))
        self._tell_moments(moment_recipients(table, dealt))
        return True

    def end_empty_table(
        self,
        table_id: TableId,
        connected_accounts: AbstractContextManager[frozenset[str] | None],
        empty_seconds: int,
    ) -> bool:
        """End a table nobody is connected to and on which no hand was dealt, on the server's own account, with no
        actor, command id or receipt.

        `connected_accounts` is entered once the row is locked and left after the commit; it yields who holds an open
        stream then, or None once the presence cannot tell. The decision reads who is present under the row lock, so a
        repeat, a table that ended meanwhile, or a stream that opened since changes nothing. `empty_seconds` is the
        wait the answer will name. True when it ended the table.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return False
            present = present_at(table, after_commit.enter_context(connected_accounts), self._live_leases())
            if not ends_empty(table, present):
                return False
            members = members_of(transaction, table)
            transaction.end_table(table_id, self._now(), Ending.empty(empty_seconds))
        self._tell(members)
        return True

    def note_presence(
        self,
        table_id: TableId,
        connected_accounts: AbstractContextManager[frozenset[str] | None],
        empty_seconds: int,
    ) -> bool:
        """Bring the time since when nobody has been at the table in line with who is present, on the server's own
        account, with no actor, command id, receipt or version change.

        `connected_accounts` is entered once the row is locked and left after the commit, as for `end_empty_table`,
        so the last write after any change reflects the latest truth. A table someone arrives at after its time was
        up ends instead of reviving. True when it ended the table.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return False
            present = present_at(table, after_commit.enter_context(connected_accounts), self._live_leases())
            now = self._now()
            step = presence_step(table, present, transaction.empty_since(table_id), now, empty_seconds)
            members: frozenset[str] = members_of(transaction, table) if step is PresenceStep.END else frozenset()
            if step is PresenceStep.END:
                transaction.end_table(table_id, now, Ending.empty(empty_seconds))
            elif step is not PresenceStep.KEEP:
                transaction.set_empty_since(table_id, now if step is PresenceStep.STAMP else None)
        self._tell(members)
        return step is PresenceStep.END

    def resume_empty_waits(self, empty_seconds: int) -> dict[str, float]:
        """At the server's start: give every live table on which no hand was dealt and that has no time one, end
        every such table whose wait is already up, and answer each remaining table's id with the seconds left of its
        wait; a table with a dealt hand pauses and is left out.
        """
        now = self._now()
        with self._transactions.begin() as transaction:
            resumed = tuple(
                (wait.table_id, resume_step(wait.dealer, wait.empty_since, now, empty_seconds))
                for wait in transaction.live_empty_since()
            )
            for table_id, resume in resumed:
                if resume.step is ResumeStep.STAMP:
                    transaction.set_empty_since(table_id, now)
        left: dict[str, float] = {}
        for table_id, resume in resumed:
            if resume.step is ResumeStep.SKIP:
                continue
            if resume.step is ResumeStep.END and self.end_empty_table(
                table_id, nullcontext(frozenset()), empty_seconds
            ):
                continue
            left[table_id.value] = resume.seconds_left
        return left
