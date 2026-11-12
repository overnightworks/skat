"""A send-away through the table service: the chair opens at once, the agent's book row follows, a retry changes
nothing twice and the hand waits for a sitter.
"""

import copy
import itertools
import random
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.member_place import Acceptance, MemberRefusal, MembershipState, TableStanding
from skat.table.records import Actor, CreateTable, OccupantKind, Refusal, SendAway, SitDown, StandUp, TableId
from skat.table.service import CommandIdReusedError, TableService
from tests.support.calls import call_facts
from tests.support.fake_tables import FakeTableStore

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
MOZART = Actor(account_id="account-mozart", display_name="Mozart", kind=OccupantKind.AGENT)
BACH = Actor(account_id="account-bach", display_name="Bach", kind=OccupantKind.AGENT)
DORA = Actor(account_id="account-dora", display_name="Dora")
START = datetime(2026, 11, 1, 12, tzinfo=UTC)
NOBODY = frozenset[str]()
MOZARTS_SEAT = 3


class Scene:
    """Anna opened a table; Ben sat in chair 2 and Mozart, an agent, in chair 3, which dealt the first hand; without
    `agent_seated` Mozart stays away."""

    def __init__(self, *, agent_seated=True):
        self.store = FakeTableStore()
        self.now = START
        self.commands = itertools.count(1)
        self.service = TableService(
            self.store,
            random_source=random.Random(1),  # noqa: S311 - seeded for a known deal
            now=lambda: self.now,
        )
        self.told = []
        self.service = self.service.with_standing_signal(self.told.append)
        self.table_id = self.service.create(ANNA, CreateTable(command_id="command-open")).id
        self.sit(BEN, 2)
        if agent_seated:
            self.sit(MOZART, MOZARTS_SEAT)
        self.told.clear()

    @property
    def table(self):
        return self.store.tables[self.table_id]

    def sit(self, person, seat):
        return self.service.sit(person, SitDown(f"command-{next(self.commands)}", self.table_id, seat), NOBODY)

    def send_away(self, agent=MOZART, *, by=ANNA, command_id=None):
        command = SendAway(command_id or f"command-{next(self.commands)}", self.table_id, agent.account_id)
        return self.service.send_away(by, command, NOBODY)

    def step(self, person):
        command = AuctionCommand(
            f"command-{next(self.commands)}", self.table_id, self.table.version, AuctionAction.PASS, None
        )
        return self.service.take_auction_step(person, command, NOBODY)

    def book(self, agent=MOZART):
        return self.store.book.get((self.table_id, agent.account_id))

    def standing(self, agent=MOZART):
        return self.service.standings_of(agent.account_id)

    def snapshot(self):
        return copy.deepcopy((self.store.tables, self.store.book))


class TestTheChairOpensAtOnce:
    def test_in_the_running_hand_with_the_hand_as_it_was(self):
        scene = Scene()
        before = scene.table

        result = scene.send_away()

        assert result.refusal is None
        assert [chair.occupant_name for chair in result.view.chairs] == ["Anna", "Ben", None]
        assert result.view.hand.waiting_seat == MOZARTS_SEAT
        assert (scene.table.hand, replace(scene.table.progress, seats_held=frozenset()), scene.table.game_list) == (
            before.hand,
            before.progress,
            before.game_list,
        )
        assert scene.table.version == before.version + 1

    def test_outside_a_hand_and_the_next_sit_deals_when_it_fills_the_last_chair(self):
        scene = Scene(agent_seated=False)
        scene.service.stand(BEN, StandUp("command-ben-up", scene.table_id), NOBODY)
        scene.sit(MOZART, 2)
        scene.send_away()
        assert scene.table.dealer is None

        scene.sit(BEN, 2)
        result = scene.sit(DORA, 3)

        assert [chair.occupant_name for chair in result.view.chairs] == ["Anna", "Ben", "Dora"]
        assert scene.table.hand is not None

    def test_the_agent_may_sit_in_its_old_chair_again(self):
        scene = Scene()
        scene.send_away()

        again = scene.sit(MOZART, MOZARTS_SEAT)

        assert again.refusal is None
        assert again.view.hand.waiting_seat is None

    def test_the_agent_sits_only_in_its_old_chair_while_the_hand_runs_and_in_any_after_it(self):
        scene = Scene()
        scene.send_away()
        scene.service.stand(BEN, StandUp(f"command-{next(scene.commands)}", scene.table_id), NOBODY)

        into_another = scene.sit(MOZART, 2)
        into_its_own = scene.sit(MOZART, MOZARTS_SEAT)

        assert (into_another.refusal, into_its_own.refusal) == (Refusal.OWN_SEAT_ONLY, None)

    def test_neither_it_nor_a_sit_into_the_chair_counts_as_a_step_of_play(self):
        scene = Scene()
        played_at = scene.store.last_played_at[scene.table_id]
        scene.now = START + timedelta(days=3)

        scene.send_away()
        scene.sit(BACH, MOZARTS_SEAT)

        assert scene.store.last_played_at[scene.table_id] == played_at

    def test_the_table_with_a_waiting_hand_is_not_ended_for_being_empty(self):
        scene = Scene()
        scene.send_away()

        ended = scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 60)

        assert (ended, scene.table.hand is not None) == (False, True)


class TestWhileTheChairIsOpen:
    def test_a_hand_command_through_the_service_is_refused_seat_open_and_writes_nothing(self):
        scene = Scene()
        scene.send_away()
        before = scene.snapshot()

        result = scene.step(ANNA)

        assert result.refusal is Refusal.SEAT_OPEN
        assert scene.snapshot() == before

    def test_a_person_who_sits_in_the_chair_lets_the_hand_move_again(self):
        scene = Scene()
        scene.send_away()
        scene.sit(DORA, MOZARTS_SEAT)

        assert scene.step(ANNA).refusal is not Refusal.SEAT_OPEN

    def test_an_agent_accepting_its_invitation_takes_the_lowest_free_chair_of_the_running_hand(self):
        scene = Scene()
        scene.send_away()
        offer = scene.service.invite_agent(
            TableId(scene.table_id), call_facts(BACH.account_id, ANNA.account_id), timedelta(hours=1)
        )

        result = scene.service.accept_invitation(
            BACH, ANNA.account_id, Acceptance(scene.table_id, offer.id, offer.epoch), frozenset({ANNA.account_id})
        )

        assert result.refusal is None
        assert scene.table.chairs[MOZARTS_SEAT - 1].occupant.display_name == "Bach"
        assert scene.standing(BACH) == (TableStanding(TableId(scene.table_id), MembershipState.ACTIVE),)


class TestRefusals:
    @pytest.mark.parametrize(
        ("target", "refusal"),
        [
            pytest.param(BEN, Refusal.NOT_AN_AGENT, id="a-person"),
            pytest.param(BACH, Refusal.NOT_SEATED, id="an-agent-without-a-chair-here"),
        ],
    )
    def test_change_no_chair_and_no_book_row_and_tell_nobody(self, target, refusal):
        scene = Scene()
        before = scene.snapshot()

        result = scene.send_away(target)

        assert result.refusal is refusal
        assert scene.snapshot() == before
        assert scene.told == []


class TestTheBook:
    def test_an_open_invitation_is_cleared_and_the_epoch_raised(self):
        scene = Scene(agent_seated=False)
        offer = scene.service.invite_agent(
            TableId(scene.table_id), call_facts(MOZART.account_id, ANNA.account_id), timedelta(hours=1)
        )
        scene.sit(MOZART, MOZARTS_SEAT)

        scene.send_away()

        entry = scene.book()
        assert (entry.epoch, entry.invitation) == (offer.epoch + 1, None)

    def test_an_accept_with_the_old_epoch_is_stale_and_the_standing_lists_no_table(self):
        scene = Scene(agent_seated=False)
        offer = scene.service.invite_agent(
            TableId(scene.table_id), call_facts(MOZART.account_id, ANNA.account_id), timedelta(hours=1)
        )
        scene.sit(MOZART, MOZARTS_SEAT)
        scene.send_away()

        result = scene.service.accept_invitation(
            MOZART, ANNA.account_id, Acceptance(scene.table_id, offer.id, offer.epoch), frozenset({ANNA.account_id})
        )

        assert result.refusal is MemberRefusal.STALE_INVITATION
        assert scene.standing() == ()


class TestTheStandingSignal:
    def test_the_agent_is_told_once_after_the_commit_with_the_table_no_longer_in_its_standing(self):
        scene = Scene()
        shown = []
        scene.service = scene.service.with_standing_signal(
            lambda accounts: shown.append((accounts, scene.standing(MOZART)))
        )

        scene.send_away()

        assert shown == [(frozenset({MOZART.account_id}), ())]

    def test_a_replay_tells_nobody_again(self):
        scene = Scene()
        scene.send_away(command_id="command-away")
        scene.told.clear()

        scene.send_away(command_id="command-away")

        assert scene.told == []


class TestTheStandingSignalOfAnAgentsOwnStandUp:
    def stand(self, scene, command_id="command-stand"):
        return scene.service.stand(MOZART, StandUp(command_id, scene.table_id), NOBODY)

    def test_the_agent_is_told_once_after_the_commit_and_no_book_row_is_written(self):
        scene = Scene()

        result = self.stand(scene)

        assert (result.refusal, scene.told, scene.store.book) == (None, [frozenset({MOZART.account_id})], {})

    def test_a_replay_and_a_refusal_tell_nobody(self):
        scene = Scene()
        self.stand(scene, "command-stand")
        scene.told.clear()

        replayed = self.stand(scene, "command-stand")
        refused = self.stand(scene, "command-again")

        assert (replayed.refusal, refused.refusal, scene.told) == (None, Refusal.NOT_SEATED, [])


class TestARetry:
    def test_the_same_command_id_sends_away_once_and_raises_the_epoch_once(self):
        scene = Scene()
        first = scene.send_away(command_id="command-away")
        version = scene.table.version

        again = scene.send_away(command_id="command-away")

        assert again.view == first.view
        assert (scene.table.version, scene.book().epoch) == (version, 1)

    def test_a_command_id_reused_for_another_agent_is_refused(self):
        scene = Scene()
        scene.send_away(command_id="command-away")

        with pytest.raises(CommandIdReusedError):
            scene.send_away(BACH, command_id="command-away")
