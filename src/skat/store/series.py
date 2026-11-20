"""The `series` rows: one per series of a table, holding the length and options the series started with and its
counters, end proposal, its answers and Bock rounds. Once a series is over, the settings a seat saves for the next one
are that series' own row with no deal yet; its first deal finds the row and counts there.

Every write here happens in a transaction that holds the table's row lock (`_table_record`'s `with_for_update`, taken by
`locked_table`), so a series row needs no lock of its own and a later change that locks several tables keeps taking
the `tables` rows in id order.
"""

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from sqlalchemy import insert, select, update

from skat.engine.bock import BockRounds
from skat.store.game_list import last_series_with_games, read_game_list
from skat.store.schema import option_values, options_of, series
from skat.table.records import EndProposal, NextSettings, PlayedSeries, Series
from skat.table.rules import series_number_of

if TYPE_CHECKING:
    from sqlalchemy import Row, Select
    from sqlalchemy.engine import Connection

    from skat.table.records import TableRecord


class SeriesSettingsChangedError(Exception):
    """A series is saved with a length or options other than its stored row holds: a series keeps the settings it
    started with.
    """


def _counters_of(table: TableRecord) -> dict[str, object]:
    """The columns that change while the series is played: its deals, early end, standing proposal, the minute of its
    „Neue Serie“ and Bock rounds.
    """
    current = table.series
    proposal = None if current is None else current.end_proposal
    return {
        "deals": None if current is None else current.deals,
        "ended_early": current is not None and current.ended_early,
        "end_proposer": None if proposal is None else proposal.proposer,
        "end_accepter": None if proposal is None else _accepter_of(proposal),
        "end_agreed": [] if proposal is None else sorted(proposal.agreed),
        "end_asked_at": None if proposal is None else proposal.asked_at,
        "end_refused_by": [] if current is None else sorted(current.end_refused_by),
        "new_series_asked_at": None if current is None else current.new_series_asked_at,
        "bock_rounds": list(table.bock.remaining),
        "ramsch_round_games": table.bock.ramsch_games,
    }


def _accepter_of(proposal: EndProposal) -> int | None:
    """The one seat besides the proposer that said yes, as the release before stores it; every seat saying yes ends the
    series, so no proposal holds two.
    """
    return next(iter(proposal.agreed - {proposal.proposer}), None)


def _length_of(table: TableRecord) -> int | None:
    return None if table.series is None else table.series.length


def _series_query(table_id: str, number: int) -> Select[Any]:
    return select(series).where(series.c.table_id == table_id, series.c.number == number)


def insert_series(connection: Connection, table: TableRecord) -> None:
    """The row of the series the record is in, with the settings and counters the record holds."""
    connection.execute(
        insert(series).values(
            table_id=table.id.value,
            number=series_number_of(table),
            length=_length_of(table),
            **option_values(table.options),
            **_counters_of(table),
        )
    )


def save_series(connection: Connection, table: TableRecord) -> None:
    """Write the counters of the record's series; the first save of a series adds its row with the record's
    settings, and a record whose settings differ from the stored row raises.
    """
    number = series_number_of(table)
    stored = connection.execute(_series_query(table.id.value, number)).one_or_none()
    if stored is None:
        insert_series(connection, table)
    elif stored.length != _length_of(table) or options_of(stored) != table.options:
        message = f"series {number} of table {table.id.value} is saved with settings other than it started with"
        raise SeriesSettingsChangedError(message)
    else:
        connection.execute(
            update(series)
            .where(series.c.table_id == table.id.value, series.c.number == number)
            .values(**_counters_of(table))
        )
    _save_next_settings(connection, table)


def _save_next_settings(connection: Connection, table: TableRecord) -> None:
    """The row of the series after the record's, which holds the settings a seat saved for it; a save after another
    rewrites that row, and the first deal of the series finds it and counts there.
    """
    saved = None if table.series is None else table.series.next_settings
    if saved is None:
        return
    number = series_number_of(table) + 1
    values = {"length": saved.length, "settings_revision": saved.revision, **option_values(saved.options)}
    if connection.execute(_series_query(table.id.value, number)).one_or_none() is None:
        connection.execute(insert(series).values(table_id=table.id.value, number=number, deals=0, **values))
    else:
        connection.execute(
            update(series).where(series.c.table_id == table.id.value, series.c.number == number).values(**values)
        )


def series_row(connection: Connection, table_id: str, number: int) -> Row[Any]:
    """The row of the table's series `number`; a pointer without a row is a fault, so a missing row raises."""
    return connection.execute(_series_query(table_id, number)).one()


def series_of(row: Row[Any]) -> Series | None:
    """The series a row holds, None for the row of a table with no series."""
    if row.length is None:
        return None
    proposal = _proposal_of(row)
    return Series(
        row.length,
        row.deals,
        number=row.number,
        ended_early=row.ended_early,
        end_proposal=proposal,
        end_refused_by=frozenset(row.end_refused_by),
        new_series_asked_at=row.new_series_asked_at,
    )


def series_with_next_settings(connection: Connection, table_id: str, row: Row[Any]) -> Series | None:
    """The series a row holds with the settings saved for the next one, which only a series that is over can hold."""
    current = series_of(row)
    if current is None or not current.is_over:
        return current
    saved = connection.execute(_series_query(table_id, current.number + 1)).one_or_none()
    if saved is None:
        return current
    return replace(current, next_settings=NextSettings(saved.length, options_of(saved), saved.settings_revision))


def _proposal_of(row: Row[Any]) -> EndProposal | None:
    if row.end_proposer is None:
        return None
    return EndProposal(row.end_proposer, frozenset(row.end_agreed), row.end_asked_at)


def bock_of(row: Row[Any]) -> BockRounds:
    return BockRounds(tuple(row.bock_rounds), row.ramsch_round_games)


def last_played_series(connection: Connection, table_id: str) -> PlayedSeries | None:
    """The highest series of the table that has games, read with its own options; None if no game was finished."""
    number = last_series_with_games(connection, table_id)
    if number is None:
        return None
    return PlayedSeries(
        number, options_of(series_row(connection, table_id, number)), read_game_list(connection, table_id, number)
    )
