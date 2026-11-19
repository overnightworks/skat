import random
import threading
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from skat.engine.deal import Position, deal, positions_from
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer, Word
from skat.store.game_list import game_list
from skat.store.migrate import create_store_engine
from skat.store.schema import StepLogRewrittenError, hand_cards, options_of, series, tables
from skat.store.series import SeriesSettingsChangedError
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.ready import NewSeriesCommand
from skat.table.records import (
    Actor,
    CreateTable,
    Ending,
    HandProgress,
    Refusal,
    Series,
    SitDown,
    StandUp,
    TableId,
    TableOptions,
)
from skat.table.series_end import SeriesEndCommand
from skat.table.service import TableService
from tests.support.faulty_tables import BothReadBeforeEitherWrites, FaultyTableTransactions
from tests.support.migrations import run_in_transaction
from tests.support.played_game import after_a_game, after_the_first_game, an_entry

pytestmark = pytest.mark.postgres

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
THIRD_PLAYER = Actor(account_id="account-third", display_name="Cleo")
PEOPLE = {1: OPENER, 2: VISITOR, 3: THIRD_PLAYER}
ALL_THREE = frozenset(person.account_id for person in PEOPLE.values())


def read(transactions, table_id):
    with transactions.begin() as transaction:
        return transaction.table(TableId(table_id))


def series_of(transactions, table_id):
    return read(transactions, table_id).series


def pass_the_hand_in(service, transactions, table_id):
    record = read(transactions, table_id)
    by_position = {position: PEOPLE[seat] for seat, position in positions_from(record.dealer).items()}
    for step, position in enumerate((Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND)):
        command = AuctionCommand(
            f"pass-{record.version}-{step}", table_id, record.version + step, AuctionAction.PASS, None
        )
        assert service.take_auction_step(by_position[position], command, frozenset()).refusal is None


@pytest.fixture
def table_id(service):
    """A series of three games, its first game dealt by the last sit."""
    table_id = service.create(OPENER, CreateTable(command_id="command-open", series_length=3)).id
    service.sit(VISITOR, SitDown("command-visitor", table_id, 2), frozenset())
    service.sit(THIRD_PLAYER, SitDown("command-third", table_id, 3), frozenset())
    return table_id


def test_a_restart_between_deals_keeps_the_count_and_after_the_last_game_deals_no_more(
    service, transactions, table_id, database_url
):
    assert series_of(transactions, table_id) == Series(3, 1)
    for expected_deals in (2, 3):
        pass_the_hand_in(service, transactions, table_id)
        restarted_engine = create_store_engine(database_url)
        restarted = TableService(PostgresTableTransactions(restarted_engine))
        assert restarted.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is True
        assert series_of(PostgresTableTransactions(restarted_engine), table_id) == Series(3, expected_deals)
        restarted_engine.dispose()

    pass_the_hand_in(service, transactions, table_id)
    restarted_engine = create_store_engine(database_url)
    try:
        restarted = TableService(PostgresTableTransactions(restarted_engine))
        assert restarted.deal_next(TableId(table_id), nullcontext(ALL_THREE)) is False
        assert series_of(PostgresTableTransactions(restarted_engine), table_id) == Series(3, 3)
    finally:
        restarted_engine.dispose()


def test_a_stand_keeps_the_count_and_the_re_sit_that_deals_adds_one(service, transactions, table_id):
    pass_the_hand_in(service, transactions, table_id)
    service.stand(THIRD_PLAYER, StandUp("command-stand", table_id), frozenset())
    assert series_of(transactions, table_id) == Series(3, 1)

    service.sit(THIRD_PLAYER, SitDown("command-sit-again", table_id, 3), frozenset())

    assert series_of(transactions, table_id) == Series(3, 2)


def test_two_checks_at_once_deal_one_hand_and_count_one_deal(service, transactions, table_id):
    pass_the_hand_in(service, transactions, table_id)
    racing = TableService(BothReadBeforeEitherWrites(transactions, 2))
    answers = []

    def check():
        answers.append(racing.deal_next(TableId(table_id), nullcontext(ALL_THREE)))

    threads = [threading.Thread(target=check), threading.Thread(target=check)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(answers) == [False, True]
    assert series_of(transactions, table_id) == Series(3, 2)


def test_a_replay_of_the_sit_that_dealt_counts_no_second_deal(service, transactions, table_id):
    service.sit(THIRD_PLAYER, SitDown("command-third", table_id, 3), frozenset())

    assert series_of(transactions, table_id) == Series(3, 1)


def rows_of(engine, table):
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table)).scalar_one()


def stored_series_and_ordinals(engine):
    with engine.connect() as connection:
        rows = connection.execute(
            select(game_list.c.series_number, game_list.c.ordinal).order_by(
                game_list.c.series_number, game_list.c.ordinal
            )
        )
        return [tuple(row) for row in rows]


@pytest.fixture
def ended_series(service, transactions, table_id):
    """The series' only game played and its last game over: one list row, no hand, nobody has tapped."""
    record = read(transactions, table_id)
    with transactions.begin() as transaction:
        transaction.save_table(
            replace(after_the_first_game(record), version=record.version + 1, series=Series(3, 3)), played_at=None
        )
    return table_id


def tap_all(service, table_id, round_name="new-series", series=1):
    for seat, person in PEOPLE.items():
        command = NewSeriesCommand(f"{round_name}-{seat}", table_id, series)
        assert service.start_new_series(person, command, ALL_THREE).refusal is None


class TestNewSeries:
    def test_the_three_taps_delete_nothing_and_the_deal_keeps_the_rows_shows_an_empty_list_and_counts_one(
        self, service, transactions, engine, ended_series
    ):
        tap_all(service, ended_series)
        assert rows_of(engine, game_list) == 1
        assert read(transactions, ended_series).series == Series(3, 3)

        assert service.deal_next(TableId(ended_series), nullcontext(ALL_THREE)) is True

        dealt = read(transactions, ended_series)
        assert (dealt.series, dealt.game_list) == (Series(3, 1, number=2), ())
        assert [chair.ready for chair in dealt.chairs] == [False, False, False]
        assert stored_series_and_ordinals(engine) == [(1, 1)]
        assert rows_of(engine, hand_cards) == 32

    def test_two_taps_leave_the_rows_and_deal_nothing(self, service, transactions, engine, ended_series):
        for seat in (1, 2):
            service.start_new_series(PEOPLE[seat], NewSeriesCommand(f"new-series-{seat}", ended_series, 1), ALL_THREE)

        assert service.deal_next(TableId(ended_series), nullcontext(ALL_THREE)) is False

        assert rows_of(engine, game_list) == 1
        assert read(transactions, ended_series).series == Series(3, 3)

    def test_a_failed_deal_keeps_the_old_list_the_count_and_the_marks_and_deals_no_hand(
        self, service, transactions, engine, ended_series
    ):
        tap_all(service, ended_series)
        before = read(transactions, ended_series)
        failing = TableService(FaultyTableTransactions(transactions, save_failure=ConnectionError("lost")))

        table_id = TableId(ended_series)
        sources = nullcontext(ALL_THREE)

        with pytest.raises(ConnectionError):
            failing.deal_next(table_id, sources)

        assert read(transactions, ended_series) == before
        assert (rows_of(engine, game_list), rows_of(engine, hand_cards)) == (1, 0)
        assert [chair.ready for chair in before.chairs] == [True, True, True]

    def test_a_restart_between_the_last_tap_and_the_deal_keeps_the_marks_and_the_deal_follows(
        self, service, ended_series, database_url
    ):
        tap_all(service, ended_series)
        restarted_engine = create_store_engine(database_url)
        try:
            restarted_transactions = PostgresTableTransactions(restarted_engine)
            assert [chair.ready for chair in read(restarted_transactions, ended_series).chairs] == [True] * 3

            assert TableService(restarted_transactions).deal_next(TableId(ended_series), nullcontext(ALL_THREE))

            assert read(restarted_transactions, ended_series).series == Series(3, 1, number=2)
            assert rows_of(restarted_engine, game_list) == 1
        finally:
            restarted_engine.dispose()

    def test_two_checks_at_once_after_the_last_tap_delete_and_deal_once(
        self, service, transactions, engine, ended_series
    ):
        tap_all(service, ended_series)
        racing = TableService(BothReadBeforeEitherWrites(transactions, 2))
        answers = []

        def check():
            answers.append(racing.deal_next(TableId(ended_series), nullcontext(ALL_THREE)))

        threads = [threading.Thread(target=check), threading.Thread(target=check)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(answers) == [False, True]
        assert read(transactions, ended_series).series == Series(3, 1, number=2)
        assert rows_of(engine, game_list) == 1

    def test_a_second_new_series_reads_number_three_and_keeps_both_earlier_series(
        self, service, transactions, engine, ended_series
    ):
        tap_all(service, ended_series)
        assert service.deal_next(TableId(ended_series), nullcontext(ALL_THREE)) is True
        record = read(transactions, ended_series)
        with transactions.begin() as transaction:
            transaction.save_table(
                replace(
                    after_the_first_game(record),
                    version=record.version + 1,
                    series=Series(3, 3, number=2),
                ),
                played_at=None,
            )
        tap_all(service, ended_series, "second-new-series", series=2)

        assert service.deal_next(TableId(ended_series), nullcontext(ALL_THREE)) is True

        assert read(transactions, ended_series).series == Series(3, 1, number=3)
        assert read(transactions, ended_series).game_list == ()
        assert stored_series_and_ordinals(engine) == [(1, 1), (2, 1)]

    def test_the_first_game_of_the_next_series_is_ordinal_one_of_its_number_and_a_restart_reads_only_it(
        self, service, transactions, engine, ended_series, database_url
    ):
        tap_all(service, ended_series)
        service.deal_next(TableId(ended_series), nullcontext(ALL_THREE))
        record = read(transactions, ended_series)
        with transactions.begin() as transaction:
            transaction.save_table(replace(after_the_first_game(record), version=record.version + 1), played_at=None)

        assert stored_series_and_ordinals(engine) == [(1, 1), (2, 1)]
        restarted_engine = create_store_engine(database_url)
        try:
            restarted = read(PostgresTableTransactions(restarted_engine), ended_series)
        finally:
            restarted_engine.dispose()
        assert (restarted.series, restarted.game_list) == (
            Series(3, 1, number=2),
            (after_the_first_game(record).game_list),
        )

    def test_a_retried_tap_after_the_deal_changes_nothing(self, service, transactions, engine, ended_series):
        tap_all(service, ended_series)
        service.deal_next(TableId(ended_series), nullcontext(ALL_THREE))
        dealt = read(transactions, ended_series)

        again = service.start_new_series(OPENER, NewSeriesCommand("new-series-1", ended_series, 1), ALL_THREE)

        assert again.refusal is None
        assert read(transactions, ended_series) == dealt
        assert rows_of(engine, game_list) == 1

    @pytest.mark.parametrize(
        ("deals", "dealt"),
        [(2, False), (3, False), (1, False), (2, True), (1, True)],
        ids=[
            "handless-inside-a-series",
            "handless-at-its-last-game",
            "handless-at-its-first-game",
            "dealt-inside-a-series",
            "dealt-with-the-same-number-and-an-empty-list",
        ],
    )
    def test_a_list_that_does_not_continue_the_stored_one_of_its_series_raises_and_changes_nothing(
        self, transactions, engine, ended_series, deals, dealt
    ):
        record = read(transactions, ended_series)
        rewritten = replace(record, version=record.version + 1, game_list=(), series=Series(3, deals))
        if dealt:
            source = random.Random(3)  # noqa: S311 - a seeded source makes the deal reproducible
            rewritten = replace(rewritten, hand=deal(source), dealer=1, progress=HandProgress())

        def save():
            with transactions.begin() as transaction:
                transaction.save_table(rewritten, played_at=None)

        with pytest.raises(StepLogRewrittenError):
            save()

        assert rows_of(engine, game_list) == 1
        assert read(transactions, ended_series) == record


@pytest.fixture
def between_games(service, transactions, table_id):
    """A series of three whose first game is played: its result stands, nobody has tapped."""
    record = read(transactions, table_id)
    with transactions.begin() as transaction:
        transaction.save_table(replace(after_the_first_game(record), version=record.version + 1), played_at=None)
    return table_id


def a_table_between_games(service, transactions):
    """Another table of three games, its first game played, seated by the same three people."""
    table_id = service.create(OPENER, CreateTable(command_id=f"open-{uuid4().hex}", series_length=3)).id
    service.sit(VISITOR, SitDown(f"visitor-{uuid4().hex}", table_id, 2), frozenset())
    service.sit(THIRD_PLAYER, SitDown(f"third-{uuid4().hex}", table_id, 3), frozenset())
    record = read(transactions, table_id)
    with transactions.begin() as transaction:
        transaction.save_table(replace(after_the_first_game(record), version=record.version + 1), played_at=None)
    return table_id


def say_yes(service, seat, table_id, service_for=None):
    return (service_for or service).agree_to_end_series(
        PEOPLE[seat], SeriesEndCommand(f"yes-{seat}-{table_id}", table_id), ALL_THREE
    )


def say_no(service, seat, table_id, service_for=None):
    return (service_for or service).refuse_to_end_series(
        PEOPLE[seat], SeriesEndCommand(f"no-{seat}-{table_id}", table_id), ALL_THREE
    )


def race(first, second):
    answers = {}

    def run(name, call):
        answers[name] = call()

    threads = [threading.Thread(target=run, args=item) for item in (("first", first), ("second", second))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return answers


class TestEndingEarly:
    def test_a_proposal_an_acceptance_and_the_early_end_read_back_across_a_restart(
        self, service, transactions, database_url, between_games
    ):
        for seat, yes_of in ((1, {1}), (2, {1, 2}), (3, None)):
            assert say_yes(service, seat, between_games).refusal is None
            restarted_engine = create_store_engine(database_url)
            try:
                read = series_of(PostgresTableTransactions(restarted_engine), between_games)
                assert (None if read.end_proposal is None else read.end_proposal.agreed) == yes_of
                assert read.ended_early is (yes_of is None)
            finally:
                restarted_engine.dispose()

    def test_the_early_end_keeps_the_list_and_clears_the_marks(self, service, transactions, engine, between_games):
        for seat in (1, 2, 3):
            say_yes(service, seat, between_games)

        ended = read(transactions, between_games)

        assert rows_of(engine, game_list) == 1
        assert [chair.ready for chair in ended.chairs] == [False, False, False]

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE series SET end_proposer = 4", id="a-proposer-beyond-the-seats"),
            pytest.param("UPDATE series SET end_proposer = 0", id="a-proposer-below-the-seats"),
            pytest.param("UPDATE series SET end_proposer = 1, end_accepter = 4", id="an-accepter-beyond-the-seats"),
            pytest.param("UPDATE series SET end_accepter = 2", id="an-accepter-without-a-proposer"),
            pytest.param(
                "UPDATE series SET end_proposer = 2, end_accepter = 2",
                id="an-accepter-equal-to-the-proposer",
            ),
            pytest.param(
                "UPDATE series SET ended_early = true, end_proposer = 1",
                id="an-ended-series-with-a-proposal",
            ),
        ],
    )
    def test_the_checks_refuse_a_row_that_is_no_proposal(self, engine, between_games, statement):
        with pytest.raises(IntegrityError):
            run_in_transaction(engine, text(statement))

    @pytest.mark.parametrize(
        "statement",
        [
            pytest.param("UPDATE series SET end_proposer = 1 WHERE table_id = 'plain'", id="a-proposal"),
            pytest.param("UPDATE series SET ended_early = true WHERE table_id = 'plain'", id="an-early-end"),
        ],
    )
    def test_the_checks_refuse_a_proposal_or_an_early_end_on_a_table_without_a_series(self, engine, statement):
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tables (id, version) VALUES ('plain', 1)"))
            connection.execute(text("INSERT INTO series (table_id, number) VALUES ('plain', 1)"))

        with pytest.raises(IntegrityError):
            run_in_transaction(engine, text(statement))

    def test_two_yes_at_once_after_a_proposal_accept_once_and_end_once(self, service, transactions, between_games):
        say_yes(service, 1, between_games)
        version = read(transactions, between_games).version
        racing = TableService(BothReadBeforeEitherWrites(transactions, 2))

        race(
            lambda: say_yes(service, 2, between_games, racing),
            lambda: say_yes(service, 3, between_games, racing),
        )

        assert series_of(transactions, between_games) == Series(3, 1, ended_early=True)
        assert read(transactions, between_games).version == version + 2

    def test_a_yes_and_a_no_at_once_serialise_to_one_of_the_two_orders(self, service, transactions, between_games):
        say_yes(service, 1, between_games)
        say_yes(service, 2, between_games)
        racing = TableService(BothReadBeforeEitherWrites(transactions, 2))

        answers = race(
            lambda: say_yes(service, 3, between_games, racing),
            lambda: say_no(service, 1, between_games, racing),
        )

        outcome = (
            series_of(transactions, between_games),
            answers["first"].refusal,
            answers["second"].refusal,
        )
        assert outcome in (
            (Series(3, 1, ended_early=True), None, Refusal.NO_PROPOSAL),
            (Series(3, 1, end_refused_by=frozenset({1})), Refusal.END_REFUSED, None),
        )

    def test_a_proposal_its_instant_and_the_refusal_that_ended_it_read_back(self, service, transactions, between_games):
        before = datetime.now(UTC)
        say_yes(service, 1, between_games)

        proposal = series_of(transactions, between_games).end_proposal
        say_no(service, 2, between_games)

        assert (proposal.proposer, proposal.agreed, before <= proposal.asked_at <= datetime.now(UTC)) == (
            1,
            frozenset({1}),
            True,
        )
        assert series_of(transactions, between_games) == Series(3, 1, end_refused_by=frozenset({2}))

    def test_a_proposal_the_release_before_wrote_reads_with_its_accepter_as_a_yes_and_its_minute_from_the_write(
        self, engine, transactions, between_games
    ):
        before = datetime.now(UTC)
        run_in_transaction(engine, text("UPDATE series SET end_proposer = 1, end_accepter = 2"))

        proposal = series_of(transactions, between_games).end_proposal

        assert (proposal.proposer, proposal.agreed, before <= proposal.asked_at <= datetime.now(UTC)) == (
            1,
            frozenset({1, 2}),
            True,
        )

    @pytest.mark.parametrize(
        ("answers", "old_release_writes", "proposer", "yes_of"),
        [
            pytest.param(
                [(say_yes, 1), (say_no, 2)],
                ["UPDATE series SET end_proposer = 1"],
                1,
                {1},
                id="an-agree-after-a-refusal",
            ),
            pytest.param(
                [(say_yes, 1), (say_yes, 2)],
                ["UPDATE series SET end_proposer = NULL, end_accepter = NULL", "UPDATE series SET end_proposer = 3"],
                3,
                {3},
                id="an-agree-by-another-seat-after-the-old-release-refused-a-proposal-with-two-yes",
            ),
            pytest.param(
                [(say_yes, 1), (say_yes, 2)],
                ["UPDATE series SET end_proposer = NULL, end_accepter = NULL", "UPDATE series SET end_proposer = 1"],
                1,
                {1},
                id="an-agree-by-the-same-seat-after-the-old-release-refused-a-proposal-with-two-yes",
            ),
            pytest.param(
                [(say_yes, 1)],
                ["UPDATE series SET end_accepter = 3"],
                1,
                {1, 3},
                id="an-accept-the-old-release-writes",
            ),
        ],
    )
    def test_a_row_the_release_before_wrote_after_this_release_reads_as_the_proposal_it_wrote(
        self, service, engine, transactions, between_games, answers, old_release_writes, proposer, yes_of
    ):
        for answer, seat in answers:
            assert answer(service, seat, between_games).refusal is None
        for statement in old_release_writes:
            run_in_transaction(engine, text(statement))

        read_back = series_of(transactions, between_games)

        assert (read_back.end_proposal.proposer, read_back.end_proposal.agreed, read_back.end_refused_by) == (
            proposer,
            yes_of,
            frozenset(),
        )

    def test_a_yes_does_not_end_the_series_after_the_old_release_replaced_a_proposal_that_had_two_yes(
        self, service, engine, transactions, between_games
    ):
        say_yes(service, 1, between_games)
        say_yes(service, 2, between_games)
        run_in_transaction(engine, text("UPDATE series SET end_proposer = NULL, end_accepter = NULL"))
        run_in_transaction(engine, text("UPDATE series SET end_proposer = 1"))

        say_yes(service, 3, between_games)

        read_back = series_of(transactions, between_games)
        assert (read_back.ended_early, read_back.end_proposal.agreed) == (False, frozenset({1, 3}))

    @pytest.mark.parametrize(
        "old_release_writes",
        [
            pytest.param("UPDATE series SET deals = deals + 1", id="a-deal"),
            pytest.param("UPDATE series SET end_proposer = 1", id="a-proposal"),
        ],
    )
    def test_a_refusal_ends_with_the_next_deal_or_proposal_the_release_before_writes(
        self, service, engine, transactions, between_games, old_release_writes
    ):
        say_yes(service, 1, between_games)
        say_no(service, 2, between_games)
        run_in_transaction(engine, text(old_release_writes))
        run_in_transaction(engine, text("UPDATE series SET end_proposer = NULL, end_accepter = NULL"))

        assert series_of(transactions, between_games).end_refused_by == frozenset()

    def test_a_restart_rearms_only_the_proposals_standing_on_a_live_tables_current_series(
        self, service, transactions, engine, between_games
    ):
        say_yes(service, 1, between_games)
        ended = a_table_between_games(service, transactions)
        say_yes(service, 1, ended)
        with transactions.begin() as transaction:
            transaction.end_table(TableId(ended), datetime(2026, 11, 9, 12, 0, tzinfo=UTC), Ending.closed("Anna"))
        moved_on = a_table_between_games(service, transactions)
        for seat in (1, 2, 3):
            say_yes(service, seat, moved_on)
        tap_all(service, moved_on)
        assert service.deal_next(TableId(moved_on), nullcontext(ALL_THREE)) is True
        run_in_transaction(
            engine,
            text(
                "UPDATE series SET ended_early = false, end_proposer = 1, end_asked_at = now() "
                "WHERE table_id = :table_id AND number = 1"
            ).bindparams(table_id=moved_on),
        )

        assert set(service.pending_end_answers()) == {between_games}

    def test_the_first_deal_of_the_next_series_clears_the_flag_and_keeps_the_rows(
        self, service, transactions, engine, between_games
    ):
        for seat in (1, 2, 3):
            say_yes(service, seat, between_games)
        tap_all(service, between_games)

        assert service.deal_next(TableId(between_games), nullcontext(ALL_THREE)) is True

        assert read(transactions, between_games).series == Series(3, 1, number=2)
        assert read(transactions, between_games).game_list == ()
        assert rows_of(engine, game_list) == 1


def kontra_options(reach):
    return TableOptions(kontra=KontraOptions(KontraSayer.ANY_OPPONENT, reach, KontraDeadline.OWN_CARD))


FIRST_SERIES_OPTIONS = kontra_options(KontraReach.KONTRA_RE_STANDINGS)
SECOND_SERIES_OPTIONS = kontra_options(KontraReach.KONTRA_RE)


def series_rows(engine, table_id):
    with engine.connect() as connection:
        return connection.execute(select(series).where(series.c.table_id == table_id).order_by(series.c.number)).all()


class TestTheSeriesRow:
    @pytest.fixture
    def first_series(self, service, transactions):
        """A table of three games opened with `FIRST_SERIES_OPTIONS`, seated, its first game played and its last
        game over: one list row with a Kontra word, no hand.
        """
        table_id = service.create(
            OPENER, CreateTable(command_id="command-open", series_length=3, options=FIRST_SERIES_OPTIONS)
        ).id
        service.sit(VISITOR, SitDown("command-visitor", table_id, 2), frozenset())
        service.sit(THIRD_PLAYER, SitDown("command-third", table_id, 3), frozenset())
        record = read(transactions, table_id)
        played = after_a_game(replace(record, game_list=()), replace(an_entry(), kontra_word=Word.KONTRA))
        with transactions.begin() as transaction:
            transaction.save_table(replace(played, series=Series(3, 3)), played_at=None)
        return table_id

    def second_series(self, transactions, table_id, options):
        record = read(transactions, table_id)
        return replace(record, series=Series(3, 1, number=2), options=options, game_list=())

    def test_a_new_table_stores_its_length_options_and_counters_on_series_one_and_a_deal_counts_there(
        self, service, transactions, engine, table_id
    ):
        pass_the_hand_in(service, transactions, table_id)
        service.deal_next(TableId(table_id), nullcontext(ALL_THREE))

        (first,) = series_rows(engine, table_id)

        assert (first.number, first.length, first.deals, first.ended_early) == (1, 3, 2, False)
        assert options_of(first) == TableOptions()

    def test_the_next_series_adds_a_row_with_its_own_options_and_leaves_the_earlier_row_as_it_was(
        self, transactions, engine, first_series
    ):
        before = series_rows(engine, first_series)

        with transactions.begin() as transaction:
            transaction.save_table(
                self.second_series(transactions, first_series, SECOND_SERIES_OPTIONS), played_at=None
            )

        first, second = series_rows(engine, first_series)
        assert first == before[0]
        assert (first.deals, options_of(first)) == (3, FIRST_SERIES_OPTIONS)
        assert (second.number, second.length, second.deals, options_of(second)) == (2, 3, 1, SECOND_SERIES_OPTIONS)
        with engine.connect() as connection:
            assert (
                connection.execute(select(tables.c.series_number).where(tables.c.id == first_series)).scalar_one() == 2
            )

    def test_a_save_that_changes_the_options_of_a_stored_series_raises_and_writes_nothing(
        self, transactions, engine, first_series
    ):
        record = read(transactions, first_series)
        before = (series_rows(engine, first_series), record)

        with pytest.raises(SeriesSettingsChangedError), transactions.begin() as transaction:
            transaction.save_table(
                replace(record, version=record.version + 1, options=SECOND_SERIES_OPTIONS), played_at=None
            )

        after = (series_rows(engine, first_series), read(transactions, first_series))
        assert after == before

    def test_a_save_that_changes_the_length_of_a_stored_series_raises(self, transactions, first_series):
        record = read(transactions, first_series)

        with pytest.raises(SeriesSettingsChangedError), transactions.begin() as transaction:
            transaction.save_table(replace(record, series=Series(6, 3)), played_at=None)

    def test_an_ended_table_reads_the_last_series_with_games_under_the_options_it_was_played_with(
        self, service, transactions, stored, first_series
    ):
        with transactions.begin() as transaction:
            transaction.save_table(
                self.second_series(transactions, first_series, SECOND_SERIES_OPTIONS), played_at=None
            )
            transaction.end_table(
                TableId(first_series), datetime(2026, 11, 9, 12, 0, tzinfo=UTC), Ending.closed("Anna")
            )

        last = stored(transactions, first_series).last_series

        assert (last.number, last.options, len(last.game_list)) == (1, FIRST_SERIES_OPTIONS, 1)
        ended = service.view(OPENER, first_series, frozenset()).ended
        assert [(each.account_id, each.total, each.place) for each in ended.standings] == [
            (OPENER.account_id, 136, 1),
            (VISITOR.account_id, 0, 2),
            (THIRD_PLAYER.account_id, 0, 2),
        ]

    def test_an_ended_table_that_finished_no_game_has_no_last_series(self, service, transactions, stored, table_id):
        with transactions.begin() as transaction:
            transaction.end_table(TableId(table_id), datetime(2026, 11, 9, 12, 0, tzinfo=UTC), Ending.closed("Anna"))

        assert stored(transactions, table_id).last_series is None
