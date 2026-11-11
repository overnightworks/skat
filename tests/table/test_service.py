import itertools
import random
from contextlib import AbstractContextManager, nullcontext
from dataclasses import replace

import pytest

from skat.engine.bidding import Pass
from skat.engine.cards import DECK
from skat.engine.deal import SEATS, Position, next_dealer, positions_from
from skat.engine.tricks import CardPlayed
from skat.table.hand_state import playing_of
from skat.table.playing import PlayCardCommand
from skat.table.records import Actor, CreateTable, HandProgress, Receipt, Refusal, SitDown, StandUp, TableId
from skat.table.service import CommandIdReusedError, TableService
from skat.table.transactions import OccupiedChair
from tests.support.fake_tables import FakeTableStore
from tests.support.faulty_tables import FaultyTableTransactions
from tests.support.played_game import after_the_first_game, before_the_last_card, declared_herz_hand

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")


@pytest.fixture
def store():
    return FakeTableStore()


@pytest.fixture
def service(store):
    numbers = itertools.count(1)
    return TableService(store, new_table_id=lambda: TableId(f"{next(numbers):032x}"))


class TestCreate:
    def test_seats_the_opener_in_chair_one_with_two_free_chairs(self, service):
        view = service.create(OPENER, CreateTable(command_id="command-1"))

        chairs = [(chair.seat, chair.occupant_name, chair.is_mine) for chair in view.chairs]
        assert chairs == [
            (1, "Anna", True),
            (2, None, False),
            (3, None, False),
        ]

    def test_starts_the_table_at_version_one(self, service):
        assert service.create(OPENER, CreateTable(command_id="command-1")).version == 1

    def test_one_account_may_open_any_number_of_tables(self, service, store):
        first = service.create(OPENER, CreateTable(command_id="command-1"))
        second = service.create(OPENER, CreateTable(command_id="command-2"))

        assert first.id != second.id
        assert len(store.tables) == 2

    def test_the_same_command_id_and_payload_returns_the_table_the_first_request_created(self, service, store):
        first = service.create(OPENER, CreateTable(command_id="command-1"))
        again = service.create(OPENER, CreateTable(command_id="command-1"))

        assert again == first
        assert len(store.tables) == 1

    def test_another_account_using_the_same_command_id_opens_its_own_table(self, service, store):
        service.create(OPENER, CreateTable(command_id="command-1"))
        service.create(VISITOR, CreateTable(command_id="command-1"))

        assert len(store.tables) == 2

    def test_a_command_id_reused_with_another_payload_is_refused_and_writes_nothing(self, service, store):
        first = service.create(OPENER, CreateTable(command_id="command-1"))
        receipt = store.receipts[(OPENER.account_id, "command-1")]
        store.receipts[(OPENER.account_id, "command-1")] = Receipt(
            receipt.account_id, receipt.command_id, receipt.command, '{"seats": 4}', receipt.table_id
        )

        command = CreateTable(command_id="command-1")

        with pytest.raises(CommandIdReusedError):
            service.create(OPENER, command)

        assert list(store.tables) == [first.id]

    def test_a_failure_between_the_table_write_and_the_receipt_persists_nothing(self, service, store):
        faulty = TableService(FaultyTableTransactions(store, receipt_failure=RuntimeError("connection lost")))

        command = CreateTable(command_id="command-1")

        with pytest.raises(RuntimeError, match="connection lost"):
            faulty.create(OPENER, command)

        assert store.tables == {}
        assert store.receipts == {}

    def test_loses_a_race_against_an_identical_request_by_returning_the_winners_table(self, service, store):
        winner = service.create(OPENER, CreateTable(command_id="command-1"))
        blind = TableService(FaultyTableTransactions(store, blind_first_replay=True))

        assert blind.create(OPENER, CreateTable(command_id="command-1")) == winner
        assert len(store.tables) == 1


class TestView:
    def test_shows_another_member_the_opener_in_chair_one_and_assigns_them_no_chair(self, service):
        created = service.create(OPENER, CreateTable(command_id="command-1"))

        view = service.view(VISITOR, created.id, frozenset())

        chairs = [(chair.seat, chair.occupant_name, chair.is_mine) for chair in view.chairs]
        assert chairs == [
            (1, "Anna", False),
            (2, None, False),
            (3, None, False),
        ]

    def test_shows_the_opener_their_own_chair_after_a_reload(self, service):
        created = service.create(OPENER, CreateTable(command_id="command-1"))

        assert service.view(OPENER, created.id, frozenset()) == created

    @pytest.mark.parametrize(
        ("connected", "watchers"),
        [
            pytest.param(frozenset(), 0, id="nobody-connected"),
            pytest.param({OPENER.account_id}, 0, id="the-seated-opener-is-no-watcher"),
            pytest.param({VISITOR.account_id}, 1, id="a-connected-member-without-a-chair-watches"),
            pytest.param({OPENER.account_id, VISITOR.account_id, "account-third"}, 2, id="each-account-counts-once"),
        ],
    )
    def test_counts_the_connected_members_without_a_chair_as_watchers(self, service, connected, watchers):
        created = service.create(OPENER, CreateTable(command_id="command-1"))

        assert service.view(VISITOR, created.id, connected).watchers == watchers

    @pytest.mark.parametrize(
        ("viewer", "connected", "away"),
        [
            pytest.param(OPENER, frozenset(), [False, True, False], id="the-viewers-own-chair-is-never-away"),
            pytest.param(OPENER, {VISITOR.account_id}, [False, False, False], id="a-connected-occupant-is-present"),
            pytest.param(VISITOR, frozenset(), [True, False, False], id="an-occupant-without-a-stream-is-away"),
            pytest.param(VISITOR, {"account-third"}, [True, False, False], id="a-third-accounts-stream-is-no-help"),
            pytest.param(VISITOR, {OPENER.account_id}, [False, False, False], id="an-occupant-with-a-stream-is-here"),
        ],
    )
    def test_marks_a_chair_away_when_its_occupant_has_no_connected_stream(self, service, viewer, connected, away):
        created = service.create(OPENER, CreateTable(command_id="command-1"))
        service.sit(VISITOR, SitDown("command-2", created.id, 2), frozenset())

        view = service.view(viewer, created.id, frozenset(connected))

        assert [chair.is_away for chair in view.chairs] == away

    def test_a_new_table_has_no_watchers(self, service):
        assert service.create(OPENER, CreateTable(command_id="command-1")).watchers == 0

    @pytest.mark.parametrize("table_id", ["0" * 32, "", "not-an-id", "A" * 32, "0" * 31, "0" * 33, "../" + "0" * 29])
    def test_an_unknown_or_malformed_id_is_no_table(self, service, table_id):
        assert service.view(OPENER, table_id, frozenset()) is None


class TestTableId:
    def test_a_random_id_is_128_bits_of_hex_that_parses_back(self):
        identifiers = {TableId.random() for _ in range(50)}

        assert len(identifiers) == 50
        assert all(
            len(identifier.value) == 32 and TableId.parse(identifier.value) == identifier for identifier in identifiers
        )


@pytest.fixture
def table_id(service):
    return service.create(OPENER, CreateTable(command_id="command-open")).id


def sit(service, actor, table_id, seat, command_id="command-sit"):
    return service.sit(actor, SitDown(command_id, table_id, seat), frozenset())


def occupants_of(view):
    return [chair.occupant_name for chair in view.chairs]


class TestSit:
    def test_seats_the_member_in_the_chair_and_marks_it_theirs(self, service, table_id):
        result = sit(service, VISITOR, table_id, 2)

        assert result.refusal is None
        chairs = [(chair.occupant_name, chair.is_mine) for chair in result.view.chairs]
        assert chairs == [
            ("Anna", False),
            ("Ben", True),
            (None, False),
        ]

    def test_the_seat_is_there_for_the_next_read(self, service, table_id):
        sit(service, VISITOR, table_id, 2)

        assert occupants_of(service.view(OPENER, table_id, frozenset())) == ["Anna", "Ben", None]

    def test_refuses_a_taken_chair_naming_who_holds_it(self, service, table_id):
        result = sit(service, VISITOR, table_id, 1)

        assert result.refusal == Refusal.SEAT_TAKEN
        assert result.holder == "Anna"
        assert occupants_of(result.view) == ["Anna", None, None]

    def test_the_loser_of_the_last_chair_is_told_who_got_it(self, service, table_id):
        sit(service, VISITOR, table_id, 2)
        sit(service, Actor("account-third", "Cem"), table_id, 3)

        late = sit(service, Actor("account-fourth", "Dora"), table_id, 3)

        assert late.refusal == Refusal.SEAT_TAKEN
        assert late.holder == "Cem"

    def test_refuses_a_second_chair_to_a_seated_member(self, service, table_id):
        result = sit(service, OPENER, table_id, 2)

        assert result.refusal is Refusal.ALREADY_SEATED
        assert occupants_of(result.view) == ["Anna", None, None]

    def test_a_retry_returns_the_first_seat_and_writes_nothing_more(self, service, store, table_id):
        first = sit(service, VISITOR, table_id, 2)
        written = dict(store.tables)

        assert sit(service, VISITOR, table_id, 2) == first
        assert store.tables == written

    def test_a_retry_of_a_refusal_returns_the_refusal_even_after_the_chair_frees_up(self, service, table_id):
        first = sit(service, VISITOR, table_id, 1)
        service.stand(OPENER, StandUp("command-stand", table_id), frozenset())

        again = sit(service, VISITOR, table_id, 1)

        assert again.refusal == first.refusal
        assert again.holder == first.holder
        assert occupants_of(again.view) == [None, None, None]

    def test_refuses_a_command_id_reused_for_another_chair(self, service, store, table_id):
        sit(service, VISITOR, table_id, 2)
        before = dict(store.tables)

        with pytest.raises(CommandIdReusedError):
            sit(service, VISITOR, table_id, 3)

        assert store.tables == before

    def test_refuses_a_command_id_reused_by_stand_up(self, service, table_id):
        sit(service, VISITOR, table_id, 2)

        reuse = StandUp("command-sit", table_id)

        with pytest.raises(CommandIdReusedError):
            service.stand(VISITOR, reuse, frozenset())

    @pytest.mark.parametrize("unknown", ["0" * 32, "", "not-an-id"])
    def test_an_unknown_or_malformed_table_is_no_table_and_writes_nothing(self, service, store, unknown):
        before = (dict(store.tables), dict(store.receipts))

        assert sit(service, VISITOR, unknown, 2) is None
        state = (store.tables, store.receipts)
        assert state == before

    def test_a_failure_after_the_decision_persists_nothing(self, store, table_id):
        before = (dict(store.tables), dict(store.receipts))
        faulty = TableService(FaultyTableTransactions(store, receipt_failure=RuntimeError("connection lost")))

        with pytest.raises(RuntimeError, match="connection lost"):
            sit(faulty, VISITOR, table_id, 2)

        state = (store.tables, store.receipts)
        assert state == before

    def test_the_same_command_id_on_another_table_is_refused_when_it_races_the_first(self, service, store, table_id):
        other_id = service.create(OPENER, CreateTable(command_id="command-other")).id
        sit(service, VISITOR, table_id, 2)
        blind = TableService(FaultyTableTransactions(store, blind_first_replay=True))

        with pytest.raises(CommandIdReusedError):
            sit(blind, VISITOR, other_id, 2)


class TestStand:
    def test_frees_the_own_chair_and_keeps_every_number(self, service, table_id):
        sit(service, VISITOR, table_id, 3)

        result = service.stand(VISITOR, StandUp("command-stand", table_id), frozenset())

        assert result.refusal is None
        chairs = [(chair.seat, chair.occupant_name) for chair in result.view.chairs]
        assert chairs == [
            (1, "Anna"),
            (2, None),
            (3, None),
        ]

    def test_refuses_a_member_without_a_chair_and_changes_nothing(self, service, table_id):
        result = service.stand(VISITOR, StandUp("command-stand", table_id), frozenset())

        assert result.refusal is Refusal.NOT_SEATED
        assert occupants_of(service.view(OPENER, table_id, frozenset())) == ["Anna", None, None]

    def test_a_retry_returns_the_first_outcome(self, service, store, table_id):
        first = service.stand(OPENER, StandUp("command-stand", table_id), frozenset())
        written = dict(store.tables)

        assert service.stand(OPENER, StandUp("command-stand", table_id), frozenset()) == first
        assert store.tables == written

    def test_another_member_may_take_the_freed_chair(self, service, table_id):
        service.stand(OPENER, StandUp("command-stand", table_id), frozenset())

        assert occupants_of(sit(service, VISITOR, table_id, 1).view) == ["Ben", None, None]

    def test_an_unknown_table_is_no_table(self, service):
        assert service.stand(OPENER, StandUp("command-stand", "0" * 32), frozenset()) is None


CLEO = Actor("account-cleo", "Cleo")
DORA = Actor("account-dora", "Dora")


def seeded_service(store, seed):
    numbers = itertools.count(1)
    return TableService(
        store,
        new_table_id=lambda: TableId(f"{next(numbers):032x}"),
        random_source=random.Random(seed),  # noqa: S311 - a seeded source makes the deal reproducible
    )


def seated_three(service, last=3):
    table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
    sit(service, VISITOR, table_id, 2, "command-ben")
    return table_id, sit(service, CLEO, table_id, last, "command-cleo")


class TestDeal:
    def test_the_third_sit_stores_a_dealer_and_a_hand_of_ten_ten_ten_and_two_covering_the_deck(self, store):
        table_id, result = seated_three(seeded_service(store, 1))

        stored = store.tables[table_id]
        assert result.refusal is None
        assert stored.dealer in SEATS
        assert [len(cards) for cards in stored.hand.hands.values()] == [10, 10, 10]
        assert len(stored.hand.skat) == 2
        dealt = [card for cards in stored.hand.hands.values() for card in cards] + list(stored.hand.skat)
        assert sorted(dealt, key=DECK.index) == list(DECK)

    def test_the_third_sit_is_one_version_bump_and_one_receipt(self, store):
        table_id, _ = seated_three(seeded_service(store, 1))

        assert store.tables[table_id].version == 3
        assert len(store.receipts) == 3

    def test_a_chair_freed_earlier_is_dealt_as_the_last_chair_too(self, store):
        service = seeded_service(store, 1)
        table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
        sit(service, VISITOR, table_id, 2, "command-ben")
        service.stand(OPENER, StandUp("command-stand", table_id), frozenset())
        sit(service, CLEO, table_id, 3, "command-cleo")

        assert store.tables[table_id].hand is None

        sit(service, DORA, table_id, 1, "command-dora")

        assert store.tables[table_id].hand is not None

    def test_the_same_seed_on_fresh_tables_deals_the_same_dealer_and_hand(self):
        first_store, second_store = FakeTableStore(), FakeTableStore()
        first_id, _ = seated_three(seeded_service(first_store, 9))
        second_id, _ = seated_three(seeded_service(second_store, 9))

        first, second = first_store.tables[first_id], second_store.tables[second_id]
        assert (first.dealer, first.hand) == (second.dealer, second.hand)

    def test_a_retry_of_the_third_sit_returns_its_first_outcome_and_deals_nothing_again(self, store):
        service = seeded_service(store, 1)
        table_id, first = seated_three(service)
        dealt = store.tables[table_id]

        assert sit(service, CLEO, table_id, 3, "command-cleo") == first
        assert store.tables[table_id] == dealt

    def test_two_or_fewer_seated_have_no_hand(self, store):
        service = seeded_service(store, 1)
        table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
        sit(service, VISITOR, table_id, 2, "command-ben")
        service.stand(VISITOR, StandUp("command-stand", table_id), frozenset())

        assert (store.tables[table_id].dealer, store.tables[table_id].hand) == (None, None)

    def test_a_fourth_member_gets_seat_taken_and_no_second_deal(self, store):
        service = seeded_service(store, 1)
        table_id, _ = seated_three(service)
        dealt = store.tables[table_id]

        late = sit(service, DORA, table_id, 2, "command-dora")

        assert late.refusal is Refusal.SEAT_TAKEN
        assert store.tables[table_id] == dealt

    def test_standing_up_while_a_hand_runs_is_refused_and_changes_nothing(self, store):
        service = seeded_service(store, 1)
        table_id, _ = seated_three(service)
        dealt = store.tables[table_id]

        result = service.stand(VISITOR, StandUp("command-stand", table_id), frozenset())

        assert result.refusal is Refusal.HAND_RUNNING
        assert store.tables[table_id] == dealt

    def test_a_third_sit_rolled_back_after_a_duplicate_receipt_leaves_no_hand(self, store):
        service = seeded_service(store, 1)
        table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
        other_id = service.create(OPENER, CreateTable(command_id="command-other")).id
        sit(service, VISITOR, table_id, 2, "command-ben")
        sit(service, CLEO, other_id, 2, "command-cleo")
        blind = TableService(
            FaultyTableTransactions(store, blind_first_replay=True),
            random_source=random.Random(2),  # noqa: S311 - a seeded source makes the deal reproducible
        )

        with pytest.raises(CommandIdReusedError):
            sit(blind, CLEO, table_id, 3, "command-cleo")

        assert (store.tables[table_id].dealer, store.tables[table_id].hand) == (None, None)


def always_due() -> AbstractContextManager[bool]:
    return nullcontext(enter_result=True)


class TestFreeChair:
    def test_frees_the_chair_of_its_occupant_keeps_every_number_and_bumps_the_version_without_a_receipt(
        self, service, store, table_id
    ):
        sit(service, VISITOR, table_id, 3)
        receipts_before = dict(store.receipts)
        version_before = store.tables[table_id].version

        freed = service.free_chair(TableId(table_id), VISITOR.account_id, always_due())

        assert freed is True
        assert occupants_of(service.view(OPENER, table_id, frozenset())) == ["Anna", None, None]
        assert store.tables[table_id].version == version_before + 1
        assert store.receipts == receipts_before

    def test_a_second_run_changes_nothing(self, service, store, table_id):
        sit(service, VISITOR, table_id, 3)
        service.free_chair(TableId(table_id), VISITOR.account_id, always_due())
        written = dict(store.tables)

        assert service.free_chair(TableId(table_id), VISITOR.account_id, always_due()) is False
        assert store.tables == written

    def test_changes_nothing_for_an_account_that_stood_up_before(self, service, store, table_id):
        sit(service, VISITOR, table_id, 3)
        service.stand(VISITOR, StandUp("command-stand", table_id), frozenset())
        written = dict(store.tables)

        assert service.free_chair(TableId(table_id), VISITOR.account_id, always_due()) is False
        assert store.tables == written

    def test_changes_nothing_while_a_hand_runs(self, store):
        service = seeded_service(store, 1)
        table_id, _ = seated_three(service)
        dealt = store.tables[table_id]

        assert service.free_chair(TableId(table_id), VISITOR.account_id, always_due()) is False
        assert store.tables[table_id] == dealt

    def test_changes_nothing_when_the_caller_is_no_longer_due_once_the_row_is_locked(self, service, store, table_id):
        sit(service, VISITOR, table_id, 3)
        written = dict(store.tables)

        assert service.free_chair(TableId(table_id), VISITOR.account_id, nullcontext(enter_result=False)) is False
        assert store.tables == written

    def test_an_unknown_table_is_no_table(self, service):
        assert service.free_chair(TableId("0" * 32), VISITOR.account_id, always_due()) is False

    def test_a_failure_after_the_chair_write_persists_nothing(self, service, store, table_id):
        sit(service, VISITOR, table_id, 3)
        written = dict(store.tables)
        failing = TableService(FaultyTableTransactions(store, save_failure=ConnectionError("lost")))

        chair_to_free = TableId(table_id)
        due = always_due()

        with pytest.raises(ConnectionError):
            failing.free_chair(chair_to_free, VISITOR.account_id, due)

        assert store.tables == written


ALL_THREE = frozenset({OPENER.account_id, VISITOR.account_id, CLEO.account_id})


def passed_in(store, table_id):
    """The table as the third pass leaves it: no hand, and the three passes still stored."""
    steps = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
    store.tables[table_id] = replace(store.tables[table_id], hand=None, progress=HandProgress(steps))


class TestDealNext:
    @pytest.fixture
    def table_id(self, store):
        table_id, _ = seated_three(seeded_service(store, 1))
        passed_in(store, table_id)
        return table_id

    @pytest.fixture
    def dealing(self, store):
        return seeded_service(store, 2)

    def test_deals_the_next_dealer_a_new_hand_and_clears_the_steps_in_one_bump_without_a_receipt(
        self, dealing, store, table_id
    ):
        before = store.tables[table_id]
        receipts_before = dict(store.receipts)

        assert dealing.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is True

        after = store.tables[table_id]
        assert after.dealer == next_dealer(before.dealer)
        assert [len(cards) for cards in after.hand.hands.values()] == [10, 10, 10]
        assert after.progress == HandProgress()
        assert after.version == before.version + 1
        assert store.receipts == receipts_before

    def test_a_second_run_changes_nothing(self, dealing, store, table_id):
        dealing.deal_next(TableId(table_id), nullcontext(ALL_THREE))
        written = dict(store.tables)

        assert dealing.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is False
        assert store.tables == written

    @pytest.mark.parametrize(
        "connected",
        [
            pytest.param(ALL_THREE - {CLEO.account_id}, id="one-member-away"),
            pytest.param(frozenset(), id="nobody-connected"),
        ],
    )
    def test_changes_nothing_while_a_member_is_away(self, dealing, store, table_id, connected):
        written = dict(store.tables)

        assert dealing.deal_next(TableId(table_id), nullcontext(connected)) is False
        assert store.tables == written

    def test_changes_nothing_when_a_chair_is_free(self, dealing, store, table_id):
        dealing.stand(CLEO, StandUp("command-stand", table_id), frozenset())
        written = dict(store.tables)

        assert dealing.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is False
        assert store.tables == written

    def test_changes_nothing_while_a_hand_runs(self, store):
        service = seeded_service(store, 1)
        table_id, _ = seated_three(service)
        written = dict(store.tables)

        assert service.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is False
        assert store.tables == written

    def test_an_unknown_table_is_no_table(self, dealing):
        assert dealing.deal_next(TableId("0" * 32), nullcontext(ALL_THREE)) is False

    def test_a_failure_after_the_write_persists_nothing(self, store, table_id):
        written = dict(store.tables)
        failing = TableService(FaultyTableTransactions(store, save_failure=ConnectionError("lost")))
        identifier = TableId(table_id)
        everyone = nullcontext(ALL_THREE)

        with pytest.raises(ConnectionError):
            failing.deal_next(identifier, everyone)

        assert store.tables == written


def end_the_first_game(store, table_id, *ready_seats):
    store.tables[table_id] = after_the_first_game(store.tables[table_id], *ready_seats)


class TestDealNextAfterAResult:
    @pytest.fixture
    def table_id(self, store):
        table_id, _ = seated_three(seeded_service(store, 1))
        return table_id

    @pytest.fixture
    def dealing(self, store):
        return seeded_service(store, 2)

    def test_all_three_ready_deal_the_next_dealer_clear_every_mark_and_end_the_result_in_one_bump(
        self, dealing, store, table_id
    ):
        end_the_first_game(store, table_id, 1, 2, 3)
        before = store.tables[table_id]

        assert dealing.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is True

        after = store.tables[table_id]
        view = dealing.view(OPENER, table_id, ALL_THREE)
        assert (after.dealer, after.version) == (next_dealer(before.dealer), before.version + 1)
        assert [chair.ready for chair in after.chairs] == [False, False, False]
        assert (view.result, after.game_list) == (None, before.game_list)

    def test_two_marks_deal_nothing(self, dealing, store, table_id):
        end_the_first_game(store, table_id, 1, 2)
        written = dict(store.tables)

        assert dealing.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is False
        assert store.tables == written

    def test_a_sit_in_the_free_chair_marks_the_sitter_and_deals_nothing(self, dealing, store, table_id):
        end_the_first_game(store, table_id, 1, 2)
        dealing.stand(CLEO, StandUp("command-stand", table_id), frozenset())

        result = dealing.sit(DORA, SitDown("command-dora", table_id, 3), ALL_THREE)

        after = store.tables[table_id]
        assert result.refusal is None
        assert after.hand is None
        assert [chair.ready for chair in after.chairs] == [True, True, True]
        assert result.view.result is not None


def declared(store, table_id):
    """The table once middlehand won at 18 and declared a Herz Hand game; forehand leads."""
    store.tables[table_id] = replace(store.tables[table_id], progress=declared_herz_hand())


def at_the_last_card(store, table_id):
    """The declared table one card before the end; returns that last card."""
    store.tables[table_id], last = before_the_last_card(store.tables[table_id])
    return last


class TestPlayCard:
    @pytest.fixture
    def table_id(self, store):
        table_id, _ = seated_three(seeded_service(store, 1))
        return table_id

    def play(self, service, store, table_id, played, heard, version):
        """Only the opener is connected; the card comes from whoever holds its position."""
        seat = {position: seat for seat, position in positions_from(store.tables[table_id].dealer).items()}
        actor = (OPENER, VISITOR, CLEO)[seat[played.position] - 1]
        command = PlayCardCommand("command-card", table_id, version, played.card)
        return service.play_card(actor, command, frozenset({OPENER.account_id}), on_hand_ended=heard.append)

    def test_the_thirtieth_card_names_who_sat_and_tells_the_caller_who_was_away(self, service, store, table_id):
        last = at_the_last_card(store, table_id)
        heard = []

        result = self.play(service, store, table_id, last, heard, store.tables[table_id].version)

        assert result.seated_when_hand_ended == {OPENER.account_id, VISITOR.account_id, CLEO.account_id}
        assert heard == [{VISITOR.account_id, CLEO.account_id}]

    def test_a_card_before_the_thirtieth_ends_no_hand(self, service, store, table_id):
        declared(store, table_id)
        lead = CardPlayed(Position.FOREHAND, playing_of(store.tables[table_id]).hands[Position.FOREHAND][0])
        heard = []

        result = self.play(service, store, table_id, lead, heard, store.tables[table_id].version)

        assert result.seated_when_hand_ended == frozenset()
        assert heard == [frozenset()]

    def test_a_retry_of_the_thirtieth_card_restarts_no_hold(self, service, store, table_id):
        last = at_the_last_card(store, table_id)
        version = store.tables[table_id].version
        self.play(service, store, table_id, last, [], version)
        heard = []

        again = self.play(service, store, table_id, last, heard, version)

        assert again.seated_when_hand_ended == frozenset()
        assert heard == []


class TestOccupiedChairs:
    def test_lists_every_occupied_chair_of_every_table_and_no_free_one(self, service, table_id):
        sit(service, VISITOR, table_id, 3)
        other_id = service.create(VISITOR, CreateTable(command_id="command-other")).id

        assert set(service.occupied_chairs()) == {
            OccupiedChair(TableId(table_id), OPENER.account_id),
            OccupiedChair(TableId(table_id), VISITOR.account_id),
            OccupiedChair(TableId(other_id), VISITOR.account_id),
        }

    def test_lists_no_chair_when_no_table_exists(self, service):
        assert service.occupied_chairs() == ()
