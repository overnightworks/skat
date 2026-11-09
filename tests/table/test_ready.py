import itertools
from dataclasses import replace

import pytest

from skat.engine.bidding import Pass
from skat.engine.deal import Position
from skat.table.ready import ReadyCommand, decide_ready, ready_payload
from skat.table.records import (
    Actor,
    Chair,
    CreateTable,
    HandProgress,
    Occupant,
    Refusal,
    SitDown,
    TableId,
    TableRecord,
    parsed_refusal,
)
from skat.table.service import CommandIdReusedError, TableService
from tests.support.fake_tables import FakeTableStore
from tests.support.played_game import an_entry

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")
TABLE_VERSION = 9


def pending(*ready_seats: int, games: int = 2) -> TableRecord:
    """Three seated after their `games`-th game: no hand, no steps, the dealer and the list; `ready_seats` tapped."""
    people = ((1, ANNA), (2, BEN), (3, CLEO))
    chairs = tuple(
        Chair(seat, Occupant(actor.account_id, actor.display_name), ready=seat in ready_seats) for seat, actor in people
    )
    return TableRecord(
        TableId("0" * 32),
        TABLE_VERSION,
        chairs,
        dealer=2,
        hand=None,
        progress=HandProgress(),
        game_list=tuple(an_entry() for _ in range(games)),
        series=None,
    )


def weiter(ordinal: int = 2, command_id: str = "command-weiter") -> ReadyCommand:
    return ReadyCommand(command_id=command_id, table_id="0" * 32, ordinal=ordinal)


def ready_seats(table: TableRecord) -> list[int]:
    return [chair.seat for chair in table.chairs if chair.ready]


class TestDecideReady:
    def test_marks_only_the_actors_chair_and_bumps_the_version_once(self):
        decision = decide_ready(pending(), ANNA, weiter())

        assert decision.refusal is None
        assert ready_seats(decision.table) == [1]
        assert decision.table.version == TABLE_VERSION + 1

    def test_keeps_the_marks_already_set(self):
        decision = decide_ready(pending(1, 2), CLEO, weiter())

        assert ready_seats(decision.table) == [1, 2, 3]

    def test_a_chair_already_ready_is_accepted_and_changes_nothing(self):
        table = pending(1)

        decision = decide_ready(table, ANNA, weiter(command_id="command-again"))

        assert decision.refusal is None
        assert decision.table == table

    @pytest.mark.parametrize("ordinal", [1, 3], ids=["an-older-result", "a-result-not-yet-shown"])
    def test_another_result_than_the_pending_one_is_stale_and_changes_nothing(self, ordinal):
        table = pending()

        decision = decide_ready(table, ANNA, weiter(ordinal))

        assert decision.refusal is Refusal.STALE_RESULT
        assert decision.table == table

    @pytest.mark.parametrize(
        "table",
        [
            pytest.param(replace(pending(), hand=None, game_list=()), id="no-game-yet"),
            pytest.param(
                replace(pending(), progress=HandProgress((Pass(Position.MIDDLEHAND),) * 3)), id="a-passed-in-hand"
            ),
        ],
    )
    def test_no_pending_result_is_named_and_changes_nothing(self, table):
        decision = decide_ready(table, ANNA, weiter())

        assert decision.refusal is Refusal.NO_RESULT
        assert decision.table == table

    def test_a_viewer_without_a_chair_is_not_seated_before_any_other_reason(self):
        table = replace(pending(), game_list=())

        decision = decide_ready(table, DORA, weiter(5))

        assert decision.refusal is Refusal.NOT_SEATED
        assert decision.table == table

    def test_no_pending_result_is_named_before_a_stale_ordinal(self):
        assert decide_ready(replace(pending(), game_list=()), ANNA, weiter(5)).refusal is Refusal.NO_RESULT


class TestReadyPayload:
    def test_another_ordinal_is_another_request(self):
        assert ready_payload(weiter(1)) != ready_payload(weiter(2))


class TestReadyRefusalTokens:
    @pytest.mark.parametrize("refusal", [Refusal.NO_RESULT, Refusal.STALE_RESULT])
    def test_a_stored_token_reads_back_to_its_refusal(self, refusal):
        assert parsed_refusal(refusal.value) is refusal


class TestMarkReady:
    @pytest.fixture
    def store(self):
        return FakeTableStore()

    @pytest.fixture
    def table_id(self, store):
        numbers = itertools.count(1)
        service = TableService(store, new_table_id=lambda: TableId(f"{next(numbers):032x}"))
        table_id = service.create(ANNA, CreateTable(command_id="command-open")).id
        service.sit(BEN, SitDown("command-ben", table_id, 2), frozenset())
        service.sit(CLEO, SitDown("command-cleo", table_id, 3), frozenset())
        record = store.tables[table_id]
        store.tables[table_id] = replace(record, hand=None, progress=HandProgress(), game_list=(an_entry(),))
        return table_id

    @pytest.fixture
    def service(self, store):
        return TableService(store)

    def mark(self, service, table_id, actor=ANNA, ordinal=1, command_id="command-weiter"):
        return service.mark_ready(actor, ReadyCommand(command_id, table_id, ordinal), frozenset())

    def test_the_mark_shows_on_the_actors_chair_for_every_viewer(self, service, store, table_id):
        self.mark(service, table_id)

        views = [service.view(viewer, table_id, frozenset()) for viewer in (ANNA, BEN, DORA)]
        assert [[chair.ready for chair in view.chairs] for view in views] == [[True, False, False]] * 3
        assert ready_seats(store.tables[table_id]) == [1]

    def test_a_retry_replays_the_first_outcome_and_writes_nothing_more(self, service, store, table_id):
        first = self.mark(service, table_id)
        written = dict(store.tables)

        again = self.mark(service, table_id)

        assert again == first
        assert store.tables == written

    def test_a_retry_of_a_stale_tap_replays_the_refusal(self, service, table_id):
        first = self.mark(service, table_id, ordinal=7)

        again = self.mark(service, table_id, ordinal=7)

        assert (first.refusal, again.refusal) == (Refusal.STALE_RESULT, Refusal.STALE_RESULT)

    def test_a_command_id_reused_for_another_result_is_refused(self, service, table_id):
        self.mark(service, table_id)

        with pytest.raises(CommandIdReusedError):
            self.mark(service, table_id, ordinal=2)

    def test_an_unknown_table_is_no_table(self, service):
        assert self.mark(service, "0" * 32) is None
