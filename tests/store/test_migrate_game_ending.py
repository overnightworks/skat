import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.game_list import read_game_list
from skat.store.migrate import migrate
from skat.store.tables import metadata
from skat.table.game_list import GameEnding, ListEntry
from tests.support.migrations import list_row, run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


def ramsch_row(ordinal, **changed):
    columns = {
        "table_id": "'t'",
        "ordinal": ordinal,
        "seat_1_account": "'a'",
        "seat_2_account": "'b'",
        "seat_3_account": "'c'",
        "kind": "'ramsch'",
        "seat_1_points": 47,
        "seat_2_points": 40,
        "seat_3_points": 33,
        "seat_1_score": -47,
        "seat_2_score": 0,
        "seat_3_score": 0,
        "jungfrau": "false",
        **changed,
    }
    names, values = ", ".join(columns), ", ".join(str(value) for value in columns.values())
    return text(f"INSERT INTO game_list ({names}) VALUES ({values})")  # noqa: S608 - only a test's fixed literals reach this text


class TestFromAListOfEveryKindAtRevisionTwentyFour:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        """A database at 0024 holding a declared row, a row with a Kontra word and a Ramsch row, then taken to head."""
        upgrade_to(unmigrated_engine, "0024")
        with unmigrated_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('t', 3, 2, now())")
            )
            connection.execute(text(list_row()))
            connection.execute(text(list_row(ordinal=2, kontra_word="'kontra'")))
            connection.execute(ramsch_row(3))
        migrate(unmigrated_engine)
        return unmigrated_engine

    def test_every_old_row_reads_played_out_with_no_seat(self, migrated):
        with migrated.connect() as connection:
            rows = connection.execute(text("SELECT ending, ended_by_seat FROM game_list ORDER BY ordinal")).all()

        assert [tuple(row) for row in rows] == [("played-out", None)] * 3

    def test_the_store_reads_an_old_declared_entry_as_played_out_with_no_seat(self, migrated):
        with migrated.connect() as connection:
            declared = [entry for entry in read_game_list(connection, "t") if isinstance(entry, ListEntry)]

        assert [(entry.ending, entry.ended_by_seat) for entry in declared] == [(GameEnding.PLAYED_OUT, None)] * 2

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    def test_the_old_row_keeps_its_values(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(text("SELECT declarer_seat, game, score FROM game_list WHERE ordinal = 1")).one()

        assert tuple(row) == (1, "kreuz", 48)

    @pytest.mark.parametrize(
        ("ending", "seat"), [("given-up", 2), ("thrown-down", 3)], ids=["a give-up", "a throw-down"]
    )
    def test_accepts_an_ending_by_a_seat(self, migrated, ending, seat):
        run_in_transaction(migrated, text(list_row(ordinal=4, ending=f"'{ending}'", ended_by_seat=seat)))

    def test_accepts_a_played_out_game_with_no_seat(self, migrated):
        run_in_transaction(migrated, text(list_row(ordinal=4, ending="'played-out'")))

    @pytest.mark.parametrize(
        "changed",
        [
            pytest.param({"ending": "'conceded'", "ended_by_seat": 1}, id="an-unknown-token"),
            pytest.param({"ending": "'given-up'", "ended_by_seat": 0}, id="seat-0"),
            pytest.param({"ending": "'given-up'", "ended_by_seat": 4}, id="seat-4"),
            pytest.param({"ending": "'played-out'", "ended_by_seat": 1}, id="played-out-with-a-seat"),
            pytest.param({"ending": "'given-up'"}, id="given-up-without-a-seat"),
            pytest.param({"ending": "'thrown-down'"}, id="thrown-down-without-a-seat"),
        ],
    )
    def test_refuses_a_declared_row_whose_ending_and_seat_do_not_fit(self, migrated, changed):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(list_row(ordinal=4, **changed)))

    @pytest.mark.parametrize("ending", ["given-up", "thrown-down"])
    def test_refuses_a_ramsch_row_that_ends_any_other_way_than_played_out(self, migrated, ending):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, ramsch_row(4, ending=f"'{ending}'", ended_by_seat=1))
