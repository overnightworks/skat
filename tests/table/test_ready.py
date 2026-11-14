import itertools
import random
from dataclasses import replace

import pytest

from skat.engine.bidding import Pass
from skat.engine.bock import BockRounds
from skat.engine.deal import Position, deal
from skat.table.ready import (
    NewSeriesCommand,
    ReadyCommand,
    decide_new_series,
    decide_ready,
    new_series_payload,
    ready_payload,
)
from skat.table.records import (
    Actor,
    Chair,
    CreateTable,
    HandProgress,
    Occupant,
    Refusal,
    Series,
    SitDown,
    TableId,
    TableOptions,
    TableRecord,
    Visibility,
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
        Chair(seat, Occupant(actor.account_id, actor.display_name, actor.kind), ready=seat in ready_seats)
        for seat, actor in people
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
        options=TableOptions(),
        bock=BockRounds.start(),
        visibility=Visibility.OPEN,
    )


def weiter(ordinal: int = 2, command_id: str = "command-weiter", series: int = 1) -> ReadyCommand:
    return ReadyCommand(command_id=command_id, table_id="0" * 32, ordinal=ordinal, series=series)


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

    @pytest.mark.parametrize("series", [1, 4], ids=["an-earlier-series", "a-series-not-yet-started"])
    def test_another_series_than_the_tables_is_stale_and_changes_nothing(self, series):
        table = replace(pending(), series=Series(6, 2, number=3))

        decision = decide_ready(table, ANNA, weiter(series=series))

        assert decision.refusal is Refusal.STALE_SERIES
        assert decision.table == table

    def test_the_tables_series_marks_the_chair(self):
        decision = decide_ready(replace(pending(), series=Series(6, 2, number=3)), ANNA, weiter(series=3))

        assert (decision.refusal, ready_seats(decision.table)) == (None, [1])

    def test_a_table_with_no_series_is_the_first_series(self):
        assert decide_ready(pending(), ANNA, weiter(series=1)).refusal is None
        assert decide_ready(pending(), ANNA, weiter(series=2)).refusal is Refusal.STALE_SERIES

    def test_another_series_is_named_before_a_stale_ordinal(self):
        table = replace(pending(), series=Series(6, 2, number=3))

        assert decide_ready(table, ANNA, weiter(5, series=2)).refusal is Refusal.STALE_SERIES


def new_series(series: int = 1) -> NewSeriesCommand:
    return NewSeriesCommand(command_id="command-new-series", table_id="0" * 32, series=series)


def at_the_end(*ready_seats: int, games: int = 3, number: int = 1) -> TableRecord:
    """Three seated after the last game of series `number`, a series of three; `ready_seats` tapped."""
    return replace(pending(*ready_seats, games=games), series=Series(3, 3, number=number))


class TestDecideNewSeries:
    def test_marks_only_the_actors_chair_and_bumps_the_version_once(self):
        decision = decide_new_series(at_the_end(1), BEN, new_series())

        assert decision.refusal is None
        assert ready_seats(decision.table) == [1, 2]
        assert decision.table.version == TABLE_VERSION + 1

    def test_marks_the_chair_after_a_passed_in_last_game(self):
        passed_in_last = replace(at_the_end(games=0), progress=HandProgress((Pass(Position.MIDDLEHAND),) * 3))

        decision = decide_new_series(passed_in_last, CLEO, new_series())

        assert (decision.refusal, ready_seats(decision.table)) == (None, [3])

    def test_a_chair_already_marked_is_accepted_and_changes_nothing(self):
        table = at_the_end(2)

        decision = decide_new_series(table, BEN, new_series())

        assert decision.refusal is None
        assert decision.table == table

    @pytest.mark.parametrize(
        ("actor", "refusal"),
        [(DORA, Refusal.NOT_SEATED), (ANNA, Refusal.NO_SERIES)],
        ids=["a-viewer-without-a-chair-is-not-seated", "a-seated-chair-finds-no-series"],
    )
    def test_a_table_without_a_series_names_the_first_refusal_that_applies_and_changes_nothing(self, actor, refusal):
        table = replace(pending(), series=None)

        decision = decide_new_series(table, actor, new_series())

        assert decision.refusal is refusal
        assert decision.table == table

    @pytest.mark.parametrize(
        "table",
        [
            pytest.param(replace(pending(), series=Series(6, 2)), id="a-result-pending-mid-series"),
            pytest.param(replace(pending(), game_list=(), series=Series(6, 1)), id="no-game-yet"),
            pytest.param(
                replace(pending(), progress=HandProgress((Pass(Position.MIDDLEHAND),) * 3), series=Series(6, 2)),
                id="a-passed-in-hand-mid-series",
            ),
            pytest.param(
                replace(at_the_end(), hand=deal(random.Random(3))),  # noqa: S311 - a seeded source makes the deal reproducible
                id="a-hand-runs-at-the-last-game",
            ),
        ],
    )
    def test_a_series_not_over_is_named_and_changes_nothing(self, table):
        decision = decide_new_series(table, ANNA, new_series())

        assert decision.refusal is Refusal.SERIES_NOT_OVER
        assert decision.table == table

    @pytest.mark.parametrize("series", [1, 3], ids=["an-earlier-series", "a-series-not-yet-started"])
    def test_another_series_than_the_tables_is_stale_and_changes_nothing(self, series):
        table = at_the_end(1, number=2)

        decision = decide_new_series(table, BEN, new_series(series))

        assert decision.refusal is Refusal.STALE_SERIES
        assert decision.table == table

    def test_the_tables_series_marks_the_chair(self):
        decision = decide_new_series(at_the_end(number=2), BEN, new_series(2))

        assert (decision.refusal, ready_seats(decision.table)) == (None, [2])

    def test_another_series_is_named_before_a_series_not_over(self):
        table = replace(pending(), series=Series(6, 2, number=2))

        assert decide_new_series(table, ANNA, new_series(1)).refusal is Refusal.STALE_SERIES

    def test_a_table_without_a_series_has_no_series_whatever_is_named(self):
        table = replace(pending(), series=None)

        assert decide_new_series(table, ANNA, new_series(7)).refusal is Refusal.NO_SERIES


class TestNewSeriesPayload:
    def test_another_series_is_another_request(self):
        assert new_series_payload(new_series(1)) != new_series_payload(new_series(2))


class TestReadyPayload:
    def test_another_ordinal_is_another_request(self):
        assert ready_payload(weiter(1)) != ready_payload(weiter(2))

    def test_another_series_is_another_request(self):
        assert ready_payload(weiter(series=1)) != ready_payload(weiter(series=2))


class TestReadyRefusalTokens:
    @pytest.mark.parametrize(
        "refusal",
        [Refusal.NO_RESULT, Refusal.STALE_RESULT, Refusal.STALE_SERIES, Refusal.NO_SERIES, Refusal.SERIES_NOT_OVER],
    )
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

    def mark(self, service, table_id, actor=ANNA, ordinal=1, command_id="command-weiter", series=1):
        return service.mark_ready(actor, ReadyCommand(command_id, table_id, ordinal, series), frozenset())

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

    def test_a_retry_of_a_tap_for_another_series_replays_the_refusal(self, service, store, table_id):
        first = self.mark(service, table_id, series=2)
        written = dict(store.tables)

        again = self.mark(service, table_id, series=2)

        assert (first.refusal, again.refusal) == (Refusal.STALE_SERIES, Refusal.STALE_SERIES)
        assert ready_seats(store.tables[table_id]) == []
        assert store.tables == written

    def test_a_command_id_reused_for_another_series_is_refused(self, service, table_id):
        self.mark(service, table_id)

        with pytest.raises(CommandIdReusedError):
            self.mark(service, table_id, series=2)

    def test_a_command_id_reused_for_another_result_is_refused(self, service, table_id):
        self.mark(service, table_id)

        with pytest.raises(CommandIdReusedError):
            self.mark(service, table_id, ordinal=2)

    def test_an_unknown_table_is_no_table(self, service):
        assert self.mark(service, "0" * 32) is None
