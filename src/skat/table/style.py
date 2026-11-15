from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.table.records import Decision, Refusal
from skat.table.rules import seat_of

if TYPE_CHECKING:
    from skat.table.records import Actor, TableRecord, TableStyle

STYLE_COMMAND: Final = "style"


@dataclass(frozen=True)
class StyleCommand:
    """A seated member names the style the whole table has from now on; the chair comes from the session."""

    command_id: str
    table_id: str
    style: TableStyle


def style_payload(command: StyleCommand) -> str:
    """The receipt's payload: a retry repeats its style, so another style under the same id is another request."""
    return f"{command.table_id}:{command.style.value}"


def decide_style(table: TableRecord, actor: Actor, command: StyleCommand) -> Decision:
    """The table takes the style: only a member with a chair may change it, a watcher is not seated.

    The style the table already has stays as it is, with no new version, so a tap from a second tab is no error.
    """
    if seat_of(table, actor.account_id) is None:
        return Decision(table, Refusal.NOT_SEATED)
    if command.style is table.style:
        return Decision(table)
    return Decision(replace(table, version=table.version + 1, style=command.style))
