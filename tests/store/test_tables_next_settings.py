from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update

from skat.store.schema import chairs, options_of, series, tables
from skat.table.ready import NewSeriesCommand, NextSettingsCommand
from skat.table.records import (
    CreateTable,
    NextSettings,
    Refusal,
    Series,
    SitDown,
    StandUp,
    StopPlaying,
    TableId,
    TableOptions,
)
from tests.support.played_game import after_the_first_game
from tests.support.series_store import (
    ALL_THREE,
    FIRST_SERIES_OPTIONS,
    OPENER,
    PEOPLE,
    SECOND_SERIES_OPTIONS,
    THIRD_PLAYER,
    VISITOR,
    race,
    read,
    series_rows,
    tap_all,
)

pytestmark = pytest.mark.postgres


class TestTheNextSeriesSettings:
    """A seat saves what the next series is dealt with at the end of `first_series`, a table of three games opened with
    `FIRST_SERIES_OPTIONS`.
    """

    SAVED = NextSettings(12, SECOND_SERIES_OPTIONS, 1)

    @pytest.fixture
    def first_series(self, service, transactions):
        table_id = service.create(
            OPENER, CreateTable(command_id="command-open", series_length=3, options=FIRST_SERIES_OPTIONS)
        ).id
        service.sit(VISITOR, SitDown("command-visitor", table_id, 2), frozenset())
        service.sit(THIRD_PLAYER, SitDown("command-third", table_id, 3), frozenset())
        record = read(transactions, table_id)
        with transactions.begin() as transaction:
            transaction.save_table(
                replace(after_the_first_game(record), version=record.version + 1, series=Series(3, 3)), played_at=None
            )
        return table_id

    def save(self, service, table_id, *, seat=1, length=12, options=SECOND_SERIES_OPTIONS, name="settings"):
        command = NextSettingsCommand(f"{name}-{seat}", table_id, 1, length, options)
        return service.change_next_settings(PEOPLE[seat], command, ALL_THREE)

    def test_a_save_reads_back_beside_the_series_that_ended_and_changes_that_series_not(
        self, service, transactions, first_series
    ):
        assert self.save(service, first_series).refusal is None

        record = read(transactions, first_series)
        assert record.series.next_settings == self.SAVED
        assert (record.series.length, record.options) == (3, FIRST_SERIES_OPTIONS)

    def test_a_save_is_the_next_series_own_row_which_the_pointer_does_not_name_yet(self, service, engine, first_series):
        self.save(service, first_series)

        first, next_row = series_rows(engine, first_series)
        assert (first.number, first.length, first.deals, options_of(first)) == (1, 3, 3, FIRST_SERIES_OPTIONS)
        assert (next_row.number, next_row.length, next_row.deals, options_of(next_row)) == (
            2,
            12,
            0,
            SECOND_SERIES_OPTIONS,
        )
        with engine.connect() as connection:
            pointer = connection.execute(select(tables.c.series_number).where(tables.c.id == first_series)).scalar_one()
        assert pointer == 1

    def test_a_second_save_replaces_the_first_in_the_same_row(self, service, engine, transactions, first_series):
        self.save(service, first_series, length=12, name="first")

        self.save(service, first_series, seat=2, length=6, options=TableOptions(), name="second")

        assert read(transactions, first_series).series.next_settings == NextSettings(6, TableOptions(), 2)
        assert [row.number for row in series_rows(engine, first_series)] == [1, 2]

    def test_a_save_takes_back_every_new_series_and_the_minute(self, service, transactions, first_series):
        for seat in (1, 2):
            service.start_new_series(PEOPLE[seat], NewSeriesCommand(f"tap-{seat}", first_series, 1, 0), ALL_THREE)

        self.save(service, first_series, seat=3)

        record = read(transactions, first_series)
        assert [chair.ready for chair in record.chairs] == [False, False, False]
        assert record.series.new_series_asked_at is None

    def test_the_last_silent_seat_standing_up_keeps_the_given_marks_and_no_minute_is_left_to_recover(
        self, service, transactions, first_series
    ):
        for seat in (1, 2):
            service.start_new_series(PEOPLE[seat], NewSeriesCommand(f"tap-{seat}", first_series, 1, 0), ALL_THREE)
        assert set(service.pending_end_answers()) == {first_series}

        service.stand(PEOPLE[3], StandUp("stand-third", first_series), ALL_THREE)

        record = read(transactions, first_series)
        assert [chair.ready for chair in record.chairs] == [True, True, False]
        assert record.series.new_series_asked_at is None
        assert service.pending_end_answers() == {}

    def test_the_next_series_is_dealt_with_the_saved_settings_and_its_row_counts_there(
        self, service, transactions, engine, first_series
    ):
        self.save(service, first_series)
        tap_all(service, first_series, settings=1)

        assert service.deal_next(TableId(first_series), nullcontext(ALL_THREE)) is True

        record = read(transactions, first_series)
        assert (record.series, record.options, record.game_list) == (Series(12, 1, number=2), SECOND_SERIES_OPTIONS, ())
        first, second = series_rows(engine, first_series)
        assert (first.length, options_of(first)) == (3, FIRST_SERIES_OPTIONS)
        assert (second.length, second.deals, options_of(second)) == (12, 1, SECOND_SERIES_OPTIONS)

    def test_a_series_dealt_after_a_save_asks_for_no_settings_again(self, service, transactions, first_series):
        self.save(service, first_series)
        tap_all(service, first_series, settings=1)
        service.deal_next(TableId(first_series), nullcontext(ALL_THREE))

        assert read(transactions, first_series).series.next_settings is None

    def test_a_new_series_given_on_older_settings_is_refused_and_a_fresh_one_accepted(
        self, service, transactions, first_series
    ):
        self.save(service, first_series)

        stale = service.start_new_series(OPENER, NewSeriesCommand("tap-stale", first_series, 1, 0), ALL_THREE)
        fresh = service.start_new_series(OPENER, NewSeriesCommand("tap-fresh", first_series, 1, 1), ALL_THREE)

        assert (stale.refusal, fresh.refusal) == (Refusal.STALE_SETTINGS, None)
        assert [chair.ready for chair in read(transactions, first_series).chairs] == [True, False, False]

    def mark_as_the_release_before_does(self, engine, table_id, *, ready=True):
        """That release marks a chair ready, or takes the mark back as a stand-up does, and knows no revision of
        settings: it leaves the column of the revision as it is.
        """
        with engine.begin() as connection:
            connection.execute(update(chairs).where(chairs.c.table_id == table_id).values(ready=ready))

    def test_a_mark_the_release_before_gives_after_taps_on_the_saved_settings_were_taken_back_stands_for_no_choice(
        self, service, transactions, engine, first_series
    ):
        self.save(service, first_series)
        tap_all(service, first_series, settings=1)
        self.mark_as_the_release_before_does(engine, first_series, ready=False)
        self.mark_as_the_release_before_does(engine, first_series, ready=True)

        assert service.deal_next(TableId(first_series), nullcontext(ALL_THREE)) is False

        assert [chair.ready for chair in read(transactions, first_series).chairs] == [False, False, False]

    def test_marks_the_release_before_gives_after_a_save_start_no_minute_that_runs_out_on_the_next_choice(
        self, service, transactions, engine, first_series
    ):
        self.save(service, first_series)
        self.mark_as_the_release_before_does(engine, first_series)
        with engine.begin() as connection:
            connection.execute(
                update(series)
                .where(series.c.table_id == first_series, series.c.number == 1)
                .values(new_series_asked_at=datetime(2020, 1, 1, tzinfo=UTC))
            )

        assert read(transactions, first_series).series.new_series_asked_at is None
        fresh = service.start_new_series(OPENER, NewSeriesCommand("tap-fresh", first_series, 1, 1), ALL_THREE)

        assert fresh.refusal is None

    def test_marks_a_release_before_gives_after_a_save_deal_nothing_and_stand_for_no_choice(
        self, service, transactions, engine, first_series
    ):
        self.save(service, first_series)
        self.mark_as_the_release_before_does(engine, first_series)

        assert service.deal_next(TableId(first_series), nullcontext(ALL_THREE)) is False

        assert [chair.ready for chair in read(transactions, first_series).chairs] == [False, False, False]

    def test_marks_a_release_before_gives_on_unsaved_settings_deal_the_next_series(
        self, service, transactions, engine, first_series
    ):
        self.mark_as_the_release_before_does(engine, first_series)

        assert service.deal_next(TableId(first_series), nullcontext(ALL_THREE)) is True

        assert read(transactions, first_series).series == Series(3, 1, number=2)

    def test_a_tap_on_the_saved_settings_counts_where_a_mark_of_the_release_before_stood(
        self, service, transactions, engine, first_series
    ):
        self.save(service, first_series)
        self.mark_as_the_release_before_does(engine, first_series)

        tap_all(service, first_series, settings=1)

        assert service.deal_next(TableId(first_series), nullcontext(ALL_THREE)) is True
        assert read(transactions, first_series).options == SECOND_SERIES_OPTIONS

    def test_a_save_that_names_another_series_than_the_tables_is_refused(self, service, transactions, first_series):
        command = NextSettingsCommand("settings-late", first_series, 2, 12, SECOND_SERIES_OPTIONS)
        before = read(transactions, first_series)

        answer = service.change_next_settings(OPENER, command, ALL_THREE)

        assert (answer.refusal, read(transactions, first_series)) == (Refusal.STALE_SERIES, before)

    def test_a_save_after_the_table_ended_finds_no_table(self, service, first_series):
        service.stop_playing(OPENER, StopPlaying("stop", first_series))

        assert self.save(service, first_series) is None

    def test_a_retried_save_replays_and_counts_no_second_revision(self, service, transactions, first_series):
        first = self.save(service, first_series)

        again = self.save(service, first_series)

        assert again == first
        assert read(transactions, first_series).series.next_settings == self.SAVED

    def test_two_saves_at_once_are_both_accepted_in_turn_and_the_later_one_stands(
        self, service, transactions, engine, first_series
    ):
        answers = race(
            lambda: self.save(service, first_series, seat=1, length=6, options=TableOptions(), name="one"),
            lambda: self.save(service, first_series, seat=2, length=9, options=SECOND_SERIES_OPTIONS, name="two"),
        )

        saved = read(transactions, first_series).series.next_settings
        assert [answer.refusal for answer in answers.values()] == [None, None]
        assert saved.revision == 2
        assert (saved.length, saved.options) in {(6, TableOptions()), (9, SECOND_SERIES_OPTIONS)}
        assert [row.number for row in series_rows(engine, first_series)] == [1, 2]

    def test_a_save_racing_the_last_new_series_leaves_one_outcome_and_no_series_on_unseen_settings(
        self, service, transactions, first_series
    ):
        for seat in (1, 2):
            service.start_new_series(PEOPLE[seat], NewSeriesCommand(f"tap-{seat}", first_series, 1, 0), ALL_THREE)

        answers = race(
            lambda: self.save(service, first_series, seat=1),
            lambda: service.start_new_series(THIRD_PLAYER, NewSeriesCommand("tap-3", first_series, 1, 0), ALL_THREE),
        )

        assert answers["first"].refusal is None
        assert answers["second"].refusal in {None, Refusal.STALE_SETTINGS}
        assert service.deal_next(TableId(first_series), nullcontext(ALL_THREE)) is False
        record = read(transactions, first_series)
        assert (record.series.number, record.series.next_settings) == (1, self.SAVED)
        assert [chair.ready for chair in record.chairs] == [False, False, False]
