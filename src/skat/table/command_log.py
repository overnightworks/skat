"""The one log line of a table command: `table_command.ended` with the command, the table's id and how it ended."""

import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from logline import StepTimer

from skat.table.records import TableId

if TYPE_CHECKING:
    from skat.table.views import CommandResult

_LOGGER = logging.getLogger(__name__)


class CommandNotRun(StrEnum):
    """Why a table command did not run, beside the refusals of `skat.table.records`."""

    NO_TABLE = "no-table"


def command_step(command: str, table_id: str | None = None) -> StepTimer:
    """The timer of a table command's line; the id is logged only when it names a table, as parsed."""
    identifier = None if table_id is None else TableId.parse(table_id)
    return StepTimer(
        "table_command.ended", _LOGGER, command=command, table_id=None if identifier is None else identifier.value
    )


def noted(step: StepTimer, result: CommandResult | None) -> CommandResult | None:
    """Ends the step refused when the command found no table or its result carries a refusal; passes the result on."""
    if result is None:
        step.refuse(CommandNotRun.NO_TABLE)
    elif result.refusal is not None:
        step.refuse(result.refusal.value)
    return result
