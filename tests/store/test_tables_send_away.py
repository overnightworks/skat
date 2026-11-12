"""A table whose hand waits for a sitter against Postgres: the open chair beside a stored hand, across a restart and
under two sits at once, and the agent's book row.
"""

import threading
from datetime import timedelta

import pytest
from sqlalchemy import text

from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.records import (
    Actor,
    CreateTable,
    OccupantKind,
    Refusal,
    SeatHeld,
    SendAway,
    SitDown,
    StandUp,
    TableId,
)
from skat.table.service import TableService
from tests.support.calls import call_facts
from tests.support.faulty_tables import BothReadBeforeEitherWrites

pytestmark = pytest.mark.postgres

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
MOZART = Actor(account_id="account-mozart", display_name="Mozart", kind=OccupantKind.AGENT)
BACH = Actor(account_id="account-bach", display_name="Bach", kind=OccupantKind.AGENT)
NOBODY = frozenset[str]()
MOZARTS_SEAT = 3


@pytest.fixture
def table_id(service):
    """A dealt table where Mozart, an agent, holds chair 3."""
    table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
    service.sit(VISITOR, SitDown("command-ben", table_id, 2), NOBODY)
    service.sit(MOZART, SitDown("command-mozart", table_id, MOZARTS_SEAT), NOBODY)
    return table_id


def send_mozart_away(service, table_id):
    return service.send_away(OPENER, SendAway("command-away", table_id, MOZART.account_id), NOBODY)


def book_row(engine):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT epoch, invitation_id, owner_account, inviter_account FROM member_book WHERE agent_account = :a"
            ),
            {"a": MOZART.account_id},
        ).one()


def pass_as(service, person, table_id):
    version = service.view(person, table_id, NOBODY).version
    return service.take_auction_step(
        person,
        AuctionCommand(f"command-pass-{person.display_name}", table_id, version, AuctionAction.PASS, None),
        NOBODY,
    )


class TestAnOpenChairBesideAStoredHand:
    def test_the_chair_is_free_and_the_stored_hand_is_as_it_was(self, service, engine, table_id):
        before = service.view(OPENER, table_id, NOBODY)

        send_mozart_away(service, table_id)

        after = service.view(OPENER, table_id, NOBODY)
        assert [chair.occupant_name for chair in after.chairs] == ["Anna", "Ben", None]
        assert (after.hand.own_cards, after.hand.auction.turn_seat) == (
            before.hand.own_cards,
            before.hand.auction.turn_seat,
        )
        assert after.hand.waiting_seat == MOZARTS_SEAT

    def test_a_restart_reads_the_same_table_with_the_same_turn_and_the_hand_still_waits(
        self, service, engine, table_id
    ):
        send_mozart_away(service, table_id)
        before = service.view(OPENER, table_id, NOBODY)

        restarted = TableService(PostgresTableTransactions(engine))

        after = restarted.view(OPENER, table_id, NOBODY)
        assert after == before
        assert pass_as(restarted, OPENER, table_id).refusal is Refusal.SEAT_OPEN

    def test_a_sitter_after_a_restart_takes_the_seat_and_the_hand_moves_again(self, service, engine, table_id):
        send_mozart_away(service, table_id)
        restarted = TableService(PostgresTableTransactions(engine))

        sat = restarted.sit(BACH, SitDown("command-bach", table_id, MOZARTS_SEAT), NOBODY)

        assert sat.refusal is None
        assert sat.view.hand.waiting_seat is None


def stand_up(service, person, table_id, command_id="command-stand"):
    return service.stand(person, StandUp(command_id, table_id), NOBODY)


def stored_table(engine, table_id):
    with PostgresTableTransactions(engine).begin() as transaction:
        return transaction.table(TableId(table_id))


class TestTheSeatMarkAcrossTheStore:
    def test_a_stand_up_mid_hand_is_read_back_equal_by_a_restarted_service_and_keeps_its_leaver_to_his_chair(
        self, service, engine, table_id
    ):
        send_mozart_away(service, table_id)
        stand_up(service, VISITOR, table_id)
        marks = {SeatHeld(VISITOR.account_id, 2), SeatHeld(MOZART.account_id, MOZARTS_SEAT)}
        restarted = TableService(PostgresTableTransactions(engine))

        read = stored_table(engine, table_id)
        crossed = [
            restarted.sit(VISITOR, SitDown("command-ben-3", table_id, MOZARTS_SEAT), NOBODY).refusal,
            restarted.sit(MOZART, SitDown("command-mozart-2", table_id, 2), NOBODY).refusal,
        ]
        own = [
            restarted.sit(VISITOR, SitDown("command-ben-2", table_id, 2), NOBODY).refusal,
            restarted.sit(MOZART, SitDown("command-mozart-3", table_id, MOZARTS_SEAT), NOBODY).refusal,
        ]

        assert read.progress.seats_held == marks
        assert (crossed, own) == ([Refusal.OWN_SEAT_ONLY] * 2, [None, None])

    def test_the_refusal_of_a_sit_replays_from_its_receipt_after_a_restart(self, service, engine, table_id):
        send_mozart_away(service, table_id)
        stand_up(service, VISITOR, table_id)
        sit = SitDown("command-ben-3", table_id, MOZARTS_SEAT)
        first = service.sit(VISITOR, sit, NOBODY)

        again = TableService(PostgresTableTransactions(engine)).sit(VISITOR, sit, NOBODY)

        assert (first.refusal, again.refusal) == (Refusal.OWN_SEAT_ONLY, Refusal.OWN_SEAT_ONLY)

    def test_a_hand_passed_in_leaves_no_mark_in_any_chair(self, service, engine, table_id):
        send_mozart_away(service, table_id)
        stand_up(service, VISITOR, table_id)
        service.sit(VISITOR, SitDown("command-ben-2", table_id, 2), NOBODY)
        service.sit(MOZART, SitDown("command-mozart-3", table_id, MOZARTS_SEAT), NOBODY)
        people = {1: OPENER, 2: VISITOR, 3: MOZART}

        for _ in range(3):
            seat = service.view(OPENER, table_id, NOBODY).hand.auction.turn_seat
            assert pass_as(service, people[seat], table_id).refusal is None

        with engine.connect() as connection:
            held = connection.execute(text("SELECT held_in_hand FROM chairs ORDER BY seat")).scalars().all()
        assert (stored_table(engine, table_id).hand, held) == (None, [[], [], []])


class TestTwoSitsForTheOpenChair:
    def test_seat_exactly_one_and_refuse_the_other_as_taken(self, service, engine, table_id):
        send_mozart_away(service, table_id)
        rivals = [Actor("account-cem", "Cem"), Actor("account-dora", "Dora")]
        racing = TableService(BothReadBeforeEitherWrites(PostgresTableTransactions(engine), len(rivals)))
        results = {}

        def sit(rival):
            results[rival.display_name] = racing.sit(rival, SitDown("command-sit", table_id, MOZARTS_SEAT), NOBODY)

        threads = [threading.Thread(target=sit, args=(rival,)) for rival in rivals]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        winners = [name for name, result in results.items() if result.refusal is None]
        losers = [result for result in results.values() if result.refusal is not None]
        assert len(winners) == 1
        assert [(loser.refusal, loser.holder) for loser in losers] == [(Refusal.SEAT_TAKEN, winners[0])]
        chairs = service.view(OPENER, table_id, NOBODY).chairs
        assert [chair.occupant_name for chair in chairs] == ["Anna", "Ben", winners[0]]


class TestTheBookRow:
    def test_a_row_is_created_at_epoch_one_when_the_book_held_none(self, service, engine, table_id):
        send_mozart_away(service, table_id)

        assert tuple(book_row(engine)) == (1, None, None, None)

    def test_an_open_invitation_is_cleared_with_its_people_and_the_epoch_raised_and_the_standing_forgets_the_table(
        self, service, engine
    ):
        table_id = service.create(OPENER, CreateTable(command_id="command-open")).id
        service.sit(VISITOR, SitDown("command-ben", table_id, 2), NOBODY)
        service.invite_agent(TableId(table_id), call_facts(MOZART.account_id, OPENER.account_id), timedelta(hours=1))
        service.sit(MOZART, SitDown("command-mozart", table_id, MOZARTS_SEAT), NOBODY)

        send_mozart_away(service, table_id)

        assert tuple(book_row(engine)) == (1, None, None, None)
        assert service.standings_of(MOZART.account_id) == ()
