"""An agent seated at a table reads its view from the service, and each committed change that raised the table's
version tells the agents seated after it.
"""

import itertools
import random
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skat.engine.deal import Position
from skat.table.acts import ActKind, next_seq_of
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.member_place import Acceptance, InvitationOffer
from skat.table.member_view import traces_of_acts
from skat.table.playing import AgreeToGiveUpCommand, GiveUpCommand
from skat.table.ready import ReadyCommand
from skat.table.records import (
    Actor,
    CreateTable,
    EndedTable,
    Ending,
    EndProposal,
    GiveUpOptions,
    HandProgress,
    OccupantKind,
    Series,
    SitDown,
    StandUp,
    TableId,
    TableOptions,
)
from skat.table.series_end import END_ANSWER_SECONDS, SeriesEndCommand
from skat.table.service import TableService
from skat.table.transactions import TableVersion
from tests.support.calls import call_facts
from tests.support.fake_tables import FakeTableStore, ServiceScene
from tests.support.played_game import (
    an_end_proposal,
    asked_by_the_declarer,
    between_games,
    declared_herz_hand,
    table_in,
    with_agents,
)
from tests.support.seated_tables import actor_of

START = datetime(2026, 11, 1, 12, tzinfo=UTC)
NOBODY = frozenset[str]()
ANNA = Actor(account_id="account-anna", display_name="Anna")
MOZART = Actor(account_id="account-mozart", display_name="Mozart", kind=OccupantKind.AGENT)
BACH = Actor(account_id="account-bach", display_name="Bach", kind=OccupantKind.AGENT)
WATCHER = Actor(account_id="account-watcher", display_name="Watcher")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
UNKNOWN_TABLE = "0" * 32
EARLIER_TRACE = "trace-of-the-earlier-commit"


class Scene(ServiceScene):
    """A service on a store; every signal it tells is kept with each agent's view as the store showed it then."""

    def __init__(self, seed=1):
        self.store = FakeTableStore()
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

    def acts_of(self, account, table_id=None):
        return self.service.member_acts(account, table_id or self.table_id)

    def command_id(self):
        return f"command-{next(self.commands)}"

    def seat_three(self, second=MOZART, third=BACH, series_length=None):
        self.table_id = self.service.create(
            ANNA, CreateTable(command_id="command-open", series_length=series_length)
        ).id
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
        scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 0)

        assert scene.view_of(MOZART.account_id) is None


class TestTheActsOfAMember:
    def test_a_seated_account_reads_the_acts_of_the_dealt_hand_with_its_own_seat(self):
        acts = Scene().seat_three(series_length=36).acts_of(MOZART.account_id)

        assert (acts.own_seat, [each.kind for each in acts.acts], acts.starts_at) == (
            2,
            [ActKind.DEAL],
            acts.acts[0].seq,
        )

    def test_a_table_before_its_first_deal_has_no_act_and_says_the_number_of_the_next(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open", series_length=36)).id

        acts = scene.acts_of(ANNA.account_id)

        assert (acts.acts, acts.starts_at) == ((), next_seq_of(scene.table))

    @pytest.mark.parametrize(
        ("account", "table_id"),
        [
            pytest.param(WATCHER.account_id, None, id="without-a-chair"),
            pytest.param(MOZART.account_id, UNKNOWN_TABLE, id="unknown-table"),
            pytest.param(MOZART.account_id, "not-an-id", id="malformed-table"),
        ],
    )
    def test_an_account_without_a_chair_and_a_table_that_is_not_there_have_no_acts(self, scene, account, table_id):
        assert scene.acts_of(account, table_id) is None

    def test_an_ended_table_has_no_acts(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
        scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
        scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 0)

        assert scene.acts_of(MOZART.account_id) is None


class TestTheTracesAMemberReads:
    """Each act and the table's version carry the trace of the request that committed them, as stored."""

    @pytest.fixture
    def scene(self):
        scene = Scene().put(replace(table_in(HandProgress()), series=Series(36, 1)))
        scene.trace = None
        scene.service = scene.service.with_trace(lambda: scene.trace)
        return scene

    def bid_in_the_trace_of(self, scene, trace):
        scene.trace = trace
        bidder = actor_of(Position.MIDDLEHAND)
        return auction_bid(scene.service, bidder, scene.table_id, scene.table.version)

    def traced_acts(self, scene):
        acts = scene.acts_of(actor_of(Position.FOREHAND).account_id)
        return [(act.kind, acts.traces.get(act.seq)) for act in acts.acts]

    def test_an_act_and_the_version_carry_the_trace_of_the_request_that_committed_them(self, scene):
        self.bid_in_the_trace_of(scene, "trace-of-the-bid")

        assert self.traced_acts(scene) == [(ActKind.DEAL, None), (ActKind.BID, "trace-of-the-bid")]
        assert scene.view_of(actor_of(Position.FOREHAND).account_id).traceparent == "trace-of-the-bid"

    def test_an_opened_table_carries_the_trace_of_the_request_that_opened_it(self, scene):
        scene.trace = "trace-of-the-opening"

        table_id = scene.service.create(ANNA, CreateTable(command_id="command-open-traced")).id

        assert scene.view_of(ANNA.account_id, table_id).traceparent == "trace-of-the-opening"

    def test_a_later_request_leaves_the_trace_of_an_earlier_act_and_takes_the_version(self, scene):
        self.bid_in_the_trace_of(scene, "trace-of-the-bid")
        holder = actor_of(Position.FOREHAND)
        scene.trace = "trace-of-the-hold"
        scene.service.take_auction_step(
            holder, AuctionCommand("hold", scene.table_id, scene.table.version, AuctionAction.HOLD, None), NOBODY
        )

        assert self.traced_acts(scene)[1:] == [(ActKind.BID, "trace-of-the-bid"), (ActKind.HOLD, "trace-of-the-hold")]
        assert scene.view_of(holder.account_id).traceparent == "trace-of-the-hold"

    def test_a_commit_outside_a_trace_stores_none_and_leaves_an_earlier_trace_to_its_act(self, scene):
        self.bid_in_the_trace_of(scene, "trace-of-the-bid")
        scene.trace = None
        holder = actor_of(Position.FOREHAND)
        scene.service.take_auction_step(
            holder, AuctionCommand("hold", scene.table_id, scene.table.version, AuctionAction.HOLD, None), NOBODY
        )

        assert self.traced_acts(scene)[1:] == [(ActKind.BID, "trace-of-the-bid"), (ActKind.HOLD, None)]
        assert scene.view_of(holder.account_id).traceparent is None


def _traced_as_committed_earlier(scene):
    """The table as stored, its version and each act of it entered in the trace `EARLIER_TRACE`."""
    viewer = actor_of(Position.FOREHAND).account_id
    acts = scene.acts_of(viewer).acts
    scene.put(
        replace(
            scene.table,
            traces=traces_of_acts(scene.table, EARLIER_TRACE, dict.fromkeys((act.seq for act in acts), EARLIER_TRACE)),
        )
    )
    return viewer


def _a_lapsed_end_answer(scene):
    lapsed = EndProposal(1, frozenset({1}), START - timedelta(seconds=END_ANSWER_SECONDS + 1))
    scene.put(between_games(series=replace(Series(12, 1), end_proposal=lapsed)))
    viewer = _traced_as_committed_earlier(scene)
    return viewer, lambda: scene.service.lapse_end_answers(TableId(scene.table_id))


def _the_next_deal(scene):
    scene.put(between_games(1, 2, 3))
    viewer = _traced_as_committed_earlier(scene)
    everyone = frozenset(chair.occupant.account_id for chair in scene.table.chairs)
    return viewer, lambda: scene.service.deal_next(TableId(scene.table_id), nullcontext(everyone))


def _a_freed_chair_after_sits_in_the_earlier_trace(scene):
    scene.trace = EARLIER_TRACE
    scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
    scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
    scene.store.hold_due(scene.table_id, MOZART.account_id)
    return ANNA.account_id, lambda: scene.service.free_held_chair(
        TableId(scene.table_id), MOZART.account_id, nullcontext(True)
    )


class TestTheTracesAServerStepEntersIn:
    """What the server commits on its own account carries the trace the step ran in, as a request's commit does."""

    @pytest.fixture
    def scene(self):
        scene = Scene()
        scene.trace = None
        scene.service = scene.service.with_trace(lambda: scene.trace)
        return scene

    @pytest.mark.parametrize("step_trace", ["trace-of-the-step", None])
    @pytest.mark.parametrize(
        "arrange", [_a_lapsed_end_answer, _the_next_deal, _a_freed_chair_after_sits_in_the_earlier_trace]
    )
    def test_the_view_and_the_new_acts_carry_the_steps_trace_and_the_earlier_acts_keep_theirs(
        self, scene, arrange, step_trace
    ):
        viewer, step = arrange(scene)
        before = scene.acts_of(viewer)
        held = {act.seq for act in before.acts}
        scene.trace = step_trace

        step()

        after = scene.acts_of(viewer)
        assert scene.view_of(viewer).traceparent == step_trace
        assert {act.seq: after.traces.get(act.seq) for act in after.acts} == {
            act.seq: before.traces.get(act.seq) if act.seq in held else step_trace for act in after.acts
        }


class TestTheAgentInAChair:
    @pytest.mark.parametrize(
        ("seat", "account"),
        [
            pytest.param(1, None, id="a-person"),
            pytest.param(2, MOZART.account_id, id="an-agent"),
            pytest.param(3, BACH.account_id, id="another-agent"),
            pytest.param(4, None, id="no-chair"),
        ],
    )
    def test_is_the_account_of_the_agent_seated_there_and_nobody_else(self, scene, seat, account):
        assert scene.service.agent_in_chair(scene.table_id, seat) == account

    def test_is_nobody_at_a_free_chair(self, scene):
        scene.service.stand(MOZART, StandUp("command-stand", scene.table_id), NOBODY)

        assert scene.service.agent_in_chair(scene.table_id, 2) is None

    @pytest.mark.parametrize("table_id", [UNKNOWN_TABLE, "not-an-id"])
    def test_is_nobody_at_a_table_that_is_not_there(self, scene, table_id):
        assert scene.service.agent_in_chair(table_id, 2) is None

    def test_is_nobody_at_a_table_that_ended(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
        scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
        scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 0)

        assert scene.service.agent_in_chair(scene.table_id, 2) is None


def auction_bid(service, actor, table_id, version):
    command = AuctionCommand("act", table_id, version, AuctionAction.BID, 18)
    return service.take_auction_step(actor, command, NOBODY)


def auction_pass(service, actor, table_id, version):
    command = AuctionCommand("act", table_id, version, AuctionAction.PASS, None)
    return service.take_auction_step(actor, command, NOBODY)


def agree_to_give_up(service, actor, table_id, version):
    return service.agree_to_give_up(actor, AgreeToGiveUpCommand("act", table_id, version), NOBODY)


def give_up(service, actor, table_id, version):
    return service.give_up(actor, GiveUpCommand("act", table_id, version), NOBODY)


def continue_after_result(service, actor, table_id, version):
    return service.mark_ready(actor, ReadyCommand("act", table_id, 1, 1), NOBODY)


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
                table_in(declared_herz_hand()), Position.FOREHAND, give_up, True, id="8-give-up-then-the-result"
            ),
            pytest.param(
                between_games(1, 2, 3, proposal=an_end_proposal(1)),
                Position.REARHAND,
                refuse_to_end,
                False,
                id="7-refuse",
            ),
        ],
    )
    def test_the_revision_rises_and_the_seat_awaits_no_more_or_the_next_step(self, record, position, act, awaits_after):
        scene = Scene().put(record)
        seat = actor_of(position)
        before = scene.view_of(seat.account_id)

        result = act(scene.service, seat, scene.table_id, scene.table.version)

        after = scene.view_of(seat.account_id)
        assert (before.awaits_you, result.refusal) == (True, None)
        assert after.view.version > before.view.version
        assert after.awaits_you is awaits_after

    def test_after_an_opponents_give_up_his_partner_is_awaited_and_no_other_seat_where_the_partner_must_agree(self):
        scene = Scene().put(table_in(declared_herz_hand(), TableOptions(give_up=GiveUpOptions(partner_agrees=True))))
        give_up(scene.service, actor_of(Position.FOREHAND), scene.table_id, scene.table.version)

        awaiting = {position for position in Position if scene.view_of(actor_of(position).account_id).awaits_you}

        assert awaiting == {Position.REARHAND}

    def test_the_same_act_again_raises_nothing(self):
        scene = Scene().put(between_games(2, 3))
        seat = actor_of(Position.MIDDLEHAND)
        continue_after_result(scene.service, seat, scene.table_id, 0)
        revision = scene.view_of(seat.account_id).view.version

        again = continue_after_result(scene.service, seat, scene.table_id, 0)

        assert (again.refusal, scene.view_of(seat.account_id).view.version) == (None, revision)

    def test_a_refused_act_raises_nothing(self):
        scene = Scene().put(table_in(HandProgress()))
        seat = actor_of(Position.MIDDLEHAND)
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
        seat = actor_of(Position.MIDDLEHAND)

        accepted = continue_after_result(scene.service, seat, scene.table_id, 0)

        assert accepted.refusal is None
        assert [accounts for _, accounts, _ in scene.signals] == [{"account-rearhand", "account-forehand"}]
        scene.signals.clear()

        stale = scene.service.take_auction_step(
            seat, AuctionCommand("stale", scene.table_id, 99, AuctionAction.BID, 18), NOBODY
        )
        replay = continue_after_result(scene.service, seat, scene.table_id, 0)
        second_tap = scene.service.mark_ready(seat, ReadyCommand("another", scene.table_id, 1, 1), NOBODY)

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
        scene.service.stand(ANNA, StandUp("command-anna-stand", scene.table_id), NOBODY)
        scene.service.sit(BACH, SitDown("command-bach", scene.table_id, 3), NOBODY)
        scene.signals.clear()

        scene.store.hold_due(scene.table_id, MOZART.account_id)
        freed = scene.service.free_held_chair(TableId(scene.table_id), MOZART.account_id, nullcontext(True))

        assert freed is True
        assert [accounts for _, accounts, _ in scene.signals] == [{BACH.account_id}]

    def test_a_chair_not_freed_tells_nobody(self, scene):
        scene.store.hold_due(scene.table_id, MOZART.account_id)
        assert scene.service.free_held_chair(TableId(scene.table_id), MOZART.account_id, nullcontext(False)) is False
        assert scene.signals == []

    def test_an_accepted_invitation_tells_the_agents_seated_after_it(self):
        scene = Scene()
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
        scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
        facts = call_facts(BACH.account_id, ANNA.account_id)
        offer = scene.service.invite_agent(TableId(scene.table_id), facts, timedelta(hours=1))
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


class TestWhetherAnAccountHoldsAChair:
    def test_an_account_that_holds_no_chair_holds_none(self, scene):
        assert scene.service.holds_a_chair(WATCHER.account_id) is False

    def test_a_seated_account_holds_a_chair(self, scene):
        assert scene.service.holds_a_chair(MOZART.account_id) is True

    def test_a_table_that_ended_after_the_candidates_were_listed_gives_no_chair(self, scene, monkeypatch):
        scene.store.tables[scene.table_id] = EndedTable(TableId(scene.table_id), 9, Ending.empty(3600))
        monkeypatch.setattr(scene.store, "tables_of", lambda _account: (TableVersion(TableId(scene.table_id), 8, ()),))

        assert scene.service.holds_a_chair(MOZART.account_id) is False


class TestTheToolsSignal:
    def test_a_move_of_the_game_tells_nobody_the_tools_changed(self):
        told = []
        scene = Scene().seat_three()
        scene.service = scene.service.with_tools_signal(told.append)

        def on_turn():
            return next(actor for actor in (ANNA, MOZART, BACH) if scene.view_of(actor.account_id).awaits_you)

        auction_bid(scene.service, on_turn(), scene.table_id, scene.table.version)
        auction_pass(scene.service, on_turn(), scene.table_id, scene.table.version)
        auction_pass(scene.service, on_turn(), scene.table_id, scene.table.version)

        assert told == []

    def test_inviting_an_agent_sends_no_tools_notice(self):
        told = []
        scene = Scene()
        scene.service = scene.service.with_tools_signal(told.append)
        scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id

        offer = scene.service.invite_agent(
            TableId(scene.table_id), call_facts(BACH.account_id, ANNA.account_id), timedelta(hours=1)
        )

        assert isinstance(offer, InvitationOffer)
        assert told == []


def _a_sit_that_deals(scene):
    scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
    scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
    return lambda: scene.service.sit(BACH, SitDown("command-bach", scene.table_id, 3), NOBODY)


def _an_accepted_invitation(scene):
    scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
    scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
    offer = scene.service.invite_agent(
        TableId(scene.table_id), call_facts(BACH.account_id, ANNA.account_id), timedelta(hours=1)
    )
    acceptance = Acceptance(scene.table_id, offer.id, offer.epoch)
    return lambda: scene.service.accept_invitation(BACH, ANNA.account_id, acceptance, frozenset({ANNA.account_id}))


def _a_freed_chair(scene):
    scene.table_id = scene.service.create(ANNA, CreateTable(command_id="command-open")).id
    scene.service.sit(MOZART, SitDown("command-mozart", scene.table_id, 2), NOBODY)
    scene.service.stand(ANNA, StandUp("command-anna-stand", scene.table_id), NOBODY)
    scene.service.sit(BACH, SitDown("command-bach", scene.table_id, 3), NOBODY)
    scene.store.hold_due(scene.table_id, MOZART.account_id)
    return lambda: scene.service.free_held_chair(TableId(scene.table_id), MOZART.account_id, nullcontext(True))


class TestTheOrderOfTheTellings:
    @pytest.mark.parametrize(
        "arrange",
        [_a_sit_that_deals, _an_accepted_invitation, _a_freed_chair],
    )
    def test_the_tools_notice_of_a_change_precedes_every_other_telling_of_it(self, arrange):
        told = []
        scene = Scene()
        scene.service = (
            scene.service.with_view_signal(lambda _table, _accounts: told.append("view"))
            .with_standing_signal(lambda _accounts: told.append("standing"))
            .with_tools_signal(lambda _accounts: told.append("tools"))
        )
        act = arrange(scene)
        told.clear()

        act()

        assert "tools" in told
        assert told == sorted(told, key=lambda kind: kind != "tools")
