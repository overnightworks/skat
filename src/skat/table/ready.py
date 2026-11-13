from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.table.game_list import result_view_of
from skat.table.records import Decision, Refusal
from skat.table.rules import seat_of, series_number_of, series_over

if TYPE_CHECKING:
    from skat.table.records import Actor, Chair, TableRecord

READY_COMMAND: Final = "ready"
NEW_SERIES_COMMAND: Final = "new-series"


@dataclass(frozen=True)
class ReadyCommand:
    """„Weiter“ after a result; `ordinal` numbers the result the page saw and `series` the series it belongs to, and the
    chair comes from the session.
    """

    command_id: str
    table_id: str
    ordinal: int
    series: int


def ready_payload(command: ReadyCommand) -> str:
    """The receipt's payload: a retry repeats its series and ordinal, so „Weiter“ for another result or series is
    another request.
    """
    return f"{command.table_id}:{command.series}:{command.ordinal}"


@dataclass(frozen=True)
class NewSeriesCommand:
    """„Neue Serie“ after a series' end; `series` numbers the series it ended, and the chair comes from the session."""

    command_id: str
    table_id: str
    series: int


def new_series_payload(command: NewSeriesCommand) -> str:
    """The receipt's payload: a retry repeats its series, so „Neue Serie“ for another series is another request."""
    return f"{command.table_id}:{command.series}"


def decide_ready(table: TableRecord, actor: Actor, command: ReadyCommand) -> Decision:
    """„Weiter“ marks the actor's chair: no chair, no pending result, another series than the table's, another result
    than the pending one, then no game left in the series.

    A chair already ready stays as it is, with no new version, so a tap from a second tab is no error.
    """
    chair = seat_of(table, actor.account_id)
    if chair is None:
        return Decision(table, Refusal.NOT_SEATED)
    result = result_view_of(table)
    if result is None:
        return Decision(table, Refusal.NO_RESULT)
    if command.series != series_number_of(table):
        return Decision(table, Refusal.STALE_SERIES)
    if command.ordinal != result.ordinal:
        return Decision(table, Refusal.STALE_RESULT)
    if series_over(table):
        return Decision(table, Refusal.SERIES_OVER)
    return _marked(table, chair)


def decide_new_series(table: TableRecord, actor: Actor, command: NewSeriesCommand) -> Decision:
    """„Neue Serie“ marks the actor's chair: no chair, no series, another series than the table's, a series not yet
    over.

    A chair already marked stays as it is, with no new version; the deal after the third mark starts the next series.
    """
    chair = seat_of(table, actor.account_id)
    if chair is None:
        return Decision(table, Refusal.NOT_SEATED)
    if table.series is None:
        return Decision(table, Refusal.NO_SERIES)
    if command.series != series_number_of(table):
        return Decision(table, Refusal.STALE_SERIES)
    if not series_over(table):
        return Decision(table, Refusal.SERIES_NOT_OVER)
    return _marked(table, chair)


def _marked(table: TableRecord, chair: Chair) -> Decision:
    if chair.ready:
        return Decision(table)
    chairs = tuple(replace(each, ready=True) if each.seat == chair.seat else each for each in table.chairs)
    return Decision(replace(table, version=table.version + 1, chairs=chairs))
