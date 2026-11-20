"""A seated player's auction plan is stored in its own table beside the chair it belongs to: it survives a restart,
leaves the version alone off turn, is read only while its account sits there, goes with the hand and the chair, and is
cleared by a deal of the release before.
"""

import pytest
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import IntegrityError

from skat.engine.bidding import Pass
from skat.engine.deal import Position, positions_from
from skat.store.auction import auction_plans
from skat.store.schema import hand_cards
from skat.store.tables import PostgresTableTransactions
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.auction_plans import AuctionPlanCommand
from skat.table.records import BidLimit, PassAhead, PlanMode, SeatPlan
from tests.support.seated_tables import NOBODY_CONNECTED, SEATED, ended_at, seated_table
from tests.support.table_rows import rows_of

pytestmark = pytest.mark.postgres

LIMIT = BidLimit(30, PlanMode.ASK)


@pytest.fixture
def table_id(service):
    return seated_table(service, "plans")


def seat_in(stored, transactions, table_id, position):
    return next(
        seat for seat, each in positions_from(stored(transactions, table_id.value).dealer).items() if each is position
    )


@pytest.fixture
def forehand_seat(stored, transactions, table_id):
    return seat_in(stored, transactions, table_id, Position.FOREHAND)


def make_plan(service, table_id, seat, plan, command_id="plan-1"):
    command = AuctionPlanCommand(command_id, table_id.value, plan)
    result = service.set_auction_plan(SEATED[seat - 1], command, NOBODY_CONNECTED)
    assert result.refusal is None
    return result


def plans_of(stored, transactions, table_id):
    return stored(transactions, table_id.value).progress.plans


def stored_rows(engine):
    with engine.connect() as connection:
        return connection.execute(select(auction_plans)).all()


@pytest.mark.parametrize(
    "plan", [LIMIT, BidLimit(24, PlanMode.FIXED), PassAhead()], ids=["ask-limit", "fixed-limit", "pass-ahead"]
)
def test_a_plan_is_stored_for_its_seat_and_survives_a_restart(service, engine, stored, table_id, forehand_seat, plan):
    make_plan(service, table_id, forehand_seat, plan)

    restarted = PostgresTableTransactions(engine)

    assert plans_of(stored, restarted, table_id) == frozenset({SeatPlan(forehand_seat, plan)})


def test_a_plan_set_off_turn_leaves_the_stored_version_alone(service, transactions, stored, table_id, forehand_seat):
    version = stored(transactions, table_id.value).version

    make_plan(service, table_id, forehand_seat, LIMIT)

    assert stored(transactions, table_id.value).version == version


def test_a_later_command_keeps_the_plan_and_a_clear_removes_its_row(
    service, engine, transactions, stored, table_id, forehand_seat
):
    make_plan(service, table_id, forehand_seat, LIMIT)
    table = stored(transactions, table_id.value)
    service.take_auction_step(
        SEATED[seat_in(stored, transactions, table_id, Position.MIDDLEHAND) - 1],
        AuctionCommand("pass-middlehand", table_id.value, table.version, AuctionAction.PASS, None),
        NOBODY_CONNECTED,
    )
    assert plans_of(stored, transactions, table_id) == frozenset({SeatPlan(forehand_seat, LIMIT)})

    make_plan(service, table_id, forehand_seat, None, command_id="plan-2")

    assert stored_rows(engine) == []


def test_a_plan_whose_account_left_its_seat_is_not_read(service, engine, transactions, stored, table_id, forehand_seat):
    make_plan(service, table_id, forehand_seat, LIMIT)

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE chairs SET account_id = 'account-other', display_name = 'Other' WHERE seat = :seat"),
            {"seat": forehand_seat},
        )

    assert plans_of(stored, transactions, table_id) == frozenset()


def test_a_deal_of_the_release_before_clears_the_plans(service, engine, transactions, stored, table_id, forehand_seat):
    make_plan(service, table_id, forehand_seat, LIMIT)
    with engine.begin() as connection:
        dealt = connection.execute(select(hand_cards)).mappings().all()
        connection.execute(delete(hand_cards))
        connection.execute(insert(hand_cards), [dict(card) for card in dealt])

    assert stored_rows(engine) == []


def test_a_passed_in_hand_keeps_no_plan(service, engine, transactions, stored, table_id, forehand_seat):
    make_plan(service, table_id, forehand_seat, PassAhead())
    for position in (Position.MIDDLEHAND, Position.REARHAND):
        seat = seat_in(stored, transactions, table_id, position)
        service.take_auction_step(
            SEATED[seat - 1],
            AuctionCommand(
                f"pass-{seat}",
                table_id.value,
                stored(transactions, table_id.value).version,
                AuctionAction.PASS,
                None,
            ),
            NOBODY_CONNECTED,
        )

    table = stored(transactions, table_id.value)
    assert (table.hand, table.progress.plans, table.progress.auction[-1]) == (
        None,
        frozenset(),
        Pass(Position.FOREHAND),
    )
    assert stored_rows(engine) == []


@pytest.mark.parametrize(
    "row",
    [
        {"kind": "pass", "value": 30, "mode": None},
        {"kind": "pass", "value": None, "mode": "ask"},
        {"kind": "limit", "value": 19, "mode": "ask"},
        {"kind": "limit", "value": None, "mode": "ask"},
        {"kind": "limit", "value": 30, "mode": None},
        {"kind": "limit", "value": 30, "mode": "maybe"},
        {"kind": "stay", "value": None, "mode": None},
    ],
    ids=[
        "pass-with-a-value",
        "pass-with-a-mode",
        "off-the-ladder",
        "limit-without-a-value",
        "limit-without-a-mode",
        "unknown-mode",
        "unknown-kind",
    ],
)
def test_the_checks_reject_a_row_that_is_no_plan(engine, table_id, forehand_seat, row):
    insertion = insert(auction_plans).values(
        table_id=table_id.value, seat=forehand_seat, account_id=SEATED[forehand_seat - 1].account_id, **row
    )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(insertion)


@pytest.mark.parametrize("how", ["the-release-before-deletes-the-chairs", "the-table-ends"])
def test_ending_a_table_that_holds_a_plan_leaves_no_row(service, engine, transactions, table_id, forehand_seat, how):
    make_plan(service, table_id, forehand_seat, LIMIT)

    if how == "the-table-ends":
        ended_at(transactions, table_id)
    else:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM chairs WHERE table_id = :table"), {"table": table_id.value})

    assert rows_of(engine, table_id.value)["auction_plans"] == []
