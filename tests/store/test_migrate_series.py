from contextlib import nullcontext
from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from skat.engine.bock import BockRounds
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.store.migrate import create_store_engine, migrate
from skat.store.schema import metadata
from skat.store.tables import PostgresTableTransactions
from skat.table.game_list import bock_factor_of
from skat.table.ready import NewSeriesCommand
from skat.table.records import Actor, EndedTable, EndProposal, Series, TableId
from skat.table.series_end import SeriesEndCommand
from skat.table.service import TableService
from tests.support.migrations import list_row, migrated_from, only_row, run_in_transaction, upgrade_to
from tests.support.postgres import created_database

pytestmark = pytest.mark.postgres

PEOPLE = {
    1: Actor(account_id="account-anna", display_name="Anna"),
    2: Actor(account_id="account-ben", display_name="Ben"),
    3: Actor(account_id="account-cleo", display_name="Cleo"),
}
ALL_THREE = frozenset(person.account_id for person in PEOPLE.values())
SETTINGS = {
    "show_running_points": "true",
    "kontra_sayer": "'any-opponent'",
    "kontra_reach": "'kontra-re-standings'",
    "kontra_deadline": "'own-card'",
    "bock_triggers": "ARRAY['re', 'schneider']",
    "bock_overlap": "'multiply'",
    "ramsch_occasion": "'passed-in'",
    "ramsch_scoring": "'points'",
    "ramsch_jungfrau": "'off'",
    "ramsch_durchmarsch": "'off'",
}
SETTING_COLUMNS = ", ".join(SETTINGS)
LENGTH = 12


def table_row(table_id, **changed):
    """A table of a 12-game series, the settings above, a dealt hand's dealer, in series 1 at its fifth deal."""
    columns = {
        "id": f"'{table_id}'",
        "version": 4,
        "dealer": 2,
        "last_played_at": "now()",
        "series_length": LENGTH,
        "series_deals": 5,
        "series_number": 1,
        **SETTINGS,
        **changed,
    }
    return text(
        f"INSERT INTO tables ({', '.join(columns)}) VALUES ({', '.join(str(each) for each in columns.values())})"
    )  # noqa: S608 - only a test's fixed literals reach this text


def seated(table_id):
    values = ", ".join(
        f"('{table_id}', {seat}, '{person.account_id}', '{person.display_name}', 'person')"
        for seat, person in PEOPLE.items()
    )
    return text(f"INSERT INTO chairs (table_id, seat, account_id, display_name, occupant_kind) VALUES {values}")  # noqa: S608 - only a test's fixed literals reach this text


def played(table_id, series_number, ordinal=1, **changed):
    return text(
        list_row(
            table_id=f"'{table_id}'", series_number=series_number, ordinal=ordinal, kontra_word="'kontra'", **changed
        )
    )


STATES_AT_0047 = (
    table_row("first", series_deals=5, bock_rounds="ARRAY[2, 1]", ramsch_round_games=2),
    played("first", 1),
    table_row("second", series_number=2, series_deals=3),
    played("second", 1),
    played("second", 1, ordinal=2),
    played("second", 2),
    table_row(
        "plain",
        series_length="NULL",
        series_deals="NULL",
        **{**dict.fromkeys(SETTINGS, "NULL"), "show_running_points": "false"},
    ),
    table_row("proposed", series_end_proposer=1, series_end_accepter=2),
    seated("proposed"),
    played("proposed", 1),
    table_row("bocked", series_end_proposer=1, series_end_accepter=2, bock_rounds="ARRAY[3]", ramsch_round_games=1),
    seated("bocked"),
    played("bocked", 1),
    table_row("early", series_number=2, series_deals=7, series_ended_early="true"),
    seated("early"),
    played("early", 1),
    played("early", 2),
    text(
        "INSERT INTO tables (id, version, ended_at, end_reason, empty_seconds)"
        " VALUES ('gone-gameless', 7, now(), 'empty', 60)"
    ),
    table_row("gone-with-games", dealer="NULL", last_played_at="NULL", series_deals=LENGTH),
    text(
        "UPDATE tables SET ended_at = now(), end_reason = 'closed', closed_by_name = 'Anna'"
        " WHERE id = 'gone-with-games'"
    ),
    played("gone-with-games", 1),
)


@pytest.fixture
def migrated(unmigrated_engine):
    return migrated_from(unmigrated_engine, "0047", *STATES_AT_0047)


@pytest.fixture
def service(migrated):
    return TableService(PostgresTableTransactions(migrated))


def series_row(engine, table_id, number):
    return only_row(
        engine,
        text(
            "SELECT length, deals, ended_early, end_proposer, end_accepter, bock_rounds, ramsch_round_games,"
            f" {SETTING_COLUMNS} FROM series WHERE table_id = '{table_id}' AND number = {number}"  # noqa: S608 - only a test's fixed literals reach this text
        ),
    )


def numbers_of(engine, table_id):
    with engine.connect() as connection:
        rows = connection.execute(text(f"SELECT number FROM series WHERE table_id = '{table_id}' ORDER BY number"))  # noqa: S608 - only a test's fixed literals reach this text
        return [row.number for row in rows]


def record_of(engine, table_id):
    with PostgresTableTransactions(engine).begin() as transaction:
        return transaction.table(TableId(table_id))


class TestFromTablesAtTheRevisionBefore:
    def test_a_table_in_its_first_series_moves_its_settings_counters_and_bock_rounds_to_series_one(self, migrated):
        assert numbers_of(migrated, "first") == [1]
        length, deals, ended_early, proposer, accepter, bock_rounds, ramsch_games, *settings = series_row(
            migrated, "first", 1
        )
        assert (length, deals, ended_early, proposer, accepter) == (LENGTH, 5, False, None, None)
        assert (list(bock_rounds), ramsch_games) == ([2, 1], 2)
        assert settings == [
            True,
            "any-opponent",
            "kontra-re-standings",
            "own-card",
            ["re", "schneider"],
            "multiply",
            "passed-in",
            "points",
            "off",
            "off",
            None,
            None,
        ]

    def test_a_table_in_its_second_series_gets_row_one_with_every_deal_played_and_row_two_with_its_counters(
        self, migrated
    ):
        assert numbers_of(migrated, "second") == [1, 2]
        earlier = series_row(migrated, "second", 1)
        current = series_row(migrated, "second", 2)

        assert earlier[:7] == (LENGTH, LENGTH, False, None, None, [], 0)
        assert current[:7] == (LENGTH, 3, False, None, None, [], 0)
        assert earlier[7:] == current[7:]

    def test_a_table_without_a_series_reads_as_series_one_with_no_length(self, migrated):
        assert numbers_of(migrated, "plain") == [1]
        assert series_row(migrated, "plain", 1)[:2] == (None, None)

    def test_an_ended_table_keeps_the_series_of_its_games_and_a_gameless_one_its_pointed_series(self, migrated):
        assert numbers_of(migrated, "gone-gameless") == [1]
        assert numbers_of(migrated, "gone-with-games") == [1]

    def test_no_table_loses_a_series_a_game_or_the_pointer_names(self, migrated):
        assert only_row(
            migrated,
            text(
                "SELECT count(*) FROM game_list g WHERE NOT EXISTS"
                " (SELECT 1 FROM series s WHERE s.table_id = g.table_id AND s.number = g.series_number)"
            ),
        ) == (0,)
        assert only_row(
            migrated,
            text(
                "SELECT count(*) FROM tables t WHERE NOT EXISTS"
                " (SELECT 1 FROM series s WHERE s.table_id = t.id AND s.number = t.series_number)"
            ),
        ) == (0,)

    def test_a_game_stored_before_reads_its_seat_kinds_as_unknown(self, migrated):
        assert only_row(migrated, text("SELECT seat_1_kind, seat_2_kind, seat_3_kind FROM game_list LIMIT 1")) == (
            None,
            None,
            None,
        )

    def test_the_ended_table_with_games_reads_the_standings_its_options_gave_before(self, migrated, service):
        ended = record_of(migrated, "gone-with-games")

        assert isinstance(ended, EndedTable)
        assert ended.last_series.number == 1
        assert ended.last_series.options.kontra == KontraOptions(
            KontraSayer.ANY_OPPONENT, KontraReach.KONTRA_RE_STANDINGS, KontraDeadline.OWN_CARD
        )
        view = service.view(PEOPLE[1], "gone-with-games", frozenset())
        assert [(each.account_id, each.total, each.place) for each in view.ended.standings] == [
            ("account-anna", 148, 1),
            ("account-ben", 0, 2),
            ("account-cleo", 0, 2),
        ]

    def test_a_game_without_its_series_row_is_refused(self, migrated):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, played("first", 2))

    def test_the_moved_checks_guard_the_series_row_and_leave_the_tables_row(self, migrated):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text("UPDATE series SET deals = 13 WHERE table_id = 'first'"))
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text("UPDATE series SET kontra_reach = 'never' WHERE table_id = 'first'"))
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text("UPDATE tables SET series_number = 0 WHERE id = 'first'"))

    def test_a_series_in_flight_deals_its_next_game_on_its_row(self, migrated):
        before = record_of(migrated, "second")
        assert before.series == Series(LENGTH, 3, number=2)

        with PostgresTableTransactions(migrated).begin() as transaction:
            transaction.save_table(replace(before, series=Series(LENGTH, 4, number=2)), played_at=None)

        assert series_row(migrated, "second", 2)[1] == 4
        assert series_row(migrated, "second", 1)[1] == LENGTH

    def test_a_standing_proposal_stays_on_its_row_and_a_third_yes_ends_the_series(self, migrated, service):
        assert record_of(migrated, "proposed").series.end_proposal == EndProposal(1, 2)

        answer = service.agree_to_end_series(PEOPLE[3], SeriesEndCommand("yes-3", "proposed"), ALL_THREE)

        assert answer.refusal is None
        assert series_row(migrated, "proposed", 1)[2:5] == (True, None, None)

    def test_a_pending_bock_round_doubles_the_next_game_and_the_end_of_the_series_lapses_it(self, migrated, service):
        before = record_of(migrated, "bocked")
        assert (before.bock, bock_factor_of(before)) == (BockRounds((3,), 1), 2)

        service.agree_to_end_series(PEOPLE[3], SeriesEndCommand("yes-3", "bocked"), ALL_THREE)

        assert record_of(migrated, "bocked").bock == BockRounds.start()
        assert series_row(migrated, "bocked", 1)[5:7] == ([], 0)

    def test_an_early_ended_series_stays_ended_while_the_next_series_takes_its_own_row_and_proposal(
        self, migrated, service
    ):
        assert record_of(migrated, "early").series == Series(LENGTH, 7, number=2, ended_early=True)
        for seat, person in PEOPLE.items():
            service.start_new_series(person, NewSeriesCommand(f"new-{seat}", "early", 2), ALL_THREE)

        assert service.deal_next(TableId("early"), nullcontext(ALL_THREE)) is True
        dealt = record_of(migrated, "early")
        with PostgresTableTransactions(migrated).begin() as transaction:
            transaction.save_table(
                replace(dealt, series=replace(dealt.series, end_proposal=EndProposal(1))), played_at=None
            )

        assert numbers_of(migrated, "early") == [1, 2, 3]
        assert series_row(migrated, "early", 2)[2:5] == (True, None, None)
        assert series_row(migrated, "early", 3)[1:5] == (1, False, 1, None)


class TestAGameWhoseSeriesCannotBeMovedTo:
    def test_stops_the_migration_before_anything_is_dropped(self, unmigrated_engine):
        upgrade_to(unmigrated_engine, "0047")
        with unmigrated_engine.begin() as connection:
            # A game without its table cannot exist; replication mode lets the fixture write one.
            connection.execute(text("SET session_replication_role = replica"))
            connection.execute(text(list_row(table_id="'orphan'")))

        with pytest.raises(DBAPIError, match="has no row to move to"):
            migrate(unmigrated_engine)

        assert only_row(
            unmigrated_engine,
            text(
                "SELECT count(*) FROM information_schema.columns"
                " WHERE table_name = 'tables' AND column_name = 'series_length'"
            ),
        ) == (1,)


def constraints_of(engine):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT conrelid::regclass::text AS relation, conname, pg_get_constraintdef(oid) AS definition"
                " FROM pg_constraint WHERE conrelid IN ('tables'::regclass, 'series'::regclass, 'game_list'::regclass)"
                " AND contype IN ('c', 'f', 'p', 'u') ORDER BY 1, 2"
            )
        ).all()


def test_the_migrated_constraints_of_the_series_the_tables_and_the_games_are_the_ones_the_schema_declares(
    unmigrated_engine,
):
    migrate(unmigrated_engine)
    with created_database() as declared_url:
        declared_engine = create_store_engine(declared_url)
        try:
            metadata.create_all(declared_engine)

            assert constraints_of(unmigrated_engine) == constraints_of(declared_engine)
        finally:
            declared_engine.dispose()
