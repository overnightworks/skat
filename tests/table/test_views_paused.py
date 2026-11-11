from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from skat.engine.bidding import Bid, Pass
from skat.engine.deal import Position
from skat.table.records import (
    Actor,
    Chair,
    EndedTable,
    EndReason,
    GiveUpAsked,
    HandProgress,
    Occupant,
    OccupantKind,
    Series,
    TableId,
)
from skat.table.service import OccupiedChair, TableService
from skat.table.views import paused_entry_of
from tests.support.fake_tables import FakeTableStore
from tests.support.played_game import a_whole_game, after_the_first_game, declared_herz_hand, table_in

# `table_in` seats the middlehand on chair 1, the rearhand on chair 2 and the forehand on chair 3.
MIDDLEHAND, REARHAND, FOREHAND = "account-middlehand", "account-rearhand", "account-forehand"
STRANGER = "account-stranger"
FIRST_CHAIR, SECOND_CHAIR, THIRD_CHAIR = 1, 2, 3
OTHER_TABLE_IDS = tuple(TableId(f"{number:032x}") for number in (1, 2, 3))

AUCTION_RUNS = HandProgress()
AFTER_THE_BID = HandProgress(auction=(Bid(Position.MIDDLEHAND, 18),))
BEFORE_THE_DECLARATION = HandProgress(
    auction=(Bid(Position.MIDDLEHAND, 18), Pass(Position.FOREHAND), Pass(Position.REARHAND))
)
THREE_PASSES = HandProgress(auction=(Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND)))


DAYS = 90
LAST_PLAYED_AT = datetime(2026, 11, 1, 12, tzinfo=UTC)
ENDS_AT = LAST_PLAYED_AT + timedelta(days=DAYS)


def entry_of(table, viewer, ends_at=ENDS_AT, opener_name=None):
    return paused_entry_of(table, viewer, ends_at, opener_name)


def actor(account_id):
    return Actor(account_id=account_id, display_name=account_id)


@pytest.fixture
def store():
    return FakeTableStore()


@pytest.fixture
def service(store):
    return TableService(store)


def keep(store, table, last_played_at=LAST_PLAYED_AT, opener_name=None):
    store.tables[table.id.value] = table
    store.last_played_at[table.id.value] = last_played_at
    if opener_name is not None:
        store.opener_names[table.id.value] = opener_name
    return table


class TestTheSeatWhoseMoveTheHandWaitsFor:
    @pytest.mark.parametrize(
        ("progress", "turn_seat"),
        [
            pytest.param(AUCTION_RUNS, FIRST_CHAIR, id="the-middlehand-opens-the-auction"),
            pytest.param(AFTER_THE_BID, THIRD_CHAIR, id="the-forehand-answers-the-bid"),
            pytest.param(BEFORE_THE_DECLARATION, FIRST_CHAIR, id="the-declarer-declares"),
            pytest.param(declared_herz_hand(), THIRD_CHAIR, id="the-forehand-leads"),
            pytest.param(
                replace(declared_herz_hand(), give_up=GiveUpAsked(Position.MIDDLEHAND)),
                THIRD_CHAIR,
                id="the-playing-turn-stays-while-a-give-up-request-stands",
            ),
        ],
    )
    def test_names_the_speaker_the_declarer_or_the_player_on_turn(self, progress, turn_seat):
        entry = entry_of(table_in(progress), FOREHAND)

        assert (entry.turn_seat, entry.result_waits) == (turn_seat, False)

    def test_names_the_next_player_in_the_middle_of_a_trick(self):
        declared = table_in(declared_herz_hand())
        first_card = a_whole_game(declared)[0]
        entry = entry_of(replace(declared, progress=replace(declared.progress, plays=(first_card,))), FOREHAND)

        assert entry.turn_seat == FIRST_CHAIR


class TestBetweenHands:
    def test_a_pending_result_waits_with_each_chairs_total_as_the_table_shows_it(self):
        table = after_the_first_game(table_in(HandProgress()))
        table = replace(table, series=Series(36, 1))

        entry = entry_of(table, MIDDLEHAND)

        assert (entry.turn_seat, entry.result_waits) == (None, True)
        assert [chair.total for chair in entry.chairs] == [86, 0, 0]

    def test_a_passed_in_hand_waits_for_nobody(self):
        entry = entry_of(replace(table_in(THREE_PASSES), series=Series(36, 2)), MIDDLEHAND)

        assert (entry.turn_seat, entry.result_waits) == (None, False)

    def test_a_finished_series_stays_at_its_last_game_with_its_result_waiting(self):
        finished = replace(after_the_first_game(table_in(HandProgress())), series=Series(36, 36))

        entry = entry_of(finished, MIDDLEHAND)

        assert (entry.game_number, entry.game_count, entry.turn_seat, entry.result_waits) == (36, 36, None, True)

    def test_a_finished_series_whose_last_deal_was_passed_in_waits_for_no_result(self):
        entry = entry_of(replace(table_in(THREE_PASSES), series=Series(36, 36)), MIDDLEHAND)

        assert (entry.game_number, entry.game_count, entry.turn_seat, entry.result_waits) == (36, 36, None, False)


class TestTheEntry:
    def test_names_the_game_number_and_series_length_and_marks_only_the_readers_chair(self):
        table = replace(table_in(AUCTION_RUNS), series=Series(36, 1))
        entry = entry_of(table, REARHAND)

        assert (entry.id, entry.game_number, entry.game_count) == (table.id.value, 1, 36)
        assert [(chair.seat, chair.occupant_name, chair.is_mine) for chair in entry.chairs] == [
            (1, "MIDDLEHAND", False),
            (2, "REARHAND", True),
            (3, "FOREHAND", False),
        ]

    def test_a_table_without_a_series_has_no_game_number_and_no_series_length(self):
        entry = entry_of(table_in(AUCTION_RUNS), FOREHAND)

        assert (entry.game_number, entry.game_count) == (None, None)

    def test_a_free_chair_carries_no_name(self):
        table = table_in(AUCTION_RUNS)
        table = replace(table, chairs=(Chair(1, None), *table.chairs[1:]))

        assert entry_of(table, FOREHAND).chairs[0].occupant_name is None

    def test_carries_nothing_of_the_hand_nor_any_account(self):
        entry = entry_of(replace(table_in(declared_herz_hand()), series=Series(36, 1)), FOREHAND)

        assert set(asdict(entry)) == {
            "id",
            "chairs",
            "game_number",
            "game_count",
            "turn_seat",
            "result_waits",
            "ends_at",
            "opener_name",
        }
        assert all(set(chair) == {"seat", "occupant_name", "is_mine", "total"} for chair in asdict(entry)["chairs"])
        assert {FOREHAND, MIDDLEHAND, REARHAND}.isdisjoint(str(asdict(entry)))


class TestTheServiceReadsOnlyTheCallersDealtLiveTables:
    def test_a_holder_gets_the_dealt_table_and_a_stranger_gets_none(self, service, store):
        table = keep(store, table_in(AUCTION_RUNS))

        assert [entry.id for entry in service.paused_tables(actor(FOREHAND), DAYS)] == [table.id.value]
        assert service.paused_tables(actor(STRANGER), DAYS) == ()

    def test_a_table_on_which_no_hand_was_dealt_is_not_listed(self, service, store):
        keep(store, replace(table_in(AUCTION_RUNS), dealer=None, hand=None))

        assert service.paused_tables(actor(FOREHAND), DAYS) == ()

    def test_lists_the_tables_in_id_order_and_leaves_the_undealt_one_out(self, service, store):
        later, earlier, undealt = (replace(table_in(AUCTION_RUNS), id=table_id) for table_id in OTHER_TABLE_IDS[::-1])
        keep(store, later)
        keep(store, replace(undealt, dealer=None, hand=None, id=OTHER_TABLE_IDS[1]))
        keep(store, replace(earlier, id=OTHER_TABLE_IDS[0]))

        assert [entry.id for entry in service.paused_tables(actor(FOREHAND), DAYS)] == [
            OTHER_TABLE_IDS[0].value,
            OTHER_TABLE_IDS[2].value,
        ]

    def test_lists_the_soonest_end_first_and_equal_ends_in_id_order(self, service, store):
        for table_id, played in zip(
            OTHER_TABLE_IDS,
            (LAST_PLAYED_AT + timedelta(days=1), LAST_PLAYED_AT, LAST_PLAYED_AT + timedelta(days=1)),
            strict=True,
        ):
            keep(store, replace(table_in(AUCTION_RUNS), id=table_id), played)

        assert [entry.id for entry in service.paused_tables(actor(FOREHAND), DAYS)] == [
            OTHER_TABLE_IDS[1].value,
            OTHER_TABLE_IDS[0].value,
            OTHER_TABLE_IDS[2].value,
        ]

    def test_the_end_is_the_last_played_time_plus_the_days_in_utc_and_the_title_the_stored_opener(self, service, store):
        keep(store, table_in(AUCTION_RUNS), LAST_PLAYED_AT.astimezone(timezone(timedelta(hours=-5))), "Ben")

        (entry,) = service.paused_tables(actor(FOREHAND), 10)

        assert (entry.ends_at, entry.ends_at.utcoffset(), entry.opener_name) == (
            LAST_PLAYED_AT + timedelta(days=10),
            timedelta(0),
            "Ben",
        )

    def test_a_table_stored_without_an_opener_name_has_none_and_still_an_end(self, service, store):
        keep(store, table_in(AUCTION_RUNS))

        (entry,) = service.paused_tables(actor(FOREHAND), DAYS)

        assert (entry.opener_name, entry.ends_at) == (None, LAST_PLAYED_AT + timedelta(days=DAYS))

    def test_a_table_that_ended_after_the_chair_scan_is_skipped_without_an_error(self, store):
        class EndsAfterTheScan(FakeTableStore):
            def occupied_chairs(self):
                held = super().occupied_chairs()
                self.tables = {key: EndedTable(TableId(key), 9, EndReason.EMPTY, 60) for key in self.tables}
                return held

        racing = EndsAfterTheScan()
        keep(racing, table_in(AUCTION_RUNS))

        assert TableService(racing).paused_tables(actor(FOREHAND), DAYS) == ()

    def test_a_table_whose_chair_changed_hands_after_the_scan_is_skipped_for_the_one_who_left(self):
        table_id = table_in(AUCTION_RUNS).id

        class ChairChangesAfterTheScan(FakeTableStore):
            def occupied_chairs(self):
                return (*super().occupied_chairs(), OccupiedChair(table_id, STRANGER))

        racing = ChairChangesAfterTheScan()
        keep(racing, table_in(AUCTION_RUNS))

        assert TableService(racing).paused_tables(actor(STRANGER), DAYS) == ()
        assert len(TableService(racing).paused_tables(actor(FOREHAND), DAYS)) == 1


class TestTablesHeldBy:
    def test_answers_each_table_the_account_holds_a_chair_at_in_id_order(self, service, store):
        for table_id in OTHER_TABLE_IDS[::-1]:
            keep(store, replace(table_in(AUCTION_RUNS), id=table_id))
        stranger_chair = Chair(1, Occupant(STRANGER, "S", OccupantKind.PERSON))
        keep(store, replace(table_in(AUCTION_RUNS), id=TableId("f" * 32), chairs=(stranger_chair,)))

        assert service.tables_held_by(FOREHAND) == OTHER_TABLE_IDS
