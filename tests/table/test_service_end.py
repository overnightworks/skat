import itertools
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skat.engine.bidding import Pass
from skat.engine.cards import Card, Rank, Suit
from skat.engine.deal import Position
from skat.engine.declaration import TakeSkat
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.declaring import DeclaringCommand
from skat.table.playing import PlayCardCommand
from skat.table.ready import ReadyCommand
from skat.table.records import (
    Actor,
    CloseTable,
    CreateTable,
    EndedTable,
    Ending,
    EndReason,
    HandProgress,
    OccupantKind,
    Refusal,
    SitDown,
    StandUp,
    TableId,
    TableRecord,
)
from skat.table.rules import CREATE_TABLE_COMMAND, ends_empty
from skat.table.service import CommandIdReusedError, TableService
from skat.table.views import EndedView
from tests.support.fake_tables import FakeTableStore
from tests.support.faulty_tables import FaultyTableTransactions
from tests.support.played_game import after_the_first_game

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
NOBODY = frozenset[str]()
THIRD = Actor(account_id="account-third", display_name="Cleo")
ENDED_AT = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
EMPTY_SECONDS = 7
UNPLAYED_DAYS = 90


@pytest.fixture
def store():
    return FakeTableStore()


@pytest.fixture
def service(store):
    numbers = itertools.count(1)
    return TableService(store, new_table_id=lambda: TableId(f"{next(numbers):032x}"), now=lambda: ENDED_AT)


@pytest.fixture
def table_id(service):
    return TableId(service.create(OPENER, CreateTable(command_id="command-open")).id)


@pytest.fixture
def table(store, table_id):
    return store.tables[table_id.value]


@pytest.fixture
def dealt_id(service, table_id):
    """The table after a third person sat down and the first hand was dealt."""
    service.sit(VISITOR, SitDown("command-sit-ben", table_id.value, 2), NOBODY)
    service.sit(THIRD, SitDown("command-sit-cleo", table_id.value, 3), NOBODY)
    return table_id


def end_empty(service, table_id, connected=NOBODY):
    return service.end_empty_table(table_id, nullcontext(connected), EMPTY_SECONDS)


@pytest.mark.parametrize(
    ("connected", "dealt", "ends"),
    [
        pytest.param(frozenset(), False, True, id="nobody-and-no-hand-dealt"),
        pytest.param(frozenset({"account-opener"}), False, False, id="a-member"),
        pytest.param(frozenset({"account-visitor"}), False, False, id="a-watcher"),
        pytest.param(None, False, False, id="presence-stopped"),
        pytest.param(frozenset(), True, False, id="nobody-and-a-hand-dealt"),
    ],
)
def test_a_table_ends_only_while_no_hand_was_dealt_and_nobody_is_connected(table, connected, dealt, ends):
    table = replace(table, dealer=1 if dealt else None)

    assert ends_empty(table, connected) is ends


class TestEndEmptyTable:
    def test_ends_a_table_nobody_is_connected_to_with_one_version_bump_and_no_new_receipt(
        self, service, store, table_id
    ):
        before = store.tables[table_id.value]
        receipts_before = dict(store.receipts)

        assert end_empty(service, table_id) is True

        assert store.tables[table_id.value] == EndedTable(table_id, before.version + 1, Ending.empty(EMPTY_SECONDS))
        assert store.receipts == receipts_before

    def test_stamps_the_end_with_the_service_clock(self, service, store, table_id):
        end_empty(service, table_id)

        assert store.ended_at[table_id.value] == ENDED_AT

    @pytest.mark.parametrize("connected", [frozenset({"account-opener"}), None], ids=["a-member", "presence-stopped"])
    def test_changes_nothing_unless_nobody_is_connected(self, service, store, table_id, connected):
        written = dict(store.tables)

        assert end_empty(service, table_id, connected) is False
        assert store.tables == written

    def test_a_second_run_changes_nothing(self, service, store, table_id):
        end_empty(service, table_id)
        written = dict(store.tables)

        assert end_empty(service, table_id) is False
        assert store.tables == written

    def test_changes_nothing_for_a_table_that_does_not_exist(self, service, store):
        assert end_empty(service, TableId("0" * 32)) is False
        assert store.tables == {}

    def test_deletes_the_receipts_of_the_table_but_its_create_receipt_and_those_of_other_tables(
        self, service, store, table_id
    ):
        service.sit(VISITOR, SitDown("command-sit", table_id.value, 2), NOBODY)
        other = service.create(VISITOR, CreateTable(command_id="command-other"))
        service.sit(OPENER, SitDown("command-sit-other", other.id, 2), NOBODY)
        others = {key: receipt for key, receipt in store.receipts.items() if receipt.table_id.value == other.id}

        end_empty(service, table_id)

        left = {key: receipt for key, receipt in store.receipts.items() if receipt.table_id == table_id}
        assert [(receipt.command_id, receipt.command) for receipt in left.values()] == [
            ("command-open", CREATE_TABLE_COMMAND)
        ]
        assert {key: receipt for key, receipt in store.receipts.items() if key in others} == others

    def test_the_ended_table_has_no_chairs_hand_result_or_watchers(self, service, store, table_id):
        service.sit(VISITOR, SitDown("command-sit", table_id.value, 2), NOBODY)

        end_empty(service, table_id)

        view = service.view(OPENER, table_id.value, NOBODY)
        assert view.chairs == ()
        assert [view.hand, view.result, view.passed_in] == [None, None, None]
        assert view.watchers == 0
        assert view.ended == EndedView(EndReason.EMPTY, EMPTY_SECONDS, None, None)

    def test_the_wait_is_stored_with_the_end(self, service, table_id):
        service.end_empty_table(table_id, nullcontext(NOBODY), 7)

        assert service.view(OPENER, table_id.value, NOBODY).ended.empty_seconds == 7


class TestADealtTablePauses:
    def assert_kept(self, service, store, table_id):
        written = (dict(store.tables), dict(store.receipts))

        assert end_empty(service, table_id) is False
        assert store.tables == written[0]
        assert store.receipts == written[1]
        assert isinstance(store.tables[table_id.value], TableRecord)

    def test_a_running_hand_is_kept_with_every_row(self, service, store, dealt_id):
        assert store.tables[dealt_id.value].hand is not None

        self.assert_kept(service, store, dealt_id)

    def test_a_pending_result_and_its_list_are_kept(self, service, store, dealt_id):
        store.tables[dealt_id.value] = after_the_first_game(store.tables[dealt_id.value])

        self.assert_kept(service, store, dealt_id)

    def test_a_passed_in_hand_is_kept(self, service, store, dealt_id):
        passes = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
        store.tables[dealt_id.value] = replace(store.tables[dealt_id.value], hand=None, progress=HandProgress(passes))

        self.assert_kept(service, store, dealt_id)


class TestAtAnEndedTable:
    @pytest.fixture
    def ended_id(self, service, table_id):
        end_empty(service, table_id)
        return table_id

    def test_a_create_retry_returns_the_ended_table_and_makes_no_second_one(self, service, store, ended_id):
        again = service.create(OPENER, CreateTable(command_id="command-open"))

        assert again.id == ended_id.value
        assert again.ended == EndedView(EndReason.EMPTY, EMPTY_SECONDS, None, None)
        assert list(store.tables) == [ended_id.value]

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param(
                lambda service, table_id: service.sit(VISITOR, SitDown("c-sit", table_id, 2), NOBODY), id="sit"
            ),
            pytest.param(
                lambda service, table_id: service.stand(OPENER, StandUp("c-stand", table_id), NOBODY), id="stand"
            ),
            pytest.param(
                lambda service, table_id: service.take_auction_step(
                    OPENER, AuctionCommand("c-auction", table_id, 1, AuctionAction.PASS, None), NOBODY
                ),
                id="auction",
            ),
            pytest.param(
                lambda service, table_id: service.take_declaring_step(
                    OPENER, DeclaringCommand("c-declaring", table_id, 1, TakeSkat()), NOBODY
                ),
                id="declaring",
            ),
            pytest.param(
                lambda service, table_id: service.play_card(
                    OPENER, PlayCardCommand("c-card", table_id, 1, Card(Suit.KREUZ, Rank.SEVEN)), NOBODY
                ),
                id="card",
            ),
            pytest.param(
                lambda service, table_id: service.mark_ready(OPENER, ReadyCommand("c-ready", table_id, 1), NOBODY),
                id="ready",
            ),
        ],
    )
    def test_a_command_finds_no_table_and_writes_nothing(self, service, store, ended_id, command):
        written = (dict(store.tables), dict(store.receipts))

        assert command(service, ended_id.value) is None
        assert store.tables == written[0]
        assert store.receipts == written[1]

    def test_the_server_frees_no_chair_and_deals_nothing(self, service, store, ended_id):
        written = dict(store.tables)

        assert service.free_chair(ended_id, OPENER.account_id, nullcontext(True)) is False
        assert service.deal_next(ended_id, nullcontext(frozenset({OPENER.account_id}))) is False
        assert store.tables == written

    def test_the_create_command_id_is_refused_for_another_request(self, service, ended_id):
        other = service.create(VISITOR, CreateTable(command_id="command-other"))

        sit_down = SitDown("command-open", other.id, 2)

        with pytest.raises(CommandIdReusedError):
            service.sit(OPENER, sit_down, NOBODY)

    def test_lists_no_live_table_for_it(self, service, ended_id):
        live = TableId(service.create(VISITOR, CreateTable(command_id="command-other")).id)

        assert service.resume_empty_waits(EMPTY_SECONDS).keys() == {live.value}


def test_a_deal_asked_for_with_presence_stopped_deals_nothing(service, store, dealt_id):
    table_id = dealt_id
    passes = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
    store.tables[table_id.value] = replace(store.tables[table_id.value], hand=None, progress=HandProgress(passes))
    written = dict(store.tables)

    assert service.deal_next(table_id, nullcontext(None)) is False
    assert store.tables == written


SOMEBODY = frozenset({"account-opener"})


def stamp(store, table_id, seconds_ago):
    store.empty_since_by_table[table_id.value] = ENDED_AT - timedelta(seconds=seconds_ago)


def note(service, table_id, connected):
    return service.note_presence(table_id, nullcontext(connected), EMPTY_SECONDS)


class TestNotePresence:
    def test_a_created_table_is_stamped_with_the_service_clock(self, store, table_id):
        assert store.empty_since_by_table[table_id.value] == ENDED_AT

    def test_the_sit_that_deals_the_first_hand_clears_the_time_with_no_stream_open(self, store, dealt_id):
        assert store.empty_since_by_table[dealt_id.value] is None

    def test_a_view_and_a_sit_that_deals_nothing_leave_the_time_as_it_is(self, service, store, table_id):
        stamp(store, table_id, 3)

        service.view(OPENER, table_id.value, NOBODY)
        service.sit(VISITOR, SitDown("command-sit-ben", table_id.value, 2), NOBODY)

        assert store.empty_since_by_table[table_id.value] == ENDED_AT - timedelta(seconds=3)

    def test_the_last_leave_stamps_a_table_with_no_time_and_changes_nothing_else(self, service, store, table_id):
        store.empty_since_by_table[table_id.value] = None
        before = store.tables[table_id.value]

        assert note(service, table_id, NOBODY) is False

        assert store.empty_since_by_table[table_id.value] == ENDED_AT
        assert store.tables[table_id.value] == before

    def test_a_leave_keeps_an_earlier_time(self, service, store, table_id):
        stamp(store, table_id, 3)

        note(service, table_id, NOBODY)

        assert store.empty_since_by_table[table_id.value] == ENDED_AT - timedelta(seconds=3)

    def test_an_arrival_before_the_time_is_up_clears_the_time(self, service, store, table_id):
        stamp(store, table_id, EMPTY_SECONDS - 1)

        assert note(service, table_id, SOMEBODY) is False

        assert store.empty_since_by_table[table_id.value] is None
        assert isinstance(store.tables[table_id.value], TableRecord)

    def test_an_arrival_after_the_time_is_up_ends_the_table(self, service, store, table_id):
        stamp(store, table_id, EMPTY_SECONDS)

        assert note(service, table_id, SOMEBODY) is True

        assert isinstance(store.tables[table_id.value], EndedTable)

    @pytest.mark.parametrize("connected", [None, SOMEBODY], ids=["presence-stopped", "someone-without-a-time"])
    def test_changes_nothing_when_the_presence_cannot_tell_or_there_is_no_time_to_clear(
        self, service, store, table_id, connected
    ):
        store.empty_since_by_table[table_id.value] = None
        written = dict(store.empty_since_by_table), dict(store.tables)

        assert note(service, table_id, connected) is False
        assert dict(store.empty_since_by_table) == written[0]
        assert dict(store.tables) == written[1]

    def test_changes_nothing_for_a_table_that_does_not_exist(self, service, store):
        assert note(service, TableId("0" * 32), NOBODY) is False
        assert store.tables == {}


class TestResumeEmptyWaits:
    def test_a_table_with_no_time_is_stamped_now_and_waits_a_full_time(self, service, store, table_id):
        store.empty_since_by_table[table_id.value] = None

        assert service.resume_empty_waits(EMPTY_SECONDS) == {table_id.value: EMPTY_SECONDS}
        assert store.empty_since_by_table[table_id.value] == ENDED_AT

    def test_a_table_waits_what_is_left_of_its_wait(self, service, store, table_id):
        stamp(store, table_id, 3)

        assert service.resume_empty_waits(EMPTY_SECONDS) == {table_id.value: EMPTY_SECONDS - 3}

    def test_a_table_past_its_wait_has_ended_and_is_not_waited_for(self, service, store, table_id):
        stamp(store, table_id, EMPTY_SECONDS + 1)

        assert service.resume_empty_waits(EMPTY_SECONDS) == {}
        assert isinstance(store.tables[table_id.value], EndedTable)

    @pytest.mark.parametrize("seconds_ago", [None, EMPTY_SECONDS + 1], ids=["without-a-time", "past-its-wait"])
    def test_a_dealt_table_is_kept_and_stamped_with_nothing(self, service, store, dealt_id, seconds_ago):
        store.empty_since_by_table[dealt_id.value] = None
        if seconds_ago is not None:
            stamp(store, dealt_id, seconds_ago)
        before = store.empty_since_by_table[dealt_id.value]

        assert service.resume_empty_waits(EMPTY_SECONDS) == {}
        assert isinstance(store.tables[dealt_id.value], TableRecord)
        assert store.empty_since_by_table[dealt_id.value] == before


def last_played(store, table_id, *, days_ago=UNPLAYED_DAYS, seconds_more=0):
    store.last_played_at[table_id.value] = ENDED_AT - timedelta(days=days_ago, seconds=seconds_more)


class TestEndUnplayedTable:
    def test_ends_a_dealt_table_with_a_running_hand_with_one_version_bump_and_the_days_in_force(
        self, service, store, dealt_id
    ):
        before = store.tables[dealt_id.value]
        last_played(store, dealt_id, seconds_more=1)

        assert service.end_unplayed_table(dealt_id, UNPLAYED_DAYS, nullcontext(NOBODY)) is True

        assert before.hand is not None
        assert store.tables[dealt_id.value] == EndedTable(dealt_id, before.version + 1, Ending.unplayed(UNPLAYED_DAYS))
        assert store.ended_at[dealt_id.value] == ENDED_AT
        assert dealt_id.value not in store.last_played_at
        assert dealt_id.value not in store.opener_names

    @pytest.mark.parametrize(
        ("seconds_more", "ends"),
        [pytest.param(-1, False, id="a-second-before"), pytest.param(0, True, id="exactly-at-the-end")],
    )
    def test_ends_exactly_when_the_paused_list_says_it_ends(self, service, store, dealt_id, seconds_more, ends):
        last_played(store, dealt_id, seconds_more=seconds_more)

        assert service.end_unplayed_table(dealt_id, UNPLAYED_DAYS, nullcontext(NOBODY)) is ends

    def test_a_longer_setting_ends_nothing_that_the_shorter_one_would(self, service, store, dealt_id):
        last_played(store, dealt_id)

        assert service.end_unplayed_table(dealt_id, UNPLAYED_DAYS + 1, nullcontext(NOBODY)) is False
        assert isinstance(store.tables[dealt_id.value], TableRecord)

    def test_deletes_the_receipts_but_the_create_receipt(self, service, store, dealt_id):
        last_played(store, dealt_id)

        service.end_unplayed_table(dealt_id, UNPLAYED_DAYS, nullcontext(NOBODY))

        assert [receipt.command for receipt in store.receipts.values()] == [CREATE_TABLE_COMMAND]

    def test_the_ended_table_says_why_with_the_days(self, service, store, dealt_id):
        last_played(store, dealt_id)

        service.end_unplayed_table(dealt_id, 90, nullcontext(NOBODY))

        assert service.view(OPENER, dealt_id.value, NOBODY).ended == EndedView(EndReason.UNPLAYED, None, 90, None)

    def test_a_second_run_changes_nothing(self, service, store, dealt_id):
        last_played(store, dealt_id)
        service.end_unplayed_table(dealt_id, UNPLAYED_DAYS, nullcontext(NOBODY))
        written = dict(store.tables)

        assert service.end_unplayed_table(dealt_id, UNPLAYED_DAYS, nullcontext(NOBODY)) is False
        assert store.tables == written

    def test_a_table_that_was_played_since_it_was_read_as_due_changes_nothing(self, service, store, dealt_id):
        last_played(store, dealt_id, days_ago=1)
        written = dict(store.tables)

        assert service.end_unplayed_table(dealt_id, UNPLAYED_DAYS, nullcontext(NOBODY)) is False
        assert store.tables == written

    def test_a_table_with_no_hand_dealt_changes_nothing(self, service, store, table_id):
        written = dict(store.tables)

        assert service.end_unplayed_table(table_id, UNPLAYED_DAYS, nullcontext(NOBODY)) is False
        assert store.tables == written

    def test_a_table_ended_empty_changes_nothing(self, service, store, table_id):
        end_empty(service, table_id)
        written = dict(store.tables)

        assert service.end_unplayed_table(table_id, UNPLAYED_DAYS, nullcontext(NOBODY)) is False
        assert store.tables == written


class TestUnplayedTables:
    def test_lists_the_dealt_tables_played_the_days_ago_or_earlier_in_id_order(self, service, store, dealt_id):
        service.create(VISITOR, CreateTable(command_id="command-undealt"))
        recent = TableId(service.create(VISITOR, CreateTable(command_id="command-recent")).id)
        service.sit(OPENER, SitDown("command-sit-recent-1", recent.value, 2), NOBODY)
        service.sit(THIRD, SitDown("command-sit-recent-2", recent.value, 3), NOBODY)
        last_played(store, dealt_id)
        last_played(store, recent, days_ago=UNPLAYED_DAYS - 1)

        assert service.unplayed_tables(UNPLAYED_DAYS) == (dealt_id,)


def close(service, actor, table_id, command_id="command-close"):
    return service.close(actor, CloseTable(command_id, table_id.value))


class TestClose:
    def test_ends_the_table_with_one_version_bump_and_the_closers_name(self, service, store, table_id):
        before = store.tables[table_id.value]

        result = close(service, OPENER, table_id)

        assert store.tables[table_id.value] == EndedTable(
            table_id, before.version + 1, Ending.closed(OPENER.display_name)
        )
        assert store.ended_at[table_id.value] == ENDED_AT
        assert result.refusal is None
        assert result.view.ended == EndedView(EndReason.CLOSED, None, None, OPENER.display_name)

    def test_ends_a_dealt_table_with_its_running_hand(self, service, store, dealt_id):
        assert store.tables[dealt_id.value].hand is not None

        close(service, OPENER, dealt_id)

        assert store.tables[dealt_id.value].ending == Ending.closed(OPENER.display_name)
        assert dealt_id.value not in store.last_played_at

    def test_keeps_the_create_receipt_and_the_close_receipt_and_deletes_the_others(self, service, store, dealt_id):
        close(service, OPENER, dealt_id)

        assert sorted(receipt.command for receipt in store.receipts.values()) == ["close-table", CREATE_TABLE_COMMAND]

    def test_a_retry_with_the_same_command_id_answers_the_ended_view_and_changes_nothing(
        self, service, store, table_id
    ):
        close(service, OPENER, table_id)
        written = (dict(store.tables), dict(store.receipts))

        again = close(service, OPENER, table_id)

        assert again.view.ended == EndedView(EndReason.CLOSED, None, None, OPENER.display_name)
        assert (store.tables, store.receipts) == written

    def test_the_command_id_is_refused_for_another_table(self, service, table_id):
        other = TableId(service.create(OPENER, CreateTable(command_id="command-other")).id)
        close(service, OPENER, table_id)

        with pytest.raises(CommandIdReusedError):
            close(service, OPENER, other)

    def test_refuses_a_seated_person_who_did_not_open_the_table_and_writes_no_receipt(self, service, store, dealt_id):
        written = (dict(store.tables), dict(store.receipts))

        result = close(service, VISITOR, dealt_id)

        assert result.refusal is Refusal.NOT_ALLOWED
        assert (store.tables, store.receipts) == written

    def test_the_command_id_is_refused_for_another_table_when_a_rival_close_commits_between_lookup_and_receipt(
        self, store, service, table_id
    ):
        other = TableId(service.create(OPENER, CreateTable(command_id="command-other")).id)
        close(service, OPENER, table_id)
        blind = TableService(FaultyTableTransactions(store, blind_first_replay=True), now=lambda: ENDED_AT)

        with pytest.raises(CommandIdReusedError):
            close(blind, OPENER, other)

        assert isinstance(store.tables[other.value], TableRecord)

    def test_refuses_a_watcher_who_sits_nowhere(self, service, store, table_id):
        stranger = Actor(account_id="account-stranger", display_name="Dora")

        assert close(service, stranger, table_id).refusal is Refusal.NOT_ALLOWED
        assert isinstance(store.tables[table_id.value], TableRecord)

    def test_finds_no_table_for_an_unknown_or_an_ended_one(self, service, store, table_id):
        end_empty(service, table_id)
        written = (dict(store.tables), dict(store.receipts))

        assert close(service, OPENER, table_id) is None
        assert close(service, OPENER, TableId("0" * 32)) is None
        assert service.close(OPENER, CloseTable("command-close", "not-an-id")) is None
        assert (store.tables, store.receipts) == written

    def test_the_closed_table_leaves_every_holders_paused_list(self, service, dealt_id):
        holders = (OPENER, VISITOR, THIRD)
        assert all(service.paused_tables(holder, UNPLAYED_DAYS) for holder in holders)

        close(service, OPENER, dealt_id)

        assert [service.paused_tables(holder, UNPLAYED_DAYS) for holder in holders] == [(), (), ()]

    def test_tells_the_agents_of_the_table_once_after_the_commit(self, store, table_id):
        told = []
        service = TableService(store, now=lambda: ENDED_AT).with_standing_signal(told.append)
        agent = Actor("account-agent", "Nova", OccupantKind.AGENT, OPENER.account_id)
        service.sit(agent, SitDown("command-agent-sit", table_id.value, 2), NOBODY)
        told.clear()

        close(service, OPENER, table_id)
        close(service, OPENER, table_id)

        assert told == [frozenset({agent.account_id})]

    def test_the_opener_is_the_open_tables_view_owner_and_nobody_else(self, service, table_id):
        assert service.view(OPENER, table_id.value, NOBODY).opened_by_me is True
        assert service.view(VISITOR, table_id.value, NOBODY).opened_by_me is False
