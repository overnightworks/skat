"""A vote to abort a hand against Postgres: the proposal and the aborted end across a restart, the rows the aborted hand
forgets and the deal that follows it.
"""

import pytest
from sqlalchemy import text

from skat.engine.deal import Position, positions_from
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.hand_abort import AbortVoteCommand
from skat.table.records import Actor, CreateTable, OccupantKind, SendAway, SitDown, StandUp
from skat.table.service import TableService
from tests.support.open_chairs import RAMSCH
from tests.support.stored_game import count_rows, nobody_connected, person, seated_table_id

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
    return service.send_away(
        OPENER, SendAway("command-away", table_id, MOZART.account_id), frozenset({OPENER.account_id}), is_member=True
    )


def agree(service, voter, table_id):
    return service.agree_to_abort_hand(voter, AbortVoteCommand(f"command-agree-{voter.display_name}", table_id), NOBODY)


def restarted(engine):
    return TableService(PostgresTableTransactions(engine))


class TestARestartInEachState:
    def test_the_open_chair_the_standing_proposal_and_the_aborted_end_read_back_the_same(
        self, service, engine, table_id
    ):
        send_mozart_away(service, table_id)
        read = {"open": restarted(engine).view(OPENER, table_id, NOBODY)}
        assert read["open"] == service.view(OPENER, table_id, NOBODY)

        agree(service, OPENER, table_id)
        read["proposal"] = restarted(engine).view(VISITOR, table_id, NOBODY)
        assert read["proposal"] == service.view(VISITOR, table_id, NOBODY)

        agree(service, VISITOR, table_id)
        read["aborted"] = restarted(engine).view(OPENER, table_id, NOBODY)
        assert read["aborted"] == service.view(OPENER, table_id, NOBODY)

        assert (read["proposal"].hand.abort, read["aborted"].hand, read["aborted"].aborted is not None) == (
            (1,),
            None,
            True,
        )

    def test_a_restarted_service_takes_the_second_yes_and_ends_the_hand(self, service, engine, table_id):
        send_mozart_away(service, table_id)
        agree(service, OPENER, table_id)

        ended = agree(restarted(engine), VISITOR, table_id)

        assert (ended.refusal, ended.view.aborted is not None) == (None, True)


class TestTheAbortedHand:
    def test_it_forgets_its_cards_and_steps_and_the_next_sit_deals_and_clears_the_end(self, service, engine, table_id):
        send_mozart_away(service, table_id)
        agree(service, OPENER, table_id)
        agree(service, VISITOR, table_id)

        with engine.connect() as connection:
            flags = connection.execute(text("SELECT hand_aborted, abort_yes_seats FROM tables")).one()
        assert (flags, count_rows(engine, "hand_cards")) == ((True, []), 0)

        sat = service.sit(BACH, SitDown("command-bach", table_id, MOZARTS_SEAT), NOBODY)

        assert (sat.view.aborted, sat.view.hand is not None) == (None, True)
        with engine.connect() as connection:
            flag = connection.execute(text("SELECT hand_aborted FROM tables")).scalar_one()
        assert (flag, count_rows(engine, "hand_cards")) == (False, 32)

    def test_an_aborted_ramsch_forgets_every_row_and_reads_as_aborted_never_as_passed_in(
        self, service, engine, database_url
    ):
        table_id = seated_table_id(service, RAMSCH)
        record = service.view(person("Anna"), table_id, nobody_connected())
        by_seat = {1: person("Anna"), 2: person("Ben"), 3: person("Cleo")}
        by_position = {position: by_seat[seat] for seat, position in positions_from(record.hand.dealer_seat).items()}
        version = record.version
        for position in (Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND):
            command = AuctionCommand(f"pass-{position.value}", table_id, version, AuctionAction.PASS, None)
            version = service.take_auction_step(by_position[position], command, nobody_connected()).view.version
        assert count_rows(engine, "auction_actions") == 3
        service.stand(person("Cleo"), StandUp("command-stand", table_id), nobody_connected())

        agree(service, person("Anna"), table_id)
        agree(service, person("Ben"), table_id)

        view = restarted(engine).view(person("Anna"), table_id, nobody_connected())
        assert (view.passed_in, view.aborted is not None, view.hand) == (None, True, None)
        assert [count_rows(engine, name) for name in ("hand_cards", "auction_actions", "played_cards")] == [0, 0, 0]
