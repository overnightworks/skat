import threading

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from skat.store.migrate import MIGRATIONS_DIRECTORY, DatabaseNotAtHeadError, create_store_engine, migrate, require_head
from skat.store.tables import metadata

pytestmark = pytest.mark.postgres

STORE_TABLES = {"tables", "chairs", "receipts", "hand_cards", "auction_actions"}


@pytest.fixture
def engine(unmigrated_database_url):
    engine = create_store_engine(unmigrated_database_url)
    yield engine
    engine.dispose()


def _run_in_transaction(engine, statement):
    with engine.begin() as connection:
        connection.execute(statement)


def table_names(engine):
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_migrating_an_empty_database_creates_every_table_the_store_writes_to(engine):
    migrate(engine)

    assert table_names(engine) == STORE_TABLES


def test_the_migrated_schema_is_the_one_the_store_writes_to(engine):
    migrate(engine)

    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []


def test_migrating_twice_changes_nothing(engine):
    migrate(engine)
    with engine.connect() as connection:
        before = connection.execute(text("SELECT version_num FROM alembic_version")).all()

    migrate(engine)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).all() == before
    assert table_names(engine) == STORE_TABLES


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param("UPDATE tables SET dealer = 4", id="dealer-above-three"),
        pytest.param("UPDATE tables SET dealer = 0", id="dealer-below-one"),
        pytest.param("INSERT INTO hand_cards VALUES ('t', 'swords', 'ace', 'skat')", id="unknown-suit"),
        pytest.param("INSERT INTO hand_cards VALUES ('t', 'hearts', 'one', 'skat')", id="unknown-rank"),
        pytest.param("INSERT INTO hand_cards VALUES ('t', 'hearts', 'ace', 'dealer')", id="unknown-holder"),
        pytest.param("INSERT INTO hand_cards VALUES ('missing', 'hearts', 'ace', 'skat')", id="unknown-table"),
    ],
)
def test_the_migrated_schema_refuses_a_dealer_or_a_card_outside_the_game(engine, statement):
    migrate(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO tables (id, version) VALUES ('t', 1)"))

    refused = text(statement)
    with pytest.raises(IntegrityError):
        _run_in_transaction(engine, refused)


def test_the_migrated_schema_holds_each_card_once_per_table(engine):
    migrate(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO tables (id, version) VALUES ('t', 1)"))
        connection.execute(text("INSERT INTO hand_cards VALUES ('t', 'hearts', 'ace', 'skat')"))

    refused = text("INSERT INTO hand_cards VALUES ('t', 'hearts', 'ace', 'forehand')")
    with pytest.raises(IntegrityError):
        _run_in_transaction(engine, refused)


def test_two_migrations_at_once_serialise_and_both_succeed(unmigrated_database_url):
    engines = [create_store_engine(unmigrated_database_url) for _ in range(2)]
    failures: list[BaseException] = []
    start = threading.Barrier(2)

    def run(engine):
        start.wait()
        try:
            migrate(engine)
        except BaseException as failure:
            failures.append(failure)

    threads = [threading.Thread(target=run, args=(engine,)) for engine in engines]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    with engines[0].connect() as connection:
        assert len(connection.execute(text("SELECT version_num FROM alembic_version")).all()) == 1
    for engine in engines:
        engine.dispose()


def upgrade_to(engine, revision):
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


class TestFromAHandAtRevisionThree:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0003 holding a table with a hand, then taken to head."""
        upgrade_to(engine, "0003")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 3, 2)"))
            connection.execute(text("INSERT INTO hand_cards VALUES ('t', 'hearts', 'ace', 'skat')"))
        migrate(engine)
        return engine

    def test_keeps_the_table_and_its_hand(self, migrated):
        with migrated.connect() as connection:
            dealer = connection.execute(text("SELECT dealer FROM tables WHERE id = 't'")).scalar_one()
            cards = connection.execute(text("SELECT count(*) FROM hand_cards")).scalar_one()

        assert (dealer, cards) == (2, 1)
        assert table_names(migrated) == STORE_TABLES

    def test_accepts_a_bid_with_its_value(self, migrated):
        _run_in_transaction(migrated, text("INSERT INTO auction_actions VALUES ('t', 1, 'middlehand', 'bid', 18)"))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM auction_actions")).scalar_one() == 1

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("INSERT INTO auction_actions VALUES ('t', 1, 'dealer', 'bid', 18)", id="unknown-position"),
            pytest.param("INSERT INTO auction_actions VALUES ('t', 1, 'forehand', 'raise', 18)", id="unknown-action"),
            pytest.param("INSERT INTO auction_actions VALUES ('t', 1, 'forehand', 'bid', NULL)", id="bid-no-value"),
            pytest.param("INSERT INTO auction_actions VALUES ('t', 1, 'forehand', 'hold', 18)", id="hold-with-value"),
            pytest.param("INSERT INTO auction_actions VALUES ('t', 1, 'forehand', 'pass', 18)", id="pass-with-value"),
            pytest.param("INSERT INTO auction_actions VALUES ('t', 1, 'forehand', 'play', 18)", id="play-with-value"),
            pytest.param("INSERT INTO auction_actions VALUES ('t', 1, 'forehand', 'bid', 17)", id="below-the-lowest"),
            pytest.param("INSERT INTO auction_actions VALUES ('t', 1, 'forehand', 'bid', 265)", id="above-the-highest"),
            pytest.param("INSERT INTO auction_actions VALUES ('gone', 1, 'forehand', 'bid', 18)", id="unknown-table"),
        ],
    )
    def test_the_checks_refuse_a_row_that_is_no_auction_step(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)

    def test_the_schema_holds_each_ordinal_once_per_table(self, migrated):
        _run_in_transaction(migrated, text("INSERT INTO auction_actions VALUES ('t', 1, 'middlehand', 'bid', 18)"))
        duplicate = text("INSERT INTO auction_actions VALUES ('t', 1, 'forehand', 'hold', NULL)")

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, duplicate)


class TestRequireHead:
    def test_accepts_a_database_at_head(self, engine):
        migrate(engine)

        require_head(engine)

    def test_refuses_an_unmigrated_database_and_says_which_command_fixes_it(self, engine):
        with pytest.raises(DatabaseNotAtHeadError, match="skat migrate"):
            require_head(engine)

    def test_refuses_a_database_at_an_older_revision(self, engine):
        migrate(engine)
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'older'"))

        with pytest.raises(DatabaseNotAtHeadError, match="older"):
            require_head(engine)
