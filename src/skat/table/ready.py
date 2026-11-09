from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.table.game_list import result_view_of
from skat.table.records import Decision, Refusal
from skat.table.rules import seat_of

if TYPE_CHECKING:
    from skat.table.records import Actor, TableRecord

READY_COMMAND: Final = "ready"


@dataclass(frozen=True)
class ReadyCommand:
    """„Weiter“ after a result; `ordinal` numbers the result the page saw, and the chair comes from the session."""

    command_id: str
    table_id: str
    ordinal: int


def ready_payload(command: ReadyCommand) -> str:
    """The receipt's payload: a retry repeats its ordinal, so „Weiter“ for another result is another request."""
    return f"{command.table_id}:{command.ordinal}"


def decide_ready(table: TableRecord, actor: Actor, command: ReadyCommand) -> Decision:
    """„Weiter“ marks the actor's chair: no chair, no pending result, then another result than the pending one.

    A chair already ready stays as it is, with no new
    version, so a tap from a second tab is no error.
    """
    chair = seat_of(table, actor.account_id)
    if chair is None:
        return Decision(table, Refusal.NOT_SEATED)
    result = result_view_of(table)
    if result is None:
        return Decision(table, Refusal.NO_RESULT)
    if command.ordinal != result.ordinal:
        return Decision(table, Refusal.STALE_RESULT)
    if chair.ready:
        return Decision(table)
    chairs = tuple(replace(each, ready=True) if each.seat == chair.seat else each for each in table.chairs)
    return Decision(replace(table, version=table.version + 1, chairs=chairs))
