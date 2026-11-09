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

STORE_TABLES = {
    "tables",
    "chairs",
    "receipts",
    "hand_cards",
    "auction_actions",
    "declaring_steps",
    "played_cards",
    "game_list",
}


_PUT_BACK = "'put-back'"
_DECLARE = "'declare'"


def _declaring_row(
    *,
    table_id="'t'",
    ordinal=1,
    action="'take'",
    first="NULL, NULL",
    second="NULL, NULL",
    game="NULL",
    hand="NULL",
    ouvert="NULL",
    announcement="NULL",
):
    values = f"{table_id}, {ordinal}, {action}, {first}, {second}, {game}, {hand}, {ouvert}, {announcement}"
    return f"INSERT INTO declaring_steps VALUES ({values})"  # noqa: S608 - only a test's fixed literals reach this text


TAKE_ROW = _declaring_row()


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


class TestFromAHandAtRevisionFour:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0004 holding a hand in its auction, then taken to head."""
        upgrade_to(engine, "0004")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 4, 2)"))
            connection.execute(text("INSERT INTO hand_cards VALUES ('t', 'hearts', 'ace', 'skat')"))
            connection.execute(text("INSERT INTO auction_actions VALUES ('t', 1, 'middlehand', 'bid', 18)"))
        migrate(engine)
        return engine

    def test_keeps_the_hand_and_the_auction(self, migrated):
        with migrated.connect() as connection:
            cards = connection.execute(text("SELECT count(*) FROM hand_cards")).scalar_one()
            bids = connection.execute(text("SELECT count(*) FROM auction_actions")).scalar_one()

        assert (cards, bids) == (1, 1)
        assert table_names(migrated) == STORE_TABLES

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param(TAKE_ROW, id="a-take"),
            pytest.param(
                "INSERT INTO declaring_steps VALUES "
                "('t', 2, 'put-back', 'hearts', 'ace', 'spades', 'ace', NULL, NULL, NULL, NULL)",
                id="a-put-back",
            ),
            pytest.param(
                "INSERT INTO declaring_steps VALUES ('t', 3, 'declare', "
                "NULL, NULL, NULL, NULL, 'null', true, false, 'none')",
                id="a-declaration",
            ),
        ],
    )
    def test_accepts_each_kind_of_step(self, migrated, statement):
        _run_in_transaction(migrated, text(statement))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM declaring_steps")).scalar_one() == 1

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param(_declaring_row(ordinal=0), id="ordinal-below-the-first"),
            pytest.param(_declaring_row(ordinal=4), id="ordinal-above-the-last"),
            pytest.param(_declaring_row(action="'reject'"), id="unknown-action"),
            pytest.param(_declaring_row(first="'hearts', 'ace'"), id="take-with-a-card"),
            pytest.param(_declaring_row(game="'herz'"), id="take-with-a-game"),
            pytest.param(_declaring_row(action=_PUT_BACK, second="'hearts', 'ace'"), id="put-back-missing-a-card"),
            pytest.param(
                _declaring_row(action=_PUT_BACK, first="'hearts', 'ace'", second="'hearts', 'ace'"),
                id="put-back-the-same-card-twice",
            ),
            pytest.param(
                _declaring_row(action=_PUT_BACK, first="'hearts', 'ace'", second="'spades', 'ace'", game="'herz'"),
                id="put-back-with-a-game",
            ),
            pytest.param(
                _declaring_row(action=_PUT_BACK, first="'lila', 'ace'", second="'spades', 'ace'"), id="unknown-suit"
            ),
            pytest.param(
                _declaring_row(action=_PUT_BACK, first="'hearts', 'one'", second="'spades', 'ace'"), id="unknown-rank"
            ),
            pytest.param(
                _declaring_row(action=_DECLARE, game="'herz'", hand="true", ouvert="false"), id="declare-partly-set"
            ),
            pytest.param(
                _declaring_row(action=_DECLARE, game="'ramsch'", hand="false", ouvert="false", announcement="'none'"),
                id="unknown-game",
            ),
            pytest.param(
                _declaring_row(action=_DECLARE, game="'herz'", hand="false", ouvert="false", announcement="'kontra'"),
                id="unknown-announcement",
            ),
            pytest.param(
                _declaring_row(
                    action=_DECLARE,
                    first="'hearts', 'ace'",
                    game="'herz'",
                    hand="false",
                    ouvert="false",
                    announcement="'none'",
                ),
                id="declare-with-a-card",
            ),
            pytest.param(_declaring_row(table_id="'gone'"), id="unknown-table"),
        ],
    )
    def test_the_checks_refuse_a_row_that_is_no_declaring_step(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)

    def test_the_schema_holds_each_ordinal_once_per_table(self, migrated):
        _run_in_transaction(migrated, text(TAKE_ROW))
        duplicate = text(TAKE_ROW)

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, duplicate)


def _played_row(*, table_id="'t'", ordinal=1, position="'forehand'", suit="'hearts'", rank="'ace'"):
    return f"INSERT INTO played_cards VALUES ({table_id}, {ordinal}, {position}, {suit}, {rank})"  # noqa: S608 - only a test's fixed literals reach this text


class TestFromAHandAtRevisionFive:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0005 holding a declared hand, then taken to head."""
        upgrade_to(engine, "0005")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 5, 2)"))
            connection.execute(text("INSERT INTO hand_cards VALUES ('t', 'hearts', 'ace', 'skat')"))
            connection.execute(text("INSERT INTO auction_actions VALUES ('t', 1, 'middlehand', 'bid', 18)"))
            connection.execute(text(TAKE_ROW))
        migrate(engine)
        return engine

    def test_keeps_the_hand_the_auction_and_the_declaring_steps(self, migrated):
        with migrated.connect() as connection:
            cards = connection.execute(text("SELECT count(*) FROM hand_cards")).scalar_one()
            bids = connection.execute(text("SELECT count(*) FROM auction_actions")).scalar_one()
            steps = connection.execute(text("SELECT count(*) FROM declaring_steps")).scalar_one()

        assert (cards, bids, steps) == (1, 1, 1)
        assert table_names(migrated) == STORE_TABLES

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param(_played_row(), id="the-first"),
            pytest.param(_played_row(ordinal=30, position="'rearhand'", suit="'spades'", rank="'jack'"), id="the-last"),
        ],
    )
    def test_accepts_a_played_card(self, migrated, statement):
        _run_in_transaction(migrated, text(statement))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM played_cards")).scalar_one() == 1

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param(_played_row(ordinal=0), id="ordinal-below-the-first"),
            pytest.param(_played_row(ordinal=31), id="ordinal-above-the-last"),
            pytest.param(_played_row(position="'skat'"), id="no-position"),
            pytest.param(_played_row(suit="'lila'"), id="unknown-suit"),
            pytest.param(_played_row(rank="'one'"), id="unknown-rank"),
            pytest.param(_played_row(table_id="'gone'"), id="unknown-table"),
        ],
    )
    def test_the_checks_refuse_a_row_that_is_no_played_card(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)

    def test_the_schema_holds_each_ordinal_once_per_table(self, migrated):
        _run_in_transaction(migrated, text(_played_row()))
        duplicate = text(_played_row(position="'middlehand'", suit="'spades'", rank="'seven'"))

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, duplicate)

    def test_the_schema_holds_each_card_once_per_table(self, migrated):
        _run_in_transaction(migrated, text(_played_row()))
        duplicate = text(_played_row(ordinal=2, position="'middlehand'"))

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, duplicate)


def _list_row(**changed):
    columns = {
        "table_id": "'t'",
        "ordinal": 1,
        "seat_1_account": "'account-anna'",
        "seat_2_account": "'account-ben'",
        "seat_3_account": "'account-cleo'",
        "declarer_seat": 1,
        "game": "'kreuz'",
        "hand": "false",
        "ouvert": "false",
        "announcement": "'none'",
        "schneider": "true",
        "schwarz": "false",
        "matadors_mit": "true",
        "matadors_count": 2,
        "won": "true",
        "bid": 18,
        "game_value": 48,
        "settled_value": 48,
        "score": 48,
        "declarer_points": 95,
        **changed,
    }
    names, values = ", ".join(columns), ", ".join(str(value) for value in columns.values())
    return f"INSERT INTO game_list ({names}) VALUES ({values})"  # noqa: S608 - only a test's fixed literals reach this text


class TestFromAPlayedCardAtRevisionSix:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0006 holding a hand with one played card, then taken to head."""
        upgrade_to(engine, "0006")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 6, 2)"))
            connection.execute(text("INSERT INTO hand_cards VALUES ('t', 'hearts', 'ace', 'skat')"))
            connection.execute(text(_played_row()))
        migrate(engine)
        return engine

    def test_keeps_the_hand_and_the_played_card(self, migrated):
        with migrated.connect() as connection:
            cards = connection.execute(text("SELECT count(*) FROM hand_cards")).scalar_one()
            plays = connection.execute(text("SELECT count(*) FROM played_cards")).scalar_one()

        assert (cards, plays) == (1, 1)
        assert table_names(migrated) == STORE_TABLES

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param(_list_row(), id="kreuz-mit-2-schneider"),
            pytest.param(
                _list_row(game="'null'", matadors_mit="NULL", matadors_count="NULL", schneider="false"), id="null"
            ),
            pytest.param(
                _list_row(game="'karo'", won="false", bid=20, game_value=18, settled_value=27, score=-54), id="overbid"
            ),
        ],
    )
    def test_accepts_a_list_entry(self, migrated, statement):
        _run_in_transaction(migrated, text(statement))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM game_list")).scalar_one() == 1

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param(_list_row(ordinal=0), id="ordinal-below-the-first"),
            pytest.param(_list_row(declarer_seat=4), id="no-seat"),
            pytest.param(_list_row(game="'lila'"), id="unknown-game"),
            pytest.param(_list_row(announcement="'maybe'"), id="unknown-announcement"),
            pytest.param(_list_row(matadors_mit="NULL", matadors_count="NULL"), id="no-matadors-outside-null"),
            pytest.param(_list_row(game="'null'"), id="matadors-in-null"),
            pytest.param(_list_row(matadors_count="NULL"), id="matadors-without-a-count"),
            pytest.param(_list_row(matadors_count=12), id="more-matadors-than-trumps"),
            pytest.param(_list_row(bid=17), id="no-bid"),
            pytest.param(_list_row(declarer_points=121), id="more-than-all-card-points"),
            pytest.param(_list_row(seat_2_account="NULL"), id="a-seat-without-its-account"),
            pytest.param(_list_row(table_id="'gone'"), id="unknown-table"),
        ],
    )
    def test_the_checks_refuse_a_row_that_is_no_list_entry(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)

    def test_the_schema_holds_each_ordinal_once_per_table(self, migrated):
        _run_in_transaction(migrated, text(_list_row()))
        duplicate = text(_list_row(score=-96))

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, duplicate)


class TestFromChairsAtRevisionSeven:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0007 holding a table with one occupied and one free chair, then taken to head."""
        upgrade_to(engine, "0007")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('t', 7)"))
            connection.execute(text("INSERT INTO chairs VALUES ('t', 1, 'account-anna', 'Anna'), ('t', 2, NULL, NULL)"))
        migrate(engine)
        return engine

    def test_no_chair_is_ready(self, migrated):
        with migrated.connect() as connection:
            assert connection.execute(text("SELECT ready FROM chairs ORDER BY seat")).scalars().all() == [False, False]

    def test_an_occupied_chair_may_be_ready(self, migrated):
        _run_in_transaction(migrated, text("UPDATE chairs SET ready = true WHERE seat = 1"))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM chairs WHERE ready")).scalar_one() == 1

    def test_the_check_refuses_a_free_chair_that_is_ready(self, migrated):
        refused = text("UPDATE chairs SET ready = true WHERE seat = 2")

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)


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


class TestFromATableAtRevisionEight:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0008 holding a table, then taken to head."""
        upgrade_to(engine, "0008")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 3, 2)"))
        migrate(engine)
        return engine

    def test_reads_the_table_as_live(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(text("SELECT ended_at, end_reason, empty_seconds FROM tables")).one()

        assert tuple(row) == (None, None, None)

    def test_accepts_an_end_with_its_time_reason_and_wait(self, migrated):
        _run_in_transaction(
            migrated, text("UPDATE tables SET ended_at = now(), end_reason = 'empty', empty_seconds = 1800")
        )

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM tables WHERE ended_at IS NOT NULL")).scalar_one() == 1

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET end_reason = 'empty', empty_seconds = 1", id="reason-without-time"),
            pytest.param("UPDATE tables SET ended_at = now(), empty_seconds = 1", id="time-without-reason"),
            pytest.param("UPDATE tables SET ended_at = now(), end_reason = 'empty'", id="empty-without-seconds"),
            pytest.param("UPDATE tables SET empty_seconds = 1", id="seconds-without-reason"),
            pytest.param(
                "UPDATE tables SET ended_at = now(), end_reason = 'closed', empty_seconds = 1", id="unknown-reason"
            ),
            pytest.param(
                "UPDATE tables SET ended_at = now(), end_reason = 'empty', empty_seconds = 0", id="no-seconds-waited"
            ),
        ],
    )
    def test_the_checks_refuse_a_row_that_is_no_end(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)
