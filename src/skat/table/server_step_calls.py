"""The steps the server takes on its own account as the table service offers them: each forwards to `ServerSteps`, built
by the service, which owns what a step needs.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from skat.table.records import TableId
    from skat.table.server_steps import EndAnswerLapse, ServerSteps
    from skat.table.transactions import HeldChair


class ServerStepCalls:
    """The table service's forwards to the server's own steps; a subclass builds the steps."""

    _server_steps: Callable[[], ServerSteps]

    def note_leave(self, table_id: TableId, account_id: str, hold_seconds: float, *, newest_wins: bool) -> None:
        """The server's step of storing a chair hold; see `ServerSteps.note_leave`."""
        self._server_steps().note_leave(table_id, account_id, hold_seconds, newest_wins=newest_wins)

    def clear_hold(self, table_id: TableId, account_id: str) -> None:
        """The server's step of dropping a chair hold at an arrival; see `ServerSteps.clear_hold`."""
        self._server_steps().clear_hold(table_id, account_id)

    def due_holds(self) -> tuple[HeldChair, ...]:
        """The chair holds due now; see `ServerSteps.due_holds`."""
        return self._server_steps().due_holds()

    def free_held_chair(self, table_id: TableId, account_id: str, absent: AbstractContextManager[bool | None]) -> bool:
        """The server's step of freeing a chair whose hold is due; see `ServerSteps.free_held_chair`."""
        return self._server_steps().free_held_chair(table_id, account_id, absent)

    def deal_next(self, table_id: TableId, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        """The server's step of dealing the next hand; see `ServerSteps.deal_next`."""
        return self._server_steps().deal_next(table_id, connected_accounts)

    def end_empty_table(
        self, table_id: TableId, connected_accounts: AbstractContextManager[frozenset[str] | None], empty_seconds: int
    ) -> bool:
        """The server's step of ending an empty table; see `ServerSteps.end_empty_table`."""
        return self._server_steps().end_empty_table(table_id, connected_accounts, empty_seconds)

    def note_presence(
        self, table_id: TableId, connected_accounts: AbstractContextManager[frozenset[str] | None], empty_seconds: int
    ) -> bool:
        """The server's step of noting who is present; see `ServerSteps.note_presence`."""
        return self._server_steps().note_presence(table_id, connected_accounts, empty_seconds)

    def resume_empty_waits(self, empty_seconds: int) -> dict[str, float]:
        """The server's step at its start; see `ServerSteps.resume_empty_waits`."""
        return self._server_steps().resume_empty_waits(empty_seconds)

    def lapse_end_answers(self, table_id: TableId) -> EndAnswerLapse:
        """The server's step of ending a proposal whose minute is over; see `ServerSteps.lapse_end_answers`."""
        return self._server_steps().lapse_end_answers(table_id)

    def pending_end_answers(self) -> dict[str, float]:
        """The server's step at its start; see `ServerSteps.pending_end_answers`."""
        return self._server_steps().pending_end_answers()
