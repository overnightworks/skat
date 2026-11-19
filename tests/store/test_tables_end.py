import threading
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from skat.engine.deal import Position, positions_from
from skat.store.schema import tables
from skat.table.playing import PlayCardCommand
from skat.table.ready import NewSeriesCommand
from skat.table.records import (
    CreateTable,
    EndedTable,
    Ending,
    EndReason,
    GiveUpAsked,
    HandProgress,
    OccupantKind,
    Series,
    StopPlaying,
    TableRecord,
)
from skat.table.rules import CREATE_TABLE_COMMAND
from skat.table.series_end import END_ANSWER_SECONDS
from skat.table.service import TableService
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.support.faulty_tables import HANG_DEADLINE_SECONDS, FaultyTableTransactions
from tests.support.played_game import (
    a_whole_game,
    after_the_first_game,
    before_the_last_card,
    declared_herz_hand,
    with_agents,
)
from tests.support.seated_tables import (
    NOBODY_CONNECTED,
    OPENER,
    SEATED,
    ended_at,
    listed_game,
    save,
    seated_table,
    undealt_table,
)
from tests.support.table_rows import WorkInAThread, rows_of, wait_until_a_session_waits_for_a_lock

pytestmark = pytest.mark.postgres

HAND_TABLES = ("hand_cards", "auction_actions", "declaring_steps", "played_cards")


def played_hand(service, transactions, stored, name):
    """A seated table whose middlehand declared a Herz Hand game, with every card played but the last."""
    table_id = seated_table(service, name)
    running, _ = before_the_last_card(stored(transactions, table_id.value))
    save(transactions, running)
    return table_id


def listed_games_in_two_series(service, transactions, stored, name):
    """A seated table with a finished game in its first series and another in its second, the current one."""
    table_id = seated_table(service, name, series_length=12)
    first_game = after_the_first_game(stored(transactions, table_id.value))
    second_series = replace(first_game.series, number=2)
    save(transactions, first_game)
    save(transactions, replace(first_game, series=second_series, game_list=()))
    save(transactions, replace(first_game, series=second_series))
    return table_id


def end(service, table_id):
    return service.end_empty_table(table_id, nullcontext(NOBODY_CONNECTED), DEFAULT_EMPTY_TABLE_SECONDS)


def end_at_the_store(transactions, table_id):
    with transactions.begin() as transaction:
        assert transaction.locked_table(table_id) is not None
        transaction.end_table(
            table_id, datetime(2026, 11, 9, 12, 0, tzinfo=UTC), Ending.empty(DEFAULT_EMPTY_TABLE_SECONDS)
        )


def test_the_end_step_deletes_the_chairs_holds_hand_and_steps_of_a_running_hand_and_keeps_the_row(
    service, transactions, stored, engine
):
    table_id = played_hand(service, transactions, stored, "one")
    service.note_leave(table_id, SEATED[1].account_id, hold_seconds=300, newest_wins=True)
    before = rows_of(engine, table_id.value)
    assert all(before[name] for name in ("chairs", "chair_holds", *HAND_TABLES))

    end_at_the_store(transactions, table_id)

    after = rows_of(engine, table_id.value)
    kept = {name for name, rows in after.items() if rows}
    assert kept == {"tables", "series", "receipts"}
    assert len(after["tables"]) == 1


@pytest.mark.parametrize("make", [played_hand, listed_game], ids=["running-hand", "game-list"])
def test_a_dealt_table_nobody_is_connected_to_is_kept_with_every_row(make, service, transactions, stored, engine):
    table_id = make(service, transactions, stored, "one")
    before = rows_of(engine, table_id.value)
    version = stored(transactions, table_id.value).version

    assert end(service, table_id) is False

    assert rows_of(engine, table_id.value) == before
    assert stored(transactions, table_id.value).version == version


def test_an_end_whose_store_fails_after_it_writes_leaves_the_table_live_with_all_its_rows(
    service, transactions, stored, engine
):
    table_id = undealt_table(service, "one")
    before = rows_of(engine, table_id.value)
    failing = TableService(FaultyTableTransactions(transactions, end_failure=ConnectionError("lost")))
    nobody_connected = nullcontext(NOBODY_CONNECTED)

    with pytest.raises(ConnectionError):
        failing.end_empty_table(table_id, nobody_connected, DEFAULT_EMPTY_TABLE_SECONDS)

    assert rows_of(engine, table_id.value) == before
    assert isinstance(stored(transactions, table_id.value), TableRecord)


def test_the_end_step_keeps_the_game_list(service, transactions, stored, engine):
    table_id = listed_game(service, transactions, stored, "one")
    before = rows_of(engine, table_id.value)["game_list"]
    assert before

    end_at_the_store(transactions, table_id)

    assert rows_of(engine, table_id.value)["game_list"] == before


def test_ending_a_table_keeps_its_create_receipt_and_deletes_every_other_receipt_of_it(
    service, transactions, stored, engine
):
    table_id = undealt_table(service, "one")
    assert len(rows_of(engine, table_id.value)["receipts"]) == 2

    end(service, table_id)

    assert [row[:3] for row in rows_of(engine, table_id.value)["receipts"]] == [
        (OPENER.account_id, "open-one", CREATE_TABLE_COMMAND)
    ]


def test_ending_one_table_changes_no_row_of_another_table_of_the_same_opener_or_of_its_receipts(
    service, transactions, stored, engine
):
    ended = undealt_table(service, "one")
    kept = played_hand(service, transactions, stored, "two")
    other = listed_game(service, transactions, stored, "three")
    kept_before = rows_of(engine, kept.value)
    other_before = rows_of(engine, other.value)

    assert end(service, ended) is True

    assert rows_of(engine, kept.value) == kept_before
    assert rows_of(engine, other.value) == other_before


def test_the_end_stores_the_time_the_reason_and_the_wait_and_bumps_the_version_once(transactions, stored, engine):
    at = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    service = TableService(transactions, now=lambda: at)
    table_id = undealt_table(service, "one")
    version = stored(transactions, table_id.value).version

    service.end_empty_table(table_id, nullcontext(NOBODY_CONNECTED), 42)

    with engine.connect() as connection:
        row = connection.execute(
            select(tables.c.ended_at, tables.c.end_reason, tables.c.empty_seconds, tables.c.dealer).where(
                tables.c.id == table_id.value
            )
        ).one()
    assert tuple(row) == (at, EndReason.EMPTY.value, 42, None)
    assert stored(transactions, table_id.value) == EndedTable(table_id, version + 1, Ending.empty(42))


def test_a_read_that_meets_an_end_in_flight_waits_for_its_commit_and_sees_the_ended_table(
    service, transactions, engine
):
    table_id = undealt_table(service, "one")

    with transactions.begin() as ending:
        ending.end_table(table_id, datetime(2026, 11, 9, 12, 0, tzinfo=UTC), Ending.empty(DEFAULT_EMPTY_TABLE_SECONDS))
        views = []
        reading = threading.Thread(target=lambda: views.append(service.view(OPENER, table_id.value, NOBODY_CONNECTED)))
        reading.start()
        wait_until_a_session_waits_for_a_lock(engine, reading)

    reading.join()
    assert views[0].ended.reason == EndReason.EMPTY


def test_an_ended_table_reads_as_a_tombstone_and_is_no_live_table_and_no_chair_is_occupied(
    service, transactions, stored
):
    ended = undealt_table(service, "one")
    live = seated_table(service, "two")

    end(service, ended)

    with transactions.begin() as transaction:
        assert transaction.locked_table(ended) is None
        assert isinstance(transaction.locked_table(live), TableRecord)
        seated = frozenset(actor.account_id for actor in SEATED)
        assert {chair.table_id for chair in transaction.chairs_taken_by([ended, live], seated)} == {live}
    with transactions.begin() as transaction:
        assert [wait.table_id for wait in transaction.live_empty_since()] == [live]
    assert isinstance(stored(transactions, ended.value), EndedTable)


def test_the_start_locks_the_live_tables_in_id_order_as_every_other_step_that_locks_several_does(service, transactions):
    opened = [undealt_table(service, str(number)) for number in range(8)]

    with transactions.begin() as transaction:
        assert [wait.table_id for wait in transaction.live_empty_since()] == sorted(opened, key=lambda each: each.value)


def test_a_create_retry_under_an_ended_tables_command_id_returns_it_and_makes_no_table(service, transactions, engine):
    ended = undealt_table(service, "one")
    end(service, ended)

    again = service.create(OPENER, CreateTable(command_id="open-one"))

    assert again.id == ended.value
    assert again.ended.reason == EndReason.EMPTY
    with engine.connect() as connection:
        assert connection.execute(select(tables.c.id)).all() == [(ended.value,)]


def test_an_ended_tables_id_is_never_issued_again(service, transactions):
    ended = undealt_table(service, "one")
    end(service, ended)
    reusing = TableService(transactions, new_table_id=lambda: ended)
    command = CreateTable(command_id="open-new")

    with pytest.raises(IntegrityError):
        reusing.create(OPENER, command)


def test_the_end_enters_the_presence_once_the_row_is_locked_and_leaves_it_after_the_commit(service, engine):
    table_id = undealt_table(service, "one")
    seen = {}
    lock_attempt = select(tables.c.id).where(tables.c.id == table_id.value).with_for_update(nowait=True)

    @contextmanager
    def presence():
        with engine.connect() as other, pytest.raises(OperationalError):
            other.execute(lock_attempt)
        yield NOBODY_CONNECTED
        with engine.connect() as other:
            ended_at = select(tables.c.ended_at).where(tables.c.id == table_id.value)
            seen["ended_at"] = other.execute(ended_at).scalar_one()

    assert service.end_empty_table(table_id, presence(), DEFAULT_EMPTY_TABLE_SECONDS) is True

    assert seen["ended_at"] is not None


SOMEBODY_CONNECTED = frozenset({OPENER.account_id})


def stored_since(engine, table_id):
    with engine.connect() as connection:
        return connection.execute(select(tables.c.empty_since).where(tables.c.id == table_id.value)).scalar_one()


def set_since(engine, table_id, since):
    with engine.begin() as connection:
        connection.execute(update(tables).where(tables.c.id == table_id.value).values(empty_since=since))


def note(service, table_id, connected):
    return service.note_presence(table_id, nullcontext(connected), DEFAULT_EMPTY_TABLE_SECONDS)


def test_a_created_table_stores_its_creation_as_the_time_since_nobody_was_there(service, engine):
    before = datetime.now(UTC)

    table_id = undealt_table(service, "one")

    assert before <= stored_since(engine, table_id) <= datetime.now(UTC)


def test_the_sit_that_deals_the_first_hand_clears_the_time_with_no_stream_open(service, engine):
    table_id = seated_table(service, "one")

    assert stored_since(engine, table_id) is None


def test_a_leave_and_an_arrival_write_and_clear_the_time_and_change_no_version_or_receipt(
    service, transactions, stored, engine
):
    table_id = undealt_table(service, "one")
    before = stored(transactions, table_id.value)
    receipts = rows_of(engine, table_id.value)["receipts"]

    note(service, table_id, SOMEBODY_CONNECTED)
    cleared = stored_since(engine, table_id)
    note(service, table_id, NOBODY_CONNECTED)
    stamped = stored_since(engine, table_id)

    assert (cleared, stamped is not None) == (None, True)
    assert stored(transactions, table_id.value) == before
    assert rows_of(engine, table_id.value)["receipts"] == receipts


def test_an_arrival_after_the_wait_ends_the_table_and_a_dealt_table_keeps_no_time(
    service, transactions, stored, engine
):
    overdue = undealt_table(service, "one")
    dealt = seated_table(service, "two")
    set_since(engine, overdue, datetime.now(UTC) - timedelta(seconds=DEFAULT_EMPTY_TABLE_SECONDS))
    set_since(engine, dealt, None)

    assert note(service, overdue, SOMEBODY_CONNECTED) is True
    assert note(service, dealt, NOBODY_CONNECTED) is False

    assert isinstance(stored(transactions, overdue.value), EndedTable)
    assert stored_since(engine, dealt) is None


def test_the_note_enters_the_presence_once_the_row_is_locked_so_a_rival_leave_or_arrival_waits(service, engine):
    table_id = undealt_table(service, "one")
    lock_attempt = select(tables.c.id).where(tables.c.id == table_id.value).with_for_update(nowait=True)

    @contextmanager
    def presence():
        with engine.connect() as other, pytest.raises(OperationalError):
            other.execute(lock_attempt)
        yield NOBODY_CONNECTED

    note_inside = service.note_presence(table_id, presence(), DEFAULT_EMPTY_TABLE_SECONDS)

    assert (note_inside, stored_since(engine, table_id) is not None) == (False, True)


def test_the_start_stamps_a_table_with_no_time_ends_one_past_its_wait_and_leaves_the_rest_their_time_left(
    service, transactions, stored, engine
):
    unset, overdue, recent = (undealt_table(service, name) for name in ("one", "two", "three"))
    set_since(engine, unset, None)
    set_since(engine, overdue, datetime.now(UTC) - timedelta(seconds=DEFAULT_EMPTY_TABLE_SECONDS + 1))
    set_since(engine, recent, datetime.now(UTC) - timedelta(seconds=60))

    left = service.resume_empty_waits(DEFAULT_EMPTY_TABLE_SECONDS)

    assert left.keys() == {unset.value, recent.value}
    assert left[unset.value] == pytest.approx(DEFAULT_EMPTY_TABLE_SECONDS, abs=5)
    assert left[recent.value] == pytest.approx(DEFAULT_EMPTY_TABLE_SECONDS - 60, abs=5)
    assert stored_since(engine, unset) is not None
    assert isinstance(stored(transactions, overdue.value), EndedTable)


def test_the_start_leaves_a_dealt_table_with_no_time_unstamped_and_unwaited(service, engine):
    dealt = seated_table(service, "one")
    set_since(engine, dealt, None)

    left = service.resume_empty_waits(DEFAULT_EMPTY_TABLE_SECONDS)

    assert (left, stored_since(engine, dealt)) == ({}, None)


UNPLAYED_DAYS = 90
PLAYED_AT = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
UNPLAYED_AT = PLAYED_AT + timedelta(days=UNPLAYED_DAYS)


def unplayed_service(transactions, now=UNPLAYED_AT):
    return TableService(transactions, now=lambda: now)


def played_at(transactions, table_id, when):
    with transactions.begin() as transaction:
        transaction.save_table(transaction.table(table_id), played_at=when)


def test_the_unplayed_end_keeps_the_game_list_and_every_other_row_goes_and_stores_the_days(
    service, transactions, stored, engine
):
    table_id = listed_games_in_two_series(service, transactions, stored, "one")
    played_at(transactions, table_id, PLAYED_AT)
    games = rows_of(engine, table_id.value)["game_list"]
    version = stored(transactions, table_id.value).version
    assert {row[1] for row in games} == {1, 2}

    assert (
        unplayed_service(transactions).end_unplayed_table(table_id, UNPLAYED_DAYS, nullcontext(NOBODY_CONNECTED))
        is True
    )

    after = rows_of(engine, table_id.value)
    assert {name for name, rows in after.items() if rows} == {"tables", "series", "receipts", "game_list"}
    assert after["game_list"] == games
    assert [row[2] for row in after["receipts"]] == [CREATE_TABLE_COMMAND]
    with engine.connect() as connection:
        row = connection.execute(
            select(
                tables.c.ended_at,
                tables.c.end_reason,
                tables.c.empty_seconds,
                tables.c.unplayed_days,
                tables.c.dealer,
                tables.c.last_played_at,
                tables.c.opener_name,
            ).where(tables.c.id == table_id.value)
        ).one()
    assert tuple(row) == (UNPLAYED_AT, EndReason.UNPLAYED.value, None, UNPLAYED_DAYS, None, None, None)
    assert replace(stored(transactions, table_id.value), last_series=None) == EndedTable(
        table_id, version + 1, Ending.unplayed(UNPLAYED_DAYS)
    )


STOPPED_AT = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


def at_the_series_end(transactions, stored, table_id):
    """The table after its current series' last game: no hand, a game on the list and no game left to deal."""
    record = stored(transactions, table_id.value)
    save(transactions, replace(record, hand=None, progress=HandProgress(), series=Series(12, 12, number=2)))


def stop(service, actor, table_id, command_id="stop-one"):
    return service.stop_playing(actor, StopPlaying(command_id, table_id.value))


def test_the_stop_keeps_the_game_list_and_the_create_and_stop_receipts_and_names_nobody(
    service, transactions, stored, engine
):
    table_id = listed_games_in_two_series(service, transactions, stored, "one")
    at_the_series_end(transactions, stored, table_id)
    games = rows_of(engine, table_id.value)["game_list"]
    version = stored(transactions, table_id.value).version

    result = stop(TableService(transactions, now=lambda: STOPPED_AT), SEATED[1], table_id)

    assert result.refusal is None
    after = rows_of(engine, table_id.value)
    assert {name for name, rows in after.items() if rows} == {"tables", "series", "receipts", "game_list"}
    assert after["game_list"] == games
    assert sorted(row[:3] for row in after["receipts"]) == sorted(
        [
            (SEATED[1].account_id, "stop-one", "stop-playing"),
            (OPENER.account_id, "open-one", CREATE_TABLE_COMMAND),
        ]
    )
    with engine.connect() as connection:
        row = connection.execute(
            select(tables.c.ended_at, tables.c.end_reason, tables.c.closed_by_name, tables.c.opener_name).where(
                tables.c.id == table_id.value
            )
        ).one()
    assert tuple(row) == (STOPPED_AT, EndReason.STOPPED.value, None, None)
    assert replace(stored(transactions, table_id.value), last_series=None) == EndedTable(
        table_id, version + 1, Ending.stopped()
    )


def test_a_stop_retry_after_the_commit_answers_the_ended_table_and_a_refusal_writes_no_receipt(
    service, transactions, stored, engine
):
    table_id = listed_games_in_two_series(service, transactions, stored, "one")
    refused = stop(service, SEATED[1], table_id, "stop-early")
    assert refused.refusal is not None
    receipts_before = len(rows_of(engine, table_id.value)["receipts"])
    assert receipts_before == len(SEATED)
    at_the_series_end(transactions, stored, table_id)

    stop(service, OPENER, table_id)
    again = stop(service, OPENER, table_id)

    assert again.view.ended.reason is EndReason.STOPPED
    assert len(rows_of(engine, table_id.value)["receipts"]) == 2


def test_a_lapse_that_stops_the_table_ends_it_and_a_second_lapse_changes_nothing(service, transactions, stored, engine):
    table_id = listed_games_in_two_series(service, transactions, stored, "one")
    record = stored(transactions, table_id.value)
    chairs = (replace(record.chairs[0], ready=True), *record.chairs[1:])
    save(
        transactions,
        replace(
            record,
            hand=None,
            progress=HandProgress(),
            chairs=chairs,
            series=Series(12, 12, number=2, new_series_asked_at=STOPPED_AT),
        ),
    )
    later = TableService(transactions, now=lambda: STOPPED_AT + timedelta(seconds=END_ANSWER_SECONDS))

    first, second = later.lapse_end_answers(table_id), later.lapse_end_answers(table_id)

    assert (first.table_stopped, second.table_stopped) == (True, False)
    assert stored(transactions, table_id.value).ending == Ending.stopped()


def test_an_ask_for_new_series_is_found_with_its_instant_by_the_start_of_a_server(
    service, transactions, stored, engine
):
    table_id = listed_games_in_two_series(service, transactions, stored, "one")
    record = stored(transactions, table_id.value)
    save(
        transactions,
        replace(
            record, hand=None, progress=HandProgress(), series=Series(12, 12, number=2, new_series_asked_at=STOPPED_AT)
        ),
    )

    left = TableService(transactions, now=lambda: STOPPED_AT + timedelta(seconds=20)).pending_end_answers()

    assert left == {table_id.value: END_ANSWER_SECONDS - 20}


class SeriesEndRace:
    """A table at its series' end whose seats 1 and 2 chose „Neue Serie“ and whose third seat answers at the same
    moment as an end: the end holds the row lock, the answer waits for it, and `settle` lets the end commit.
    """

    def __init__(self, service, transactions, engine, stored):
        self.engine = engine
        self.transactions = transactions
        self.table_id = listed_games_in_two_series(service, transactions, stored, "one")
        record = stored(transactions, self.table_id.value)
        ready = tuple(replace(chair, ready=chair.seat < 3) for chair in record.chairs)
        series_over = Series(12, 12, number=2, new_series_asked_at=STOPPED_AT)
        save(transactions, replace(record, hand=None, progress=HandProgress(), chairs=ready, series=series_over))
        self.stored = lambda: stored(transactions, self.table_id.value)
        self.hold = HeldWrite()

    def holding(self):
        return HoldingAfterSave(self.transactions, self.hold)

    def third_seats_new_series(self):
        command = NewSeriesCommand("new-series-3", self.table_id.value, 2)
        service = TableService(self.transactions, now=lambda: STOPPED_AT)
        return WorkInAThread(lambda: service.start_new_series(SEATED[2], command, NOBODY_CONNECTED))

    def settle(self, ending, answer):
        ending.start()
        assert self.hold.entered.wait(HANG_DEADLINE_SECONDS)
        answer.start()
        wait_until_a_session_waits_for_a_lock(self.engine, answer)
        self.hold.release.set()
        ending.join()
        answer.join()
        return ending.outcome, answer.outcome


@pytest.fixture
def series_end_race(service, transactions, engine, stored):
    return SeriesEndRace(service, transactions, engine, stored)


def test_a_new_series_answer_that_waits_for_a_stop_finds_the_ended_table_and_deals_nothing(series_end_race):
    race = series_end_race
    service = TableService(race.holding(), now=lambda: STOPPED_AT)

    stopped, answered = race.settle(
        WorkInAThread(lambda: service.stop_playing(SEATED[0], StopPlaying("stop-one", race.table_id.value))),
        race.third_seats_new_series(),
    )

    assert [result.refusal for result in stopped] == [None]
    assert answered == [None]
    assert race.stored().ending == Ending.stopped()


def test_a_new_series_answer_that_waits_for_the_lapse_of_another_pod_finds_the_table_ended_by_it(series_end_race):
    race = series_end_race
    later = TableService(race.holding(), now=lambda: STOPPED_AT + timedelta(seconds=END_ANSWER_SECONDS))

    lapsed, answered = race.settle(
        WorkInAThread(lambda: later.lapse_end_answers(race.table_id)), race.third_seats_new_series()
    )

    assert [lapse.table_stopped for lapse in lapsed] == [True]
    assert answered == [None]
    assert race.stored().ending == Ending.stopped()


def test_the_unplayed_end_deletes_the_rows_of_a_running_hand(service, transactions, stored, engine):
    table_id = played_hand(service, transactions, stored, "one")
    played_at(transactions, table_id, PLAYED_AT)

    unplayed_service(transactions).end_unplayed_table(table_id, UNPLAYED_DAYS, nullcontext(NOBODY_CONNECTED))

    after = rows_of(engine, table_id.value)
    assert {name for name, rows in after.items() if rows} == {"tables", "series", "receipts"}


def test_the_unplayed_end_clears_an_outstanding_give_up_request(service, transactions, stored, engine):
    table_id = played_hand(service, transactions, stored, "one")
    running = stored(transactions, table_id.value)
    save(
        transactions,
        replace(
            running, progress=replace(running.progress, give_up=GiveUpAsked(Position.MIDDLEHAND, Position.FOREHAND))
        ),
    )
    played_at(transactions, table_id, PLAYED_AT)

    unplayed_service(transactions).end_unplayed_table(table_id, UNPLAYED_DAYS, nullcontext(NOBODY_CONNECTED))

    with engine.connect() as connection:
        row = connection.execute(
            select(tables.c.give_up_asked_by, tables.c.give_up_declined_by).where(tables.c.id == table_id.value)
        ).one()
    assert tuple(row) == (None, None)


def test_a_table_played_at_after_the_unplayed_read_is_not_ended_by_it(service, transactions, stored):
    table_id = seated_table(service, "one")
    played_at(transactions, table_id, PLAYED_AT)
    candidates = unplayed_service(transactions).unplayed_tables(UNPLAYED_DAYS)
    played_at(transactions, table_id, UNPLAYED_AT)

    assert candidates == (table_id,)
    assert (
        unplayed_service(transactions).end_unplayed_table(table_id, UNPLAYED_DAYS, nullcontext(NOBODY_CONNECTED))
        is False
    )
    assert isinstance(stored(transactions, table_id.value), TableRecord)


def test_the_unplayed_read_lists_only_live_dealt_tables_played_at_or_before_the_line_in_id_order(service, transactions):
    old = seated_table(service, "old")
    played_at(transactions, old, PLAYED_AT)
    recent = seated_table(service, "recent")
    played_at(transactions, recent, PLAYED_AT + timedelta(seconds=1))
    undealt_table(service, "undealt")
    ended = seated_table(service, "ended")
    played_at(transactions, ended, PLAYED_AT)
    end_at_the_store(transactions, ended)

    assert unplayed_service(transactions).unplayed_tables(UNPLAYED_DAYS) == (old,)


class HeldWrite:
    """A write guard that waits in its worker until released, so the transaction that entered it keeps the row lock."""

    def __init__(self, connected=NOBODY_CONNECTED):
        self._connected = connected
        self.entered = threading.Event()
        self.release = threading.Event()

    def __enter__(self):
        self.entered.set()
        assert self.release.wait(HANG_DEADLINE_SECONDS)
        return self._connected

    def __exit__(self, *_):
        return None


class HoldingAfterSave:
    """A transactions port whose saves wait in their worker until `hold` is released, so the command that saved keeps
    the row lock it took.
    """

    def __init__(self, inner, hold):
        self._inner = inner
        self._hold = hold

    @contextmanager
    def begin(self):
        with self._inner.begin() as transaction:
            yield _HoldingTransaction(transaction, self._hold)


class _HoldingTransaction:
    def __init__(self, inner, hold):
        self._inner = inner
        self._hold = hold

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def save_table(self, table, *, played_at):
        self._inner.save_table(table, played_at=played_at)
        with self._hold:
            pass

    def end_table(self, table_id, ended_at, ending):
        self._inner.end_table(table_id, ended_at, ending)
        with self._hold:
            pass


class Rivals:
    """A table with a hand running and a game listed, past its days, that two writes reach at once: the first holds the
    row lock, the second waits for it, and `settle` lets the first commit and returns both outcomes in that order.
    """

    def __init__(self, service, transactions, engine, stored):
        self.engine = engine
        self.transactions = transactions
        self.service = unplayed_service(transactions)
        self.table_id = seated_table(service, "one")
        seated = stored(transactions, self.table_id.value)
        declared = replace(seated, progress=declared_herz_hand())
        plays = a_whole_game(declared)
        running = replace(declared, progress=replace(declared.progress, plays=plays[:3]))
        save(transactions, replace(running, game_list=after_the_first_game(seated).game_list))
        played_at(transactions, self.table_id, PLAYED_AT)
        self.everyone = frozenset(chair.account_id for chair in SEATED)
        self.first_hold = HeldWrite(self.everyone)
        self.stored = lambda: stored(transactions, self.table_id.value)
        self.next_card = plays[3].card
        seats = {position: seat for seat, position in positions_from(running.dealer).items()}
        self.card_player = SEATED[seats[plays[3].position] - 1]

    def expire(self, writing=None):
        return WorkInAThread(
            lambda: self.service.end_unplayed_table(self.table_id, UNPLAYED_DAYS, writing or nullcontext(frozenset()))
        )

    def play(self, holding=None):
        """The next card of the running hand, played by its player through the card command; with `holding`, the
        command keeps the row lock until that hold is released.
        """
        transactions = self.transactions if holding is None else HoldingAfterSave(self.transactions, holding)
        command = PlayCardCommand("card-rival", self.table_id.value, self.stored().version, self.next_card)
        return WorkInAThread(lambda: unplayed_service(transactions).play_card(self.card_player, command, self.everyone))

    def settle(self, first, second):
        first.start()
        assert self.first_hold.entered.wait(HANG_DEADLINE_SECONDS)
        second.start()
        wait_until_a_session_waits_for_a_lock(self.engine, second)
        self.first_hold.release.set()
        first.join()
        second.join()
        return first.outcome, second.outcome


@pytest.fixture
def rivals(service, transactions, engine, stored):
    return Rivals(service, transactions, engine, stored)


def test_a_table_played_while_its_expiry_waits_for_the_row_is_not_ended_by_it(rivals):
    played, expired = rivals.settle(rivals.play(rivals.first_hold), rivals.expire())

    assert [result.refusal for result in played] == [None]
    assert expired == [False]
    assert isinstance(rivals.stored(), TableRecord)
    assert len(rivals.stored().progress.plays) == 4


def test_a_play_that_meets_the_expiry_holding_the_row_finds_the_table_ended_and_plays_nothing(rivals):
    version = rivals.stored().version
    expired, played = rivals.settle(rivals.expire(rivals.first_hold), rivals.play())

    assert (expired, played) == ([True], [None])
    assert replace(rivals.stored(), last_series=None) == EndedTable(
        rivals.table_id, version + 1, Ending.unplayed(UNPLAYED_DAYS)
    )
    assert {name for name, rows in rows_of(rivals.engine, rivals.table_id.value).items() if rows} == {
        "tables",
        "series",
        "receipts",
        "game_list",
    }


def test_two_expiries_that_meet_end_the_table_once(rivals):
    version = rivals.stored().version
    first, second = rivals.settle(rivals.expire(rivals.first_hold), rivals.expire())

    assert (first, second) == ([True], [False])
    assert replace(rivals.stored(), last_series=None) == EndedTable(
        rivals.table_id, version + 1, Ending.unplayed(UNPLAYED_DAYS)
    )


ENDINGS = (
    pytest.param(Ending(EndReason.CLOSED, closed_by_name="Anna"), id="closed"),
    pytest.param(Ending.stopped(), id="stopped"),
    pytest.param(Ending.unplayed(UNPLAYED_DAYS), id="unplayed"),
    pytest.param(Ending.empty(DEFAULT_EMPTY_TABLE_SECONDS), id="empty"),
)


class TestAnEndedTableThatFinishedAGame:
    @pytest.fixture
    def agent_game(self, service, transactions, stored):
        """A listed game whose middle seat was an agent."""
        table_id = seated_table(service, "one")
        save(transactions, after_the_first_game(with_agents(stored(transactions, table_id.value), 2)))
        return table_id

    @pytest.mark.parametrize("ending", ENDINGS)
    def test_reads_the_standings_of_its_last_series_with_each_seat_and_kind_and_names_no_closer(
        self, ending, agent_game, transactions, service
    ):
        ended_at(transactions, agent_game, ending)

        ended = service.view(OPENER, agent_game.value, NOBODY_CONNECTED).ended

        assert ended.game_count == 1
        assert ended.closed_by_name is None
        assert [(each.display_name, each.seat, each.kind, each.place) for each in ended.standings] == [
            ("Anna", 1, OccupantKind.PERSON, 1),
            ("Ben", 2, OccupantKind.AGENT, 2),
            ("Cleo", 3, OccupantKind.PERSON, 2),
        ]

    def test_a_table_that_finished_no_game_keeps_its_closers_name_and_has_no_standings(self, service, transactions):
        table_id = undealt_table(service, "one")
        ended_at(transactions, table_id, Ending(EndReason.CLOSED, closed_by_name="Anna"))

        ended = service.view(OPENER, table_id.value, NOBODY_CONNECTED).ended

        assert (ended.closed_by_name, ended.standings, ended.game_count) == ("Anna", None, None)
