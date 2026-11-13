import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import create_store_engine, migrate
from tests.support.migrations import list_row, run_in_transaction, upgrade_to

pytestmark = pytest.mark.postgres


class TestFromALiveTableAtRevisionThirtyNine:
    @pytest.fixture
    def migrated(self, unmigrated_database_url):
        """A database at 0039 holding a live table with a give-up and a game thrown down, then taken to head."""
        engine = create_store_engine(unmigrated_database_url)
        upgrade_to(engine, "0039")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, dealer, last_played_at, give_up_asked_by, give_up_declined_by)"
                    " VALUES ('t', 3, 2, now(), 'middlehand', 'rearhand')"
                )
            )
            connection.execute(text(list_row(series_number=1, ending="'thrown-down'", ended_by_seat=1)))
        migrate(engine)
        yield engine
        engine.dispose()

    def test_reads_the_give_up_as_a_give_up_with_no_open_cards(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT give_up_asked_by, give_up_declined_by, give_up_claim, give_up_agreed_by,"
                    " shortening_refused_by FROM tables"
                )
            ).one()

        assert tuple(row) == ("middlehand", "rearhand", None, None, None)

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param(
                "UPDATE tables SET give_up_declined_by = NULL, give_up_claim = 'schneider'",
                id="a-shortening-with-a-level",
            ),
            pytest.param(
                "UPDATE tables SET give_up_declined_by = NULL, give_up_claim = 'none', give_up_agreed_by = 'forehand'",
                id="a-yes-from-another-position",
            ),
            pytest.param("UPDATE tables SET shortening_refused_by = 'rearhand'", id="a-refusal"),
        ],
    )
    def test_accepts_a_shortening_a_yes_and_a_refusal(self, migrated, statement):
        run_in_transaction(migrated, text(statement))

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET give_up_claim = 'schwarzer'", id="a-level-that-is-none"),
            pytest.param(
                "UPDATE tables SET give_up_asked_by = NULL, give_up_declined_by = NULL, give_up_claim = 'none'",
                id="a-level-without-an-ask",
            ),
            pytest.param("UPDATE tables SET give_up_claim = 'none'", id="a-shortening-with-a-no"),
            pytest.param(
                "UPDATE tables SET give_up_declined_by = NULL, give_up_agreed_by = 'forehand'",
                id="a-yes-to-a-give-up",
            ),
            pytest.param(
                "UPDATE tables SET give_up_declined_by = NULL, give_up_claim = 'none',"
                " give_up_agreed_by = 'middlehand'",
                id="a-yes-from-the-asker",
            ),
            pytest.param("UPDATE tables SET shortening_refused_by = 'skat'", id="a-refuser-that-is-no-position"),
        ],
    )
    def test_refuses_what_is_no_shortening(self, migrated, statement):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(statement))

    def test_accepts_a_game_that_ended_shortened_by_the_declarer(self, migrated):
        run_in_transaction(migrated, text(list_row(series_number=1, ordinal=2, ending="'shortened'", ended_by_seat=1)))

    def test_refuses_a_shortened_game_no_seat_ended(self, migrated):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, text(list_row(series_number=1, ordinal=2, ending="'shortened'")))
