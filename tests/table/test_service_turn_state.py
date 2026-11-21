"""A member's statement about its turns, kept on the chair it sits at: refused without a seat, replaced by the next
statement, dropped with the seat and silent about the table's version.
"""

import random
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest

from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.records import Actor, CreateTable, OccupantKind, SendAway, TableId, TurnStatement
from skat.table.service import TableService
from skat.table.turn_state import THINKING_CAP_SECONDS, TurnStateView
from skat.table.views import turn_seat_of
from tests.support.fake_tables import FakeTableStore, ServiceScene

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
MOZART = Actor(account_id="account-mozart", display_name="Mozart", kind=OccupantKind.AGENT)
DORA = Actor(account_id="account-dora", display_name="Dora")
START = datetime(2026, 11, 1, 12, tzinfo=UTC)
NOBODY = frozenset[str]()
BENS_SEAT = 2
MOZARTS_SEAT = 3


class Scene(ServiceScene):
    """Anna sits in chair 1 and Ben in chair 2 of an open table; with `dealt`, Mozart, an agent, sits in chair 3 and the
    first hand is dealt."""

    def __init__(self, *, dealt=False):
        self.store = FakeTableStore()
        self.now = START
        self.service = TableService(
            self.store,
            random_source=random.Random(1),  # noqa: S311 - seeded for a known deal
            now=lambda: self.now,
        )
        self.table_id = self.service.create(ANNA, CreateTable(command_id="command-open")).id
        self.sit(BEN, BENS_SEAT)
        if dealt:
            self.sit(MOZART, MOZARTS_SEAT)

    def statement_at(self, seat):
        return self.table.chairs[seat - 1].turn_state

    def send_away(self, agent):
        command = SendAway(f"command-{next(self.commands)}", self.table_id, agent.account_id)
        return self.service.send_away(ANNA, command, frozenset({ANNA.account_id}), is_member=True)

    def hold_runs_out(self, person):
        self.store.hold_due(self.table_id, person.account_id)
        return self.service.free_held_chair(TableId(self.table_id), person.account_id, nullcontext(True))

    def state(self, person, stopped=None, *, thinking=False):
        return self.service.set_turn_state(person.account_id, self.table_id, stopped, thinking)


def test_a_members_statement_is_kept_for_its_seat_with_the_time_it_was_made():
    scene = Scene()

    stated = scene.state(BEN, "budget_spent")

    assert (stated, scene.statement_at(BENS_SEAT)) == (True, TurnStatement("budget_spent", False, START))
    assert scene.statement_at(1) is None


def test_the_next_statement_of_a_seat_replaces_the_last_whatever_it_says():
    scene = Scene()
    scene.state(BEN, "busy")
    scene.now += timedelta(seconds=5)

    scene.state(BEN, thinking=True)
    assert scene.statement_at(BENS_SEAT) == TurnStatement(None, True, START + timedelta(seconds=5))

    scene.now += timedelta(seconds=5)
    scene.state(BEN)
    assert scene.statement_at(BENS_SEAT) == TurnStatement(None, False, START + timedelta(seconds=10))


@pytest.mark.parametrize("caller", [DORA, MOZART], ids=["a watcher", "an agent without a chair here"])
def test_a_caller_without_a_seat_is_refused_and_nothing_is_kept(caller):
    scene = Scene()

    stated = scene.state(caller, "busy")

    assert stated is False
    assert [chair.turn_state for chair in scene.table.chairs] == [None, None, None]


def test_a_member_that_stood_up_is_refused():
    scene = Scene()
    scene.stand(BEN)

    assert scene.state(BEN, "busy") is False


def test_a_statement_for_no_table_is_refused():
    scene = Scene()

    assert scene.service.set_turn_state(BEN.account_id, "0" * 32, None, False) is False
    assert scene.service.set_turn_state(BEN.account_id, "not a table", None, False) is False


def test_stating_leaves_the_tables_version_alone():
    scene = Scene()
    version = scene.table.version

    scene.state(BEN, "unavailable")
    scene.state(BEN, thinking=True)

    assert scene.table.version == version


def test_a_move_made_after_a_statement_keeps_it():
    scene = Scene(dealt=True)
    scene.state(MOZART, "busy")
    version = scene.table.version
    on_turn = {1: ANNA, BENS_SEAT: BEN, MOZARTS_SEAT: MOZART}[
        turn_seat_of(scene.service.view(ANNA, scene.table_id, NOBODY).hand)
    ]

    scene.service.take_auction_step(
        on_turn,
        AuctionCommand("command-move", scene.table_id, version, AuctionAction.PASS, None),
        NOBODY,
    )

    assert scene.table.version > version
    assert scene.statement_at(MOZARTS_SEAT) == TurnStatement("busy", False, START)


SEAT_ENDS = {
    "a stand-up": lambda scene: scene.stand(MOZART),
    "a send-away": lambda scene: scene.send_away(MOZART),
}


@pytest.mark.parametrize("end_the_seat", SEAT_ENDS.values(), ids=SEAT_ENDS.keys())
def test_the_statement_goes_when_the_seat_ends(end_the_seat):
    scene = Scene(dealt=True)
    scene.state(MOZART, "budget_spent")

    end_the_seat(scene)

    assert scene.statement_at(MOZARTS_SEAT) is None


def test_the_statement_goes_when_the_hold_of_the_chair_runs_out():
    scene = Scene()
    scene.state(BEN, "busy")

    assert scene.hold_runs_out(BEN) is True

    assert scene.statement_at(BENS_SEAT) is None


def test_whoever_sits_down_at_the_chair_next_starts_with_nothing_stated():
    scene = Scene()
    scene.state(BEN, "busy")
    scene.stand(BEN)

    scene.sit(DORA, BENS_SEAT)

    assert scene.statement_at(BENS_SEAT) is None


def chair_views(scene, viewer):
    return scene.service.view(viewer, scene.table_id, NOBODY).chairs


def test_every_viewer_is_told_the_stated_outcome_of_a_chair():
    scene = Scene()
    scene.state(BEN, "unavailable")

    told = [chair_views(scene, viewer)[BENS_SEAT - 1].turn_state for viewer in (ANNA, BEN, DORA)]

    assert told == [TurnStateView("unavailable", None)] * 3
    assert chair_views(scene, ANNA)[0].turn_state is None


def test_thinking_is_told_with_the_seconds_left_on_the_services_clock_until_the_cap():
    scene = Scene()
    scene.state(BEN, thinking=True)
    told = []

    for passed in (0, 30, THINKING_CAP_SECONDS - 1, THINKING_CAP_SECONDS):
        scene.now = START + timedelta(seconds=passed)
        told.append(chair_views(scene, ANNA)[BENS_SEAT - 1].turn_state)

    assert told == [
        TurnStateView(None, THINKING_CAP_SECONDS),
        TurnStateView(None, THINKING_CAP_SECONDS - 30),
        TurnStateView(None, 1),
        None,
    ]


def test_the_lobby_tells_the_stated_value_of_a_chair_in_the_accounts_tables_and_in_the_open_ones():
    scene = Scene()
    scene.state(BEN, thinking=True)
    scene.now = START + timedelta(seconds=20)
    held = [TableId(scene.table_id)]

    mine = scene.service.my_tables(ANNA.account_id, held, {}, 3)
    open_ones = scene.service.open_tables(DORA.account_id, held, {}, 3)

    expected = TurnStateView(None, THINKING_CAP_SECONDS - 20)
    assert [chair.turn_state for chair in mine[0].chairs] == [None, expected, None]
    assert [chair.turn_state for chair in open_ones[0].chairs] == [None, expected, None]


def test_the_statement_times_of_a_table_move_with_each_statement_and_not_with_the_version():
    scene = Scene()
    table = TableId(scene.table_id)
    assert scene.service.table_versions([table])[0].turn_statement_times == ()
    version = scene.table.version

    scene.state(BEN, "busy")
    scene.now += timedelta(seconds=5)
    scene.state(ANNA)

    [stamp] = scene.service.table_versions([table])
    assert (stamp.version, stamp.turn_statement_times) == (version, (START + timedelta(seconds=5), START))
