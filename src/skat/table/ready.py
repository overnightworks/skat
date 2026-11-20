from dataclasses import dataclass, replace
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from skat.table.game_list import result_view_of
from skat.table.records import CreateTable, Decision, NextSettings, Refusal, TableOptions
from skat.table.rules import create_payload, next_settings_of, seat_of, series_number_of, series_over
from skat.table.series_end import answer_left

if TYPE_CHECKING:
    from datetime import datetime

    from skat.table.records import Actor, Chair, TableRecord

READY_COMMAND: Final = "ready"
NEW_SERIES_COMMAND: Final = "new-series"
NEXT_SETTINGS_COMMAND: Final = "next-series-settings"


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
    """„Neue Serie“ after a series' end; `series` numbers the series it ended, `settings` the revision of the next
    series' settings it answers, and the chair comes from the session.
    """

    command_id: str
    table_id: str
    series: int
    settings: int


def new_series_payload(command: NewSeriesCommand) -> str:
    """The receipt's payload: a retry repeats its series and settings, so „Neue Serie“ for another series or on other
    settings is another request.
    """
    return f"{command.table_id}:{command.series}:{command.settings}"


@dataclass(frozen=True)
class NextSettingsCommand:
    """Save the next series' settings after a series' end: the `length` and rule `options` the page's sheet holds,
    for the series that follows the one numbered `series`; the chair comes from the session.
    """

    command_id: str
    table_id: str
    series: int
    length: int
    options: TableOptions


def next_settings_payload(command: NextSettingsCommand) -> str:
    """The receipt's payload: the table, the series and the settings as the opening of a table writes them, so a retry
    that carries other settings is another request and every pod writes the same text.
    """
    settings = create_payload(CreateTable(command.command_id, command.length, command.options))
    return f"{command.table_id}:{command.series}:{settings}"


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


def decide_new_series(table: TableRecord, actor: Actor, command: NewSeriesCommand, now: datetime) -> Decision:
    """„Neue Serie“ marks the actor's chair: no chair, no series, another series than the table's, a series not yet
    over, then settings other than the next series' current ones. The first mark starts the minute after which the
    seats that stayed silent count as no, and a mark that comes after it is refused, since those seats end the table.

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
    if command.settings != next_settings_of(table).revision:
        return Decision(table, Refusal.STALE_SETTINGS)
    if chair.ready:
        return Decision(table)
    asked_at = table.series.new_series_asked_at
    if asked_at is not None and answer_left(asked_at, now) <= timedelta(0):
        return Decision(table, Refusal.ANSWER_TIME_OVER)
    marked = _marked(table, chair).table
    return Decision(replace(marked, series=replace(table.series, new_series_asked_at=asked_at or now)))


def decide_change_next_settings(
    table: TableRecord, actor: Actor, command: NextSettingsCommand, now: datetime
) -> Decision:
    """A seated member saves the settings the next series is dealt with: no chair, no series, another series than the
    table's, a series not yet over, then a minute of „Neue Serie“ that ran out, since the silent seats end the table.

    The save counts as the settings' next revision and takes back every seat's „Neue Serie“, the saver's too, since
    each was given on the settings before; with no mark standing no minute runs, so the first choice on the new
    settings starts a fresh one.
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
    asked_at = table.series.new_series_asked_at
    if asked_at is not None and answer_left(asked_at, now) <= timedelta(0):
        return Decision(table, Refusal.ANSWER_TIME_OVER)
    saved = NextSettings(command.length, command.options, next_settings_of(table).revision + 1)
    series = replace(table.series, next_settings=saved, new_series_asked_at=None)
    chairs = tuple(replace(each, ready=False) for each in table.chairs)
    return Decision(replace(table, version=table.version + 1, chairs=chairs, series=series))


def _marked(table: TableRecord, chair: Chair) -> Decision:
    if chair.ready:
        return Decision(table)
    chairs = tuple(replace(each, ready=True) if each.seat == chair.seat else each for each in table.chairs)
    return Decision(replace(table, version=table.version + 1, chairs=chairs))
