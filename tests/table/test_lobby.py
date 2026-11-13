"""The lobby's list of the account's own tables: who holds which entry, what it says and in which order."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.table.awaiting import WaitingCase
from skat.table.records import (
    EndedTable,
    Ending,
    EndProposal,
    HandProgress,
    OccupantKind,
    Series,
    TableId,
    TableOptions,
    Visibility,
)
from skat.table.service import TableService
from tests.support.fake_tables import FakeTableStore
from tests.support.played_game import asked_by_the_declarer, between_games, declared_herz_hand, table_in, with_agents

MIDDLEHAND, REARHAND, FOREHAND = "account-middlehand", "account-rearhand", "account-forehand"
LAST_PLAYED = datetime(2026, 11, 1, 12, tzinfo=UTC)
DAYS = 10
NOBODY_CONNECTED: dict[str, frozenset[str]] = {}
NO_HOLDS: dict[str, dict[str, int]] = {}
STRANGER = "account-stranger"
KONTRA_OPTIONS = TableOptions(
    kontra=KontraOptions(KontraSayer.ANY_OPPONENT, KontraReach.KONTRA_RE, KontraDeadline.OWN_CARD)
)


def table_id_of(number):
    return TableId(f"{number:032x}")


class Lobby:
    """An in-memory store holding the tables a test puts in it, read as the lobby reads them."""

    def __init__(self, leases=frozenset()):
        self.store = FakeTableStore()
        self.service = TableService(self.store).with_leases(lambda: leases)

    def put(self, number, record, *, played_at=LAST_PLAYED, opener="Anna"):
        identifier = table_id_of(number)
        self.store.tables[identifier.value] = replace(record, id=identifier)
        if record.dealer is not None:
            self.store.last_played_at[identifier.value] = played_at
        if opener is not None:
            self.store.opener_names[identifier.value] = opener
        return identifier

    def entries(self, account, held=None, connected=NOBODY_CONNECTED, holds=NO_HOLDS):
        ids = held if held is not None else sorted((TableId(key) for key in self.store.tables), key=lambda i: i.value)
        return self.service.my_tables(account, tuple(ids), connected, holds, DAYS)

    def open_entries(self, account=STRANGER, listed=None, connected=NOBODY_CONNECTED, holds=NO_HOLDS):
        ids = self.service.open_table_ids() if listed is None else listed
        return self.service.open_tables(account, tuple(ids), connected, holds, DAYS)

    def open_ids(self, account=STRANGER, **read):
        return [entry.id for entry in self.open_entries(account, **read)]

    def ids(self, account, **read):
        return [entry.id for entry in self.entries(account, **read)]


def undealt():
    return replace(table_in(HandProgress()), dealer=None, hand=None)


def private(record):
    return replace(record, visibility=Visibility.PRIVATE)


def with_free_chairs(record, *seats):
    return replace(
        record, chairs=tuple(replace(chair, occupant=None) if chair.seat in seats else chair for chair in record.chairs)
    )


@pytest.fixture
def lobby():
    return Lobby()


class TestAnEntry:
    def test_a_table_before_its_first_deal_names_its_opener_and_waits_for_nobody(self, lobby):
        lobby.put(1, undealt())

        (entry,) = lobby.entries(MIDDLEHAND)

        assert (entry.id, entry.title_name, entry.dealt, entry.waits_on, entry.awaits_you, entry.ends_at) == (
            table_id_of(1).value,
            "Anna",
            False,
            None,
            False,
            None,
        )

    def test_a_table_opened_before_the_name_was_kept_has_no_title(self, lobby):
        lobby.put(1, undealt(), opener=None)

        assert lobby.entries(MIDDLEHAND)[0].title_name is None

    def test_the_chairs_come_in_order_with_the_callers_own_marked_and_a_free_chair_without_a_name(self, lobby):
        lobby.put(1, replace(undealt(), chairs=(*undealt().chairs[:2], replace(undealt().chairs[2], occupant=None))))

        (entry,) = lobby.entries(MIDDLEHAND)

        assert [(chair.seat, chair.occupant_name, chair.occupant_kind, chair.is_mine) for chair in entry.chairs] == [
            (1, "MIDDLEHAND", OccupantKind.PERSON, True),
            (2, "REARHAND", OccupantKind.PERSON, False),
            (3, None, None, False),
        ]

    def test_the_seat_on_turn_is_marked(self, lobby):
        lobby.put(1, table_in(HandProgress()))

        (entry,) = lobby.entries(MIDDLEHAND)

        assert [chair.is_turn for chair in entry.chairs] == [True, False, False]

    def test_the_game_number_and_the_series_length_are_the_series(self, lobby):
        lobby.put(1, between_games(series=Series(12, 3)))

        (entry,) = lobby.entries(MIDDLEHAND)

        assert (entry.game_number, entry.game_count) == (3, 12)

    def test_a_table_without_a_series_has_neither(self, lobby):
        lobby.put(1, table_in(HandProgress()))

        (entry,) = lobby.entries(MIDDLEHAND)

        assert (entry.game_number, entry.game_count) == (None, None)

    def test_a_series_that_is_over_says_so_with_its_result_and_waits_on_the_series_end(self, lobby):
        lobby.put(1, between_games(series=Series(12, 12)))

        (entry,) = lobby.entries(MIDDLEHAND)

        assert (entry.series_over, entry.result_waits, entry.waits_on, entry.awaits_you) == (
            True,
            True,
            WaitingCase.SERIES_END,
            True,
        )

    def test_a_result_waits_while_the_series_goes_on(self, lobby):
        lobby.put(1, between_games())

        (entry,) = lobby.entries(MIDDLEHAND)

        assert (entry.series_over, entry.result_waits, entry.waits_on) == (False, True, WaitingCase.RESULT)

    def test_the_waiting_case_goes_when_the_caller_has_continued(self, lobby):
        lobby.put(1, between_games(1))

        (entry,) = lobby.entries(MIDDLEHAND)

        assert (entry.waits_on, entry.awaits_you, [chair.ready for chair in entry.chairs]) == (
            None,
            False,
            [True, False, False],
        )

    def test_the_hands_waits_on_a_sitter_leaves_nobody_awaited(self, lobby):
        waiting = table_in(HandProgress())
        lobby.put(1, replace(waiting, chairs=(*waiting.chairs[:2], replace(waiting.chairs[2], occupant=None))))

        (entry,) = lobby.entries(MIDDLEHAND)

        assert entry.waits_on is None


class TestWhoIsAway:
    def test_a_chair_is_away_when_its_occupant_is_not_present_and_never_the_callers_own(self, lobby):
        lobby.put(1, undealt())

        (entry,) = lobby.entries(MIDDLEHAND, connected={table_id_of(1).value: frozenset({FOREHAND})})

        assert [chair.is_away for chair in entry.chairs] == [False, True, False]

    def test_an_agent_with_a_live_lease_is_not_away(self):
        lobby = Lobby(leases=frozenset({REARHAND}))
        lobby.put(1, with_agents(undealt(), 2))

        (entry,) = lobby.entries(MIDDLEHAND)

        assert [chair.is_away for chair in entry.chairs] == [False, False, True]

    def test_the_connections_of_another_table_make_nobody_present_here(self, lobby):
        lobby.put(1, undealt())

        (entry,) = lobby.entries(MIDDLEHAND, connected={table_id_of(2).value: frozenset({REARHAND, FOREHAND})})

        assert [chair.is_away for chair in entry.chairs] == [False, True, True]


class TestTheEnd:
    def test_a_dealt_table_with_nobody_present_ends_the_given_days_after_its_last_played_time(self, lobby):
        lobby.put(1, between_games())

        assert lobby.entries(MIDDLEHAND)[0].ends_at == datetime(2026, 11, 11, 12, tzinfo=UTC)

    def test_the_end_is_in_utc_whatever_zone_the_store_keeps(self, lobby):
        lobby.put(1, between_games(), played_at=datetime(2026, 11, 1, 14, tzinfo=timezone(timedelta(hours=2))))

        assert lobby.entries(MIDDLEHAND)[0].ends_at == datetime(2026, 11, 11, 12, tzinfo=UTC)

    @pytest.mark.parametrize("present", [FOREHAND, MIDDLEHAND])
    def test_a_dealt_table_has_no_end_while_anyone_is_present(self, lobby, present):
        lobby.put(1, between_games())

        (entry,) = lobby.entries(MIDDLEHAND, connected={table_id_of(1).value: frozenset({present})})

        assert entry.ends_at is None

    def test_a_table_where_no_hand_was_dealt_has_no_end(self, lobby):
        lobby.put(1, undealt())

        assert lobby.entries(MIDDLEHAND)[0].ends_at is None

    def test_a_dealt_table_has_an_end_whether_or_not_it_waits_for_the_caller(self, lobby):
        lobby.put(1, table_in(HandProgress()))

        (entry,) = lobby.entries(MIDDLEHAND)

        assert (entry.awaits_you, entry.ends_at) == (True, datetime(2026, 11, 11, 12, tzinfo=UTC))


class TestWhichTablesAreListed:
    def test_a_table_that_ended_or_is_not_there_is_skipped(self, lobby):
        kept = lobby.put(1, undealt())
        ended = table_id_of(2)
        lobby.store.tables[ended.value] = EndedTable(ended, 9, Ending.empty(3600))

        assert [entry.id for entry in lobby.entries(MIDDLEHAND, held=[kept, ended, table_id_of(3)])] == [kept.value]

    def test_a_table_whose_chair_the_caller_left_meanwhile_is_skipped(self, lobby):
        left = lobby.put(1, undealt())

        assert lobby.entries("account-stranger", held=[left]) == ()

    def test_only_the_listed_tables_are_read(self, lobby):
        lobby.put(1, undealt())
        listed = lobby.put(2, undealt())

        assert lobby.ids(MIDDLEHAND, held=[listed]) == [listed.value]


def ids_of(*numbers):
    return [table_id_of(number).value for number in numbers]


class TestTheOrder:
    def test_waiting_tables_come_first_then_dealt_with_someone_present_then_undealt_then_resting(self, lobby):
        lobby.put(1, between_games(1, 2, 3))
        lobby.put(2, undealt())
        lobby.put(3, table_in(declared_herz_hand()))
        lobby.put(4, table_in(HandProgress()))

        order = lobby.ids(MIDDLEHAND, connected={table_id_of(3).value: frozenset({FOREHAND})})

        assert order == ids_of(4, 3, 2, 1)

    def test_the_waiting_cases_come_in_the_order_turn_question_end_proposal_result_series_end(self, lobby):
        lobby.put(1, between_games(series=Series(12, 12)))
        lobby.put(2, between_games())
        lobby.put(3, between_games(1, 2, 3, proposal=EndProposal(2)))
        lobby.put(4, table_in(HandProgress()))

        assert lobby.ids(MIDDLEHAND) == ids_of(4, 3, 2, 1)

    def test_a_give_up_question_and_a_kontra_word_share_a_rank_and_go_by_id(self, lobby):
        lobby.put(1, table_in(declared_herz_hand(), KONTRA_OPTIONS))
        lobby.put(2, asked_by_the_declarer(None))

        assert lobby.ids(REARHAND) == ids_of(1, 2)

    def test_tables_of_one_case_go_by_id(self, lobby):
        for number in (3, 1, 2):
            lobby.put(number, between_games())

        assert lobby.ids(MIDDLEHAND) == ids_of(1, 2, 3)

    def test_dealt_tables_with_someone_present_go_by_id_and_so_do_the_undealt(self, lobby):
        connected = {table_id_of(number).value: frozenset({FOREHAND}) for number in (1, 2, 5, 6)}
        for number in (6, 5, 4, 3):
            lobby.put(number, between_games(1, 2, 3) if number > 4 else undealt())
        lobby.put(2, between_games(1, 2, 3))
        lobby.put(1, between_games(1, 2, 3))

        assert lobby.ids(MIDDLEHAND, connected=connected) == ids_of(1, 2, 5, 6, 3, 4)

    def test_resting_tables_go_by_the_soonest_end_then_by_id(self, lobby):
        lobby.put(1, between_games(1, 2, 3), played_at=LAST_PLAYED + timedelta(days=2))
        lobby.put(2, between_games(1, 2, 3), played_at=LAST_PLAYED)
        lobby.put(3, between_games(1, 2, 3), played_at=LAST_PLAYED + timedelta(days=2))

        assert lobby.ids(MIDDLEHAND) == ids_of(2, 1, 3)


class TestTheOpenList:
    def test_an_open_table_is_listed_to_a_member_with_no_chair_there_with_its_names_in_chair_order(self, lobby):
        lobby.put(1, with_free_chairs(undealt(), 3))

        (entry,) = lobby.open_entries()

        assert (entry.id, entry.title_name, entry.free_chairs) == (table_id_of(1).value, "Anna", 1)
        assert [(chair.seat, chair.occupant_name, chair.occupant_kind) for chair in entry.chairs] == [
            (1, "MIDDLEHAND", OccupantKind.PERSON),
            (2, "REARHAND", OccupantKind.PERSON),
            (3, None, None),
        ]

    def test_a_private_table_is_listed_to_nobody_whose_chair_it_is_not(self, lobby):
        lobby.put(1, private(with_free_chairs(undealt(), 3)))
        lobby.put(2, with_free_chairs(undealt(), 3))

        assert lobby.open_ids(STRANGER) == ids_of(2)

    def test_a_table_the_caller_holds_a_chair_at_is_left_to_the_callers_own_list(self, lobby):
        lobby.put(1, undealt())
        lobby.put(2, undealt())
        lobby.put(3, with_free_chairs(undealt(), 1))

        assert lobby.open_ids(MIDDLEHAND) == ids_of(3)
        assert lobby.ids(MIDDLEHAND) == ids_of(1, 2)

    def test_a_table_that_ended_or_is_not_there_is_skipped(self, lobby):
        kept = lobby.put(1, undealt())
        ended = table_id_of(2)
        lobby.store.tables[ended.value] = EndedTable(ended, 9, Ending.empty(3600))

        assert lobby.open_ids(listed=[kept, ended, table_id_of(3)]) == [kept.value]

    def test_a_private_table_in_the_candidates_is_skipped(self, lobby):
        hidden = lobby.put(1, private(undealt()))

        assert lobby.open_entries(listed=[hidden]) == ()

    def test_a_full_table_has_no_free_chair_and_goes_last_after_the_fewest_free_chairs_first_each_group_by_id(
        self, lobby
    ):
        lobby.put(1, undealt())
        lobby.put(2, with_free_chairs(undealt(), 2, 3))
        lobby.put(3, with_free_chairs(undealt(), 3))
        lobby.put(4, with_free_chairs(undealt(), 1))
        lobby.put(5, undealt())

        entries = lobby.open_entries()

        assert [(entry.id, entry.free_chairs) for entry in entries] == [
            (table_id_of(3).value, 1),
            (table_id_of(4).value, 1),
            (table_id_of(2).value, 2),
            (table_id_of(1).value, 0),
            (table_id_of(5).value, 0),
        ]

    def test_an_open_paused_table_with_a_free_chair_is_listed_and_says_its_hand_waits_for_a_sitter(self, lobby):
        lobby.put(1, with_free_chairs(table_in(HandProgress()), 1))

        (entry,) = lobby.open_entries()

        assert (entry.dealt, entry.waiting_seat, entry.free_chairs) == (True, 1, 1)

    def test_the_series_length_the_rule_options_and_the_watchers_are_the_tables(self, lobby):
        lobby.put(1, replace(between_games(series=Series(12, 3)), options=KONTRA_OPTIONS))

        (entry,) = lobby.open_entries(connected={table_id_of(1).value: frozenset({FOREHAND, STRANGER, "account-x"})})

        assert (entry.game_count, entry.game_number, entry.options, entry.watchers) == (12, 3, KONTRA_OPTIONS, 2)

    def test_a_table_without_a_series_has_neither(self, lobby):
        lobby.put(1, replace(undealt(), series=None))

        (entry,) = lobby.open_entries()

        assert (entry.game_count, entry.game_number) == (None, None)

    def test_a_chair_is_away_when_its_occupant_is_not_present(self, lobby):
        lobby.put(1, undealt())

        (entry,) = lobby.open_entries(connected={table_id_of(1).value: frozenset({FOREHAND})})

        assert [chair.is_away for chair in entry.chairs] == [True, True, False]

    def test_a_dealt_table_nobody_is_present_at_names_its_end(self, lobby):
        lobby.put(1, between_games(1, 2, 3))

        (entry,) = lobby.open_entries()

        assert entry.ends_at == LAST_PLAYED + timedelta(days=DAYS)

    def test_an_away_chair_at_an_undealt_table_says_the_seconds_its_hold_has_left_from_presence(self, lobby):
        lobby.put(1, undealt())

        (entry,) = lobby.open_entries(
            connected={table_id_of(1).value: frozenset({FOREHAND})},
            holds={table_id_of(1).value: {MIDDLEHAND: 240, FOREHAND: 100}},
        )

        assert [chair.hold_seconds_left for chair in entry.chairs] == [240, None, None]

    def test_a_chair_at_a_dealt_table_has_no_hold_to_count(self, lobby):
        lobby.put(1, table_in(HandProgress()))

        (entry,) = lobby.open_entries(holds={table_id_of(1).value: {MIDDLEHAND: 240}})

        assert [chair.hold_seconds_left for chair in entry.chairs] == [None, None, None]

    def test_an_own_chair_in_the_account_s_list_says_its_hold_too(self, lobby):
        lobby.put(1, undealt())

        (entry,) = lobby.entries(MIDDLEHAND, holds={table_id_of(1).value: {MIDDLEHAND: 240, REARHAND: 120}})

        assert [chair.hold_seconds_left for chair in entry.chairs] == [240, 120, None]
