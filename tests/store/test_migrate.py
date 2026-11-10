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
    "kontra_words",
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


class TestFromADealtTableAtRevisionNine:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0009 holding a dealt table, then taken to head."""
        upgrade_to(engine, "0009")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 3, 2)"))
        migrate(engine)
        return engine

    def test_the_old_table_has_no_series(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(text("SELECT series_length, series_deals FROM tables")).one()

        assert tuple(row) == (None, None)

    def test_accepts_a_series_with_its_deals(self, migrated):
        _run_in_transaction(migrated, text("UPDATE tables SET series_length = 36, series_deals = 36"))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM tables WHERE series_deals = 36")).scalar_one() == 1

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET series_length = 12", id="length-without-deals"),
            pytest.param("UPDATE tables SET series_deals = 0", id="deals-without-length"),
            pytest.param("UPDATE tables SET series_length = 0, series_deals = 0", id="no-games"),
            pytest.param("UPDATE tables SET series_length = 4, series_deals = 0", id="not-a-multiple-of-three"),
            pytest.param("UPDATE tables SET series_length = 102, series_deals = 0", id="beyond-the-largest"),
            pytest.param("UPDATE tables SET series_length = 12, series_deals = 13", id="more-deals-than-games"),
            pytest.param("UPDATE tables SET series_length = 12, series_deals = -1", id="negative-deals"),
        ],
    )
    def test_the_checks_refuse_a_row_that_is_no_series(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)


class TestFromAGameListRowAtRevisionTen:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0010 holding a game list row, then taken to head."""
        upgrade_to(engine, "0010")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 3, 2)"))
            connection.execute(text(_list_row()))
        migrate(engine)
        return engine

    def test_the_old_row_keeps_its_accounts_and_has_no_names(self, migrated):
        with migrated.connect() as connection:
            row = connection.execute(
                text("SELECT seat_1_account, seat_1_name, seat_2_name, seat_3_name FROM game_list")
            ).one()

        assert tuple(row) == ("account-anna", None, None, None)


class TestFromALiveTableAtRevisionEleven:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0011 holding a live table, then taken to head."""
        upgrade_to(engine, "0011")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('t', 1)"))
        migrate(engine)
        return engine

    def test_reads_the_table_with_no_time_since_when_nobody_was_there(self, migrated):
        with migrated.connect() as connection:
            assert connection.execute(text("SELECT empty_since FROM tables")).scalar_one() is None

    def test_stores_a_time_on_a_live_and_on_an_ended_table(self, migrated):
        _run_in_transaction(migrated, text("UPDATE tables SET empty_since = now()"))
        _run_in_transaction(
            migrated, text("UPDATE tables SET ended_at = now(), end_reason = 'empty', empty_seconds = 1800")
        )

        with migrated.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM tables WHERE empty_since IS NOT NULL")).scalar_one() == 1
            )


class TestFromALiveAndAnEndedTableAtRevisionTwelve:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0012 holding a live and an ended table, then taken to head."""
        upgrade_to(engine, "0012")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('live', 1)"))
            connection.execute(
                text(
                    "INSERT INTO tables (id, version, ended_at, end_reason, empty_seconds)"
                    " VALUES ('ended', 2, now(), 'empty', 1800)"
                )
            )
        migrate(engine)
        return engine

    def test_both_tables_read_the_switch_off(self, migrated):
        with migrated.connect() as connection:
            rows = connection.execute(text("SELECT id, show_running_points FROM tables ORDER BY id")).all()

        assert [tuple(row) for row in rows] == [("ended", False), ("live", False)]

    def test_accepts_the_switch_on(self, migrated):
        _run_in_transaction(migrated, text("UPDATE tables SET show_running_points = true WHERE id = 'live'"))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT show_running_points FROM tables WHERE id = 'live'")).scalar_one()

    def test_refuses_a_missing_switch(self, migrated):
        refused = text("UPDATE tables SET show_running_points = NULL")

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)


class TestFromALiveTableAndAGameAtRevisionThirteen:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0013 holding a table in play and a game list row, then taken to head."""
        upgrade_to(engine, "0013")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 3, 2)"))
            connection.execute(text(_list_row()))
        migrate(engine)
        return engine

    def test_the_table_plays_without_kontra_and_the_row_names_no_word(self, migrated):
        with migrated.connect() as connection:
            options = connection.execute(text("SELECT kontra_sayer, kontra_reach, kontra_deadline FROM tables")).one()
            word = connection.execute(text("SELECT kontra_word FROM game_list")).scalar_one()

        assert (tuple(options), word) == ((None, None, None), None)

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    def test_accepts_the_three_options_and_a_word_of_the_hand(self, migrated):
        _run_in_transaction(
            migrated,
            text(
                "UPDATE tables SET kontra_sayer = 'bidders-only', kontra_reach = 'up-to-hirsch',"
                " kontra_deadline = 'own-card'"
            ),
        )
        _run_in_transaction(migrated, text("INSERT INTO kontra_words VALUES ('t', 1, 'forehand', 'kontra', 0)"))
        _run_in_transaction(migrated, text("UPDATE game_list SET kontra_word = 'hirsch'"))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM kontra_words")).scalar_one() == 1

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET kontra_sayer = 'any-opponent'", id="one-option-alone"),
            pytest.param(
                "UPDATE tables SET kontra_sayer = 'any-opponent', kontra_reach = 'kontra-re'", id="two-options-alone"
            ),
            pytest.param(
                "UPDATE tables SET kontra_sayer = 'anyone', kontra_reach = 'kontra-re', kontra_deadline = 'own-card'",
                id="unknown-sayer",
            ),
            pytest.param(
                "UPDATE tables SET kontra_sayer = 'any-opponent', kontra_reach = 'all', kontra_deadline = 'own-card'",
                id="unknown-reach",
            ),
            pytest.param(
                "UPDATE tables SET kontra_sayer = 'any-opponent', kontra_reach = 'kontra-re',"
                " kontra_deadline = 'never'",
                id="unknown-deadline",
            ),
            pytest.param("UPDATE game_list SET kontra_word = 'bock'", id="unknown-list-word"),
            pytest.param("INSERT INTO kontra_words VALUES ('t', 1, 'dealer', 'kontra', 0)", id="unknown-position"),
            pytest.param("INSERT INTO kontra_words VALUES ('t', 1, 'forehand', 'bock', 0)", id="unknown-word"),
            pytest.param("INSERT INTO kontra_words VALUES ('t', 0, 'forehand', 'kontra', 0)", id="ordinal-below-one"),
            pytest.param("INSERT INTO kontra_words VALUES ('t', 5, 'forehand', 'kontra', 0)", id="ordinal-above-four"),
            pytest.param(
                "INSERT INTO kontra_words VALUES ('t', 1, 'forehand', 'kontra', 30)", id="after-the-last-card"
            ),
            pytest.param(
                "INSERT INTO kontra_words VALUES ('t', 1, 'forehand', 'kontra', -1)", id="before-the-first-card"
            ),
            pytest.param("INSERT INTO kontra_words VALUES ('gone', 1, 'forehand', 'kontra', 0)", id="unknown-table"),
        ],
    )
    def test_the_checks_refuse_what_is_no_kontra_option_or_word(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)


class TestFromALiveTableAndAGameAtRevisionFourteen:
    @pytest.fixture
    def migrated(self, engine):
        """A database at 0014 holding a table in play and a game list row, then taken to head."""
        upgrade_to(engine, "0014")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version, dealer) VALUES ('t', 3, 2)"))
            connection.execute(text(_list_row()))
        migrate(engine)
        return engine

    def test_the_table_plays_without_bock_and_holds_no_pending_game_and_the_old_row_has_factor_1(self, migrated):
        with migrated.connect() as connection:
            options = connection.execute(text("SELECT bock_triggers, bock_overlap, bock_rounds FROM tables")).one()
            factor = connection.execute(text("SELECT bock_factor FROM game_list")).scalar_one()

        assert (tuple(options), factor) == ((None, None, []), 1)

    def test_the_migrated_schema_is_the_one_the_store_writes_to(self, migrated):
        with migrated.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), metadata) == []

    def test_accepts_the_options_the_pending_games_and_a_factor_with_a_score_beyond_a_smallint(self, migrated):
        _run_in_transaction(
            migrated,
            text(
                "UPDATE tables SET bock_triggers = ARRAY['re', 'schwarz'], bock_overlap = 'multiply',"
                " bock_rounds = ARRAY[1, 3]"
            ),
        )
        _run_in_transaction(migrated, text("UPDATE game_list SET bock_factor = 8, score = -61440"))

        with migrated.connect() as connection:
            assert connection.execute(text("SELECT bock_rounds FROM tables")).scalar_one() == [1, 3]
            assert connection.execute(text("SELECT score FROM game_list")).scalar_one() == -61440

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE tables SET bock_triggers = ARRAY['re']", id="triggers-without-an-overlap"),
            pytest.param("UPDATE tables SET bock_overlap = 'append'", id="an-overlap-without-triggers"),
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY[]::text[], bock_overlap = 'append'", id="no-trigger-at-all"
            ),
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY['double'], bock_overlap = 'append'", id="unknown-trigger"
            ),
            pytest.param("UPDATE tables SET bock_triggers = ARRAY['re'], bock_overlap = 'twice'", id="unknown-overlap"),
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY['re'], bock_overlap = 'append', bock_rounds = ARRAY[0]",
                id="a-round-with-no-game-left",
            ),
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY['re'], bock_overlap = 'append', bock_rounds = ARRAY[4]",
                id="a-round-longer-than-three-games",
            ),
            pytest.param(
                "UPDATE tables SET bock_triggers = ARRAY['re'], bock_overlap = 'append',"
                " bock_rounds = ARRAY[2, NULL]::smallint[]",
                id="a-round-without-a-count",
            ),
            pytest.param("UPDATE tables SET bock_rounds = ARRAY[3]", id="pending-games-at-a-table-without-bock"),
            pytest.param("UPDATE tables SET bock_rounds = NULL", id="no-pending-list"),
            pytest.param("UPDATE game_list SET bock_factor = 0", id="factor-zero"),
            pytest.param("UPDATE game_list SET bock_factor = 3", id="factor-not-a-power-of-two"),
        ],
    )
    def test_the_checks_refuse_what_is_no_bock_option_or_pending_game_or_factor(self, migrated, statement):
        refused = text(statement)

        with pytest.raises(IntegrityError):
            _run_in_transaction(migrated, refused)
