"""An agent seated at a table reads its view from the service, and each committed change that raised the table's
version tells the agents seated after it.
"""

import itertools
import random
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from skat.engine.deal import Position
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.member_place import Acceptance, InvitationRequest
from skat.table.playing import AgreeToGiveUpCommand
from skat.table.ready import ReadyCommand
from skat.table.records import (
    Actor,
    CreateTable,
    EndProposal,
    HandProgress,
    OccupantKind,
    SitDown,
    StandUp,
    TableId,
)
from skat.table.series_end import SeriesEndCommand
from skat.table.service import TableService
from tests.support.fake_tables import FakeTableStore
from tests.support.played_game import asked_by_the_declarer, between_games, table_in, with_agents

START = datetime(2026, 11, 1, 12, tzinfo=UTC)
NOBODY = frozenset[str]()
ANNA = Actor(account_id="account-anna", display_name="Anna")
MOZART = Actor(account_id="account-mozart", display_name="Mozart", kind=OccupantKind.AGENT)
BACH = Actor(account_id="account-bach", display_name="Bach", kind=OccupantKind.AGENT)
WATCHER = Actor(account_id="account-watcher", display_name="Watcher")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
UNKNOWN_TABLE = "0" * 32


class Scene:
    """A service on a store; every signal it tells is kept with each agent's view as the store showed it then."""

    def __init__(self, seed=1):
        self.store = FakeTableStore()
        self.commands = itertools.count(1)
        numbers = itertools.count(1)
        self.service = TableService(
            self.store,
            new_table_id=lambda: TableId(f"{next(numbers):032x}"),
            random_source=random.Random(seed),  # noqa: S311 - a seeded source makes the deal reproducible
            now=lambda: START,
        ).with_view_signal(self._record_signal)
        self.signals = []

    def _record_signal(self, table_id, accounts):
        shown = {account: self.view_of(account, table_id.value) for account in sorted(accounts)}
        self.signals.append((table_id.value, accounts, shown))

    def view_of(self, account, table_id=None):
        return self.service.member_view(account, table_id or self.table_id, NOBODY)

    def command_id(self):
        return f"command-{next(self.commands)}"

    def seat_three(self, second=MOZART, third=BACH):
        self.table_id = self.service.create(ANNA, CreateTable(command_id="command-open")).id
        self.service.sit(second, SitDown(self.command_id(), self.table_id, 2), NOBODY)
        self.service.sit(third, SitDown(self.command_id(), self.table_id, 3), NOBODY)
        self.signals.clear()
        return self

    def put(self, record):
        """The table as the record says, with the time a dealt table keeps."""
        self.table_id = record.id.value
        self.store.tables[self.table_id] = record
        self.store.last_played_at[self.table_id] = START
        return self

    @property
    def table(self):
        return self.store.tables[self.table_id]

    def waiting_agent(self):
        return next(agent for agent in (MOZART, BACH) if self.view_of(agent.account_id).awaits_you)


@pytest.fixture
def scene():
    return Scene().seat_three()


class TestTheViewOfAMember:
    def test_a_seated_account_reads_the_table_as_its_own_chair_sees_it_with_the_tables_version_as_revision(self, scene):
        member = scene.view_of(MOZART.account_id)

        assert member.view.version == scene.table.version
        assert [chair.is_mine for chair in member.view.chairs] == [False, True, False]

    def test_the_seat_on_turn_is_awaited_and_the_others_are_not(self, scene):
        awaiting = [scene.view_of(actor.account_id).awaits_you for actor in (ANNA, MOZART, BACH)]

        assert awaiting.count(True) == 1

    @pytest.mark.parametrize(
        "account",
        [pytest.param(WATCHER.account_id, id="without-a-chair"), pytest.param("", id="no-account")],
    )
    def test_an_account_without_a_chair_has_no_view(self, scene, account):
        assert scene.view_of(account) is None

    @pytest.mark.parametrize(
        "table_id", [pytest.param(UNKNOWN_TABLE, id="unknown"), pytest.param("not-an-id", id="malformed")]
    )
    def test_a_table_that_is_not_there_has_no_view(self, scene, table_id):
        assert scene.view_of(MOZART.account_id, table_id) is None

    def test_an_ended_table_has_no_view(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
        scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
        scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 60)

        assert scene.view_of(MOZART.account_id) is None


def an_actor(position):
    return Actor(account_id=f"account-{position.name.lower()}", display_name=position.name)


def auction_bid(service, actor, table_id, version):
    command = AuctionCommand("act", table_id, version, AuctionAction.BID, 18)
    return service.take_auction_step(actor, command, NOBODY)


def agree_to_give_up(service, actor, table_id, version):
    return service.agree_to_give_up(actor, AgreeToGiveUpCommand("act", table_id, version), NOBODY)


def continue_after_result(service, actor, table_id, version):
    return service.mark_ready(actor, ReadyCommand("act", table_id, 1), NOBODY)


def refuse_to_end(service, actor, table_id, version):
    return service.refuse_to_end_series(actor, SeriesEndCommand("act", table_id), NOBODY)


class TestTheAcceptedActsNoFlowDrivesRaiseTheRevision:
    """The other accepted acts of cases 1 to 7 are driven through `/mcp` by the scripted client."""

    @pytest.mark.parametrize(
        ("record", "position", "act", "awaits_after"),
        [
            pytest.param(
                asked_by_the_declarer(), Position.REARHAND, agree_to_give_up, True, id="4-agree-then-the-result"
            ),
            pytest.param(
                between_games(1, 2, 3, proposal=EndProposal(1)), Position.REARHAND, refuse_to_end, False, id="7-refuse"
            ),
        ],
    )
    def test_the_revision_rises_and_the_seat_awaits_no_more_or_the_next_step(self, record, position, act, awaits_after):
        scene = Scene().put(record)
        seat = an_actor(position)
        before = scene.view_of(seat.account_id)

        result = act(scene.service, seat, scene.table_id, scene.table.version)

        after = scene.view_of(seat.account_id)
        assert (before.awaits_you, result.refusal) == (True, None)
        assert after.view.version > before.view.version
        assert after.awaits_you is awaits_after

    def test_the_same_act_again_raises_nothing(self):
        scene = Scene().put(between_games(2, 3))
        seat = an_actor(Position.MIDDLEHAND)
        continue_after_result(scene.service, seat, scene.table_id, 0)
        revision = scene.view_of(seat.account_id).view.version

        again = continue_after_result(scene.service, seat, scene.table_id, 0)

        assert (again.refusal, scene.view_of(seat.account_id).view.version) == (None, revision)

    def test_a_refused_act_raises_nothing(self):
        scene = Scene().put(table_in(HandProgress()))
        seat = an_actor(Position.MIDDLEHAND)
        revision = scene.view_of(seat.account_id).view.version

        refused = auction_bid(scene.service, seat, scene.table_id, revision + 1)

        assert (refused.refusal is not None, scene.view_of(seat.account_id).view.version) == (True, revision)


class TestTheSignalOfACommit:
    def test_a_persons_accepted_move_tells_both_agents_once_after_it_committed(self, scene):
        mover = next(actor for actor in (ANNA, MOZART, BACH) if scene.view_of(actor.account_id).awaits_you)
        version = scene.table.version

        result = auction_bid(scene.service, mover, scene.table_id, version)

        assert result.refusal is None
        assert [(table, accounts) for table, accounts, _ in scene.signals] == [
            (scene.table_id, {MOZART.account_id, BACH.account_id})
        ]
        assert {member.view.version for member in scene.signals[0][2].values()} == {version + 1}

    def test_a_refused_move_a_replay_and_an_unchanged_mark_tell_nobody_after_an_accepted_one_told_the_agents(self):
        scene = Scene().put(with_agents(between_games(2, 3), 2, 3))
        seat = an_actor(Position.MIDDLEHAND)

        accepted = continue_after_result(scene.service, seat, scene.table_id, 0)

        assert accepted.refusal is None
        assert [accounts for _, accounts, _ in scene.signals] == [{"account-rearhand", "account-forehand"}]
        scene.signals.clear()

        stale = scene.service.take_auction_step(
            seat, AuctionCommand("stale", scene.table_id, 99, AuctionAction.BID, 18), NOBODY
        )
        replay = continue_after_result(scene.service, seat, scene.table_id, 0)
        second_tap = scene.service.mark_ready(seat, ReadyCommand("another", scene.table_id, 1), NOBODY)

        assert (stale.refusal is not None, replay.refusal, second_tap.refusal) == (True, None, None)
        assert scene.signals == []

    def test_a_sit_that_deals_tells_every_agent_seated_after_it_the_sitter_included(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
        scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
        scene.signals.clear()

        scene.service.sit(BACH, SitDown("command-bach", scene.table_id, 3), NOBODY)

        assert [accounts for _, accounts, _ in scene.signals] == [{MOZART.account_id, BACH.account_id}]

    def test_a_person_standing_up_tells_the_agents_still_seated(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
        scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
        scene.signals.clear()

        scene.service.stand(ANNA, StandUp("command-stand", scene.table_id), NOBODY)

        assert [accounts for _, accounts, _ in scene.signals] == [{MOZART.account_id}]

    def test_the_deal_after_the_third_continue_tells_the_agents_seated_at_the_new_hand(self):
        scene = Scene().put(with_agents(between_games(1, 2, 3), 2, 3))
        everyone = frozenset(chair.occupant.account_id for chair in scene.table.chairs)

        dealt = scene.service.deal_next(TableId(scene.table_id), nullcontext(everyone))

        assert dealt is True
        assert [
            (accounts, {member.view.version for member in shown.values()}) for _, accounts, shown in scene.signals
        ] == [({"account-rearhand", "account-forehand"}, {scene.table.version})]

    def test_a_deal_that_dealt_nothing_tells_nobody(self, scene):
        assert scene.service.deal_next(TableId(scene.table_id), nullcontext(NOBODY)) is False
        assert scene.signals == []

    def test_a_freed_chair_tells_the_agents_still_seated_and_not_the_one_it_freed(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
        scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
        scene.service.sit(BACH, SitDown("command-bach", scene.table_id, 3), NOBODY)
        scene.put(replace(scene.table, hand=None, dealer=None))
        scene.signals.clear()

        freed = scene.service.free_chair(TableId(scene.table_id), MOZART.account_id, nullcontext(True))

        assert freed is True
        assert [accounts for _, accounts, _ in scene.signals] == [{BACH.account_id}]

    def test_a_chair_not_freed_tells_nobody(self, scene):
        assert scene.service.free_chair(TableId(scene.table_id), MOZART.account_id, nullcontext(False)) is False
        assert scene.signals == []

    def test_an_accepted_invitation_tells_the_agents_seated_after_it(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
        scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
        request = InvitationRequest(
            BACH.account_id, ANNA.account_id, ANNA.account_id, datetime(2026, 11, 2, tzinfo=UTC)
        )
        offer = scene.service.invite_agent(TableId(scene.table_id), request)
        scene.signals.clear()

        scene.service.accept_invitation(
            BACH, ANNA.account_id, Acceptance(scene.table_id, offer.id, offer.epoch), frozenset({ANNA.account_id})
        )

        assert [accounts for _, accounts, _ in scene.signals] == [{MOZART.account_id, BACH.account_id}]

    def test_a_refused_accept_tells_nobody(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
        scene.signals.clear()

        scene.service.accept_invitation(BACH, ANNA.account_id, Acceptance(scene.table_id, "no-offer", 0), NOBODY)

        assert scene.signals == []

    def test_a_table_no_agent_sits_at_tells_nobody(self):
        scene = Scene().seat_three(second=WATCHER, third=CLEO)
        scene.signals.clear()
        mover = next(actor for actor in (ANNA, WATCHER, CLEO) if scene.view_of(actor.account_id).awaits_you)

        auction_bid(scene.service, mover, scene.table_id, scene.table.version)

        assert scene.signals == []
