"""A seated player's private plan for the auction, „halten bis“ fixed or ask and „Weg“ said ahead: the table core steps
for him as ruled, shows the plan to him alone and forgets it with the hand and the chair.
"""

import random
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from skat.engine.bidding import VALID_BIDS, Bid, BidRefusal, Hold, Pass
from skat.engine.deal import Position
from skat.table.auction import AuctionAction, AuctionWord
from skat.table.auction_plans import AuctionPlanCommand, plan_payload, run_plans
from skat.table.hand_state import auction_of
from skat.table.member_place import Acceptance
from skat.table.records import (
    Actor,
    BidLimit,
    Decision,
    OccupantKind,
    PassAhead,
    PlanMode,
    Refusal,
    SeatPlan,
    SitDown,
    StandUp,
    TableId,
)
from skat.table.rules import CommandIdReusedError, dealt, drawn_hand, with_occupant
from tests.support.calls import call_facts
from tests.support.seated_auction import ANNA, BEN, DORA, NOBODY_CONNECTED, Seated, open_table

if TYPE_CHECKING:
    from skat.table.service import TableService

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
BID, HOLD, PASS = AuctionAction.BID, AuctionAction.HOLD, AuctionAction.PASS
FIXED, ASK = PlanMode.FIXED, PlanMode.ASK
LADDER = VALID_BIDS[:5]
assert LADDER == (18, 20, 22, 23, 24)  # the cases below name the first rungs of the ladder  # noqa: S101
AGENT = Actor(account_id="account-mozart", display_name="Mozart", kind=OccupantKind.AGENT)


def actor_at(seated: Seated, position: Position) -> Actor:
    return {FOREHAND: seated.forehand, MIDDLEHAND: seated.middlehand, REARHAND: seated.rearhand}[position]


def steps_of(seated: Seated):
    return seated.table().progress.auction


def awaited_position(seated: Seated) -> Position | None:
    table = seated.table()
    return None if table.hand is None else auction_of(table).actor


def play_out(seated: Seated, script) -> None:
    for position, action, *value in script:
        result = seated.send(
            actor_at(seated, position),
            action,
            value=value[0] if value else None,
            command_id=f"step-at-version-{seated.table().version}",
        )
        assert result.refusal is None


def plan_as(seated: Seated, position: Position, plan, command_id: str = "plan-1"):
    result = seated.plan(actor_at(seated, position), plan, command_id=command_id)
    assert result.refusal is None
    return result


class TestTheDeciderStepsForAPlan:
    @pytest.mark.parametrize(
        ("owner", "plan", "script", "steps", "awaited"),
        [
            pytest.param(
                FOREHAND,
                BidLimit(20, FIXED),
                [(MIDDLEHAND, BID, 18)],
                (Bid(MIDDLEHAND, 18), Hold(FOREHAND)),
                MIDDLEHAND,
                id="a-fixed-responder-holds-below-the-limit",
            ),
            pytest.param(
                FOREHAND,
                BidLimit(20, FIXED),
                [(MIDDLEHAND, BID, 20)],
                (Bid(MIDDLEHAND, 20), Hold(FOREHAND)),
                MIDDLEHAND,
                id="a-fixed-responder-holds-at-the-limit",
            ),
            pytest.param(
                FOREHAND,
                BidLimit(20, FIXED),
                [(MIDDLEHAND, BID, 22)],
                (Bid(MIDDLEHAND, 22), Pass(FOREHAND)),
                REARHAND,
                id="a-fixed-responder-passes-above-the-limit",
            ),
            pytest.param(
                FOREHAND,
                BidLimit(20, ASK),
                [(MIDDLEHAND, BID, 20)],
                (Bid(MIDDLEHAND, 20), Hold(FOREHAND)),
                MIDDLEHAND,
                id="an-ask-responder-holds-at-the-limit",
            ),
            pytest.param(
                FOREHAND,
                BidLimit(20, ASK),
                [(MIDDLEHAND, BID, 22)],
                (Bid(MIDDLEHAND, 22),),
                FOREHAND,
                id="an-ask-responder-is-awaited-above-the-limit",
            ),
            pytest.param(
                FOREHAND,
                BidLimit(20, ASK),
                [(MIDDLEHAND, BID, 22), (FOREHAND, HOLD), (MIDDLEHAND, BID, 23)],
                (Bid(MIDDLEHAND, 22), Hold(FOREHAND), Bid(MIDDLEHAND, 23)),
                FOREHAND,
                id="an-ask-limit-awaits-him-again-after-his-own-step-above-it",
            ),
            pytest.param(
                MIDDLEHAND,
                BidLimit(18, FIXED),
                [(FOREHAND, HOLD)],
                (Bid(MIDDLEHAND, 18), Hold(FOREHAND), Pass(MIDDLEHAND)),
                REARHAND,
                id="a-fixed-bidder-bids-up-to-the-limit-and-then-passes",
            ),
            pytest.param(
                MIDDLEHAND,
                BidLimit(20, ASK),
                [(FOREHAND, HOLD), (FOREHAND, HOLD)],
                (Bid(MIDDLEHAND, 18), Hold(FOREHAND), Bid(MIDDLEHAND, 20), Hold(FOREHAND)),
                MIDDLEHAND,
                id="an-ask-bidder-is-awaited-once-the-next-bid-passes-the-limit",
            ),
            pytest.param(
                FOREHAND,
                PassAhead(),
                [(MIDDLEHAND, BID, 18)],
                (Bid(MIDDLEHAND, 18), Pass(FOREHAND)),
                REARHAND,
                id="a-pass-ahead-passes-at-the-responders-turn",
            ),
            pytest.param(
                REARHAND,
                PassAhead(),
                [(MIDDLEHAND, PASS)],
                (Pass(MIDDLEHAND), Pass(REARHAND)),
                FOREHAND,
                id="a-pass-ahead-passes-at-the-bidders-turn",
            ),
            pytest.param(
                FOREHAND,
                PassAhead(),
                [(MIDDLEHAND, PASS), (REARHAND, PASS)],
                (Pass(MIDDLEHAND), Pass(REARHAND), Pass(FOREHAND)),
                None,
                id="a-pass-ahead-passes-the-hand-in-at-forehands-choice",
            ),
            pytest.param(
                FOREHAND,
                BidLimit(30, FIXED),
                [(MIDDLEHAND, PASS), (REARHAND, PASS)],
                (Pass(MIDDLEHAND), Pass(REARHAND)),
                FOREHAND,
                id="a-limit-leaves-forehands-choice-to-his-tap",
            ),
        ],
    )
    def test_the_plan_takes_the_ruled_steps_in_the_same_decision_as_the_step_that_made_it_the_owners_turn(
        self, seated: Seated, owner, plan, script, steps, awaited
    ) -> None:
        plan_as(seated, owner, plan)

        play_out(seated, script)

        assert steps_of(seated) == steps
        assert awaited_position(seated) == awaited

    def test_a_plan_set_on_the_owners_turn_steps_at_once(self, seated: Seated) -> None:
        before = seated.table().version

        result = plan_as(seated, MIDDLEHAND, BidLimit(20, FIXED))

        assert steps_of(seated) == (Bid(MIDDLEHAND, 18),)
        assert (seated.table().version, result.view.version) == (before + 1, before + 1)

    def test_two_plans_finish_the_duel_in_one_decision(self, seated: Seated) -> None:
        plan_as(seated, MIDDLEHAND, BidLimit(20, FIXED))

        result = plan_as(seated, FOREHAND, BidLimit(20, FIXED), command_id="plan-2")

        assert steps_of(seated) == (
            Bid(MIDDLEHAND, 18),
            Hold(FOREHAND),
            Bid(MIDDLEHAND, 20),
            Hold(FOREHAND),
            Pass(MIDDLEHAND),
        )
        assert awaited_position(seated) == REARHAND
        assert result.view.version == seated.table().version

    def test_a_pass_ahead_set_on_the_owners_turn_passes_at_once(self, seated: Seated) -> None:
        plan_as(seated, MIDDLEHAND, PassAhead())

        assert steps_of(seated) == (Pass(MIDDLEHAND),)

    def test_a_limit_set_at_forehands_choice_takes_no_step_and_a_pass_ahead_passes_the_hand_in(
        self, seated: Seated
    ) -> None:
        play_out(seated, [(MIDDLEHAND, PASS), (REARHAND, PASS)])

        plan_as(seated, FOREHAND, BidLimit(30, FIXED))
        assert awaited_position(seated) == FOREHAND

        plan_as(seated, FOREHAND, PassAhead(), command_id="plan-2")
        assert seated.table().hand is None
        assert seated.table().progress.plans == frozenset()

    def test_the_runner_takes_no_step_while_the_hand_waits_for_a_sitter(self, seated: Seated) -> None:
        play_out(seated, [(MIDDLEHAND, BID, 18)])
        table = with_occupant(seated.table(), seated.seat_of(seated.rearhand), None)
        table = replace(
            table,
            progress=replace(
                table.progress, plans=frozenset({SeatPlan(seated.seat_of(seated.forehand), BidLimit(20, FIXED))})
            ),
        )

        assert run_plans(Decision(table)) == Decision(table)


class TestTheSitThatEndsTheWait:
    def an_open_hand_where_the_forehand_planned_to_hold(self, seated: Seated) -> int:
        """The table where only an open chair keeps the planned forehand from holding the middlehand's 18; returns the
        open chair.
        """
        play_out(seated, [(MIDDLEHAND, BID, 18)])
        open_seat = seated.seat_of(seated.rearhand)
        seated.service.stand(seated.rearhand, StandUp("stand", seated.table_id), NOBODY_CONNECTED)
        planned = frozenset({SeatPlan(seated.seat_of(seated.forehand), BidLimit(20, FIXED))})
        table = seated.table()
        seated.store.tables[seated.table_id] = replace(table, progress=replace(table.progress, plans=planned))
        assert steps_of(seated) == (Bid(MIDDLEHAND, 18),)
        return open_seat

    def test_a_persons_sit_takes_the_planned_step(self, seated: Seated) -> None:
        seat = self.an_open_hand_where_the_forehand_planned_to_hold(seated)

        result = seated.service.sit(DORA, SitDown("sit", seated.table_id, seat), NOBODY_CONNECTED)

        assert result.refusal is None
        assert steps_of(seated) == (Bid(MIDDLEHAND, 18), Hold(FOREHAND))

    def test_an_agents_accept_takes_the_planned_step(self, seated: Seated) -> None:
        self.an_open_hand_where_the_forehand_planned_to_hold(seated)
        owner = ANNA.account_id
        offer = seated.service.invite_agent(
            TableId(seated.table_id), call_facts(AGENT.account_id, owner), timedelta(seconds=600)
        )

        accepted = seated.service.accept_invitation(
            AGENT,
            owner,
            Acceptance(table_id=seated.table_id, invitation_id=offer.id, epoch=offer.epoch),
            frozenset({owner}),
        )

        assert accepted.refusal is None
        assert steps_of(seated) == (Bid(MIDDLEHAND, 18), Hold(FOREHAND))


class TestRefusals:
    @pytest.mark.parametrize(
        ("scene", "owner", "plan", "reason"),
        [
            pytest.param("running", FOREHAND, BidLimit(19, ASK), BidRefusal.INVALID_VALUE, id="off-the-ladder"),
            pytest.param("running", FOREHAND, BidLimit(265, ASK), BidRefusal.INVALID_VALUE, id="above-the-ladder"),
            pytest.param("standing-24", FOREHAND, BidLimit(23, ASK), BidRefusal.INVALID_VALUE, id="below-the-standing"),
            pytest.param("running", MIDDLEHAND, None, None, id="a-clear-is-no-value"),
            pytest.param("passed", MIDDLEHAND, PassAhead(), BidRefusal.ALREADY_PASSED, id="a-seat-that-passed"),
            pytest.param("passed", MIDDLEHAND, None, BidRefusal.ALREADY_PASSED, id="a-clear-by-a-seat-that-passed"),
            pytest.param("declared", MIDDLEHAND, BidLimit(30, ASK), Refusal.WRONG_PHASE, id="an-auction-that-is-over"),
            pytest.param(
                "open-chair", FOREHAND, BidLimit(30, ASK), Refusal.SEAT_OPEN, id="a-chair-waiting-for-a-sitter"
            ),
        ],
    )
    def test_a_refused_plan_leaves_the_table_as_it_was(self, seated: Seated, scene, owner, plan, reason) -> None:
        if scene == "standing-24":
            play_out(seated, [(MIDDLEHAND, BID, 24)])
        if scene == "passed":
            play_out(seated, [(MIDDLEHAND, PASS)])
        if scene == "declared":
            play_out(seated, [(MIDDLEHAND, BID, 18), (FOREHAND, PASS), (REARHAND, PASS)])
        if scene == "open-chair":
            seated.service.stand(seated.rearhand, StandUp("stand", seated.table_id), NOBODY_CONNECTED)
        before = seated.table()

        result = seated.plan(actor_at(seated, owner), plan)

        assert result.refusal is reason
        if reason is not None:
            assert seated.table() == before

    def test_no_hand_and_no_chair_are_refused_as_for_every_hand_command(self, service: TableService) -> None:
        table_id = open_table(service)
        service.sit(BEN, SitDown("command-ben", table_id, 2), NOBODY_CONNECTED)
        command = AuctionPlanCommand("plan-1", table_id, PassAhead())

        no_hand = service.set_auction_plan(BEN, command, NOBODY_CONNECTED)

        assert no_hand.refusal is Refusal.NO_HAND

    def test_a_player_without_a_chair_is_refused_as_not_seated(self, seated: Seated) -> None:
        assert seated.plan(DORA, PassAhead()).refusal is Refusal.NOT_SEATED

    def test_a_limit_equal_to_the_standing_bid_is_allowed(self, seated: Seated) -> None:
        play_out(seated, [(MIDDLEHAND, BID, 24)])

        plan_as(seated, FOREHAND, BidLimit(24, FIXED))

        assert steps_of(seated)[-1] == Hold(FOREHAND)


class TestAPlanSetOffTurn:
    def test_it_leaves_the_version_alone_and_another_players_bid_at_that_version_is_accepted(
        self, seated: Seated
    ) -> None:
        version = seated.table().version

        plan_as(seated, FOREHAND, BidLimit(20, ASK))

        assert seated.table().version == version
        accepted = seated.send(seated.middlehand, BID, value=18, version=version, command_id="bid")
        assert accepted.refusal is None

    def test_it_changes_and_clears(self, seated: Seated) -> None:
        owner = seated.seat_of(seated.forehand)

        plan_as(seated, FOREHAND, BidLimit(20, ASK))
        plan_as(seated, FOREHAND, PassAhead(), command_id="plan-2")
        assert seated.table().progress.plan_of(owner) == PassAhead()

        plan_as(seated, FOREHAND, None, command_id="plan-3")
        assert seated.table().progress.plans == frozenset()


class TestTheReceipt:
    def test_a_retry_after_a_later_plan_replays_the_first_outcome_and_applies_nothing_again(
        self, seated: Seated
    ) -> None:
        play_out(seated, [(MIDDLEHAND, BID, 18)])
        first = plan_as(seated, FOREHAND, BidLimit(20, ASK), command_id="plan-1")
        plan_as(seated, FOREHAND, BidLimit(30, ASK), command_id="plan-2")
        play_out(seated, [(MIDDLEHAND, BID, 20)])
        after_the_later_plan = seated.table()

        again = plan_as(seated, FOREHAND, BidLimit(20, ASK), command_id="plan-1")

        assert seated.table() == after_the_later_plan
        assert again.view.hand.auction.plan == BidLimit(30, ASK)
        assert first.refusal is None

    def test_the_same_id_with_another_plan_is_refused_as_reused(self, seated: Seated) -> None:
        plan_as(seated, FOREHAND, BidLimit(22, FIXED))

        with pytest.raises(CommandIdReusedError):
            seated.plan(seated.forehand, BidLimit(22, ASK), command_id="plan-1")

    @pytest.mark.parametrize("plan", [BidLimit(22, FIXED), BidLimit(22, ASK), PassAhead(), None])
    def test_the_payload_names_no_limit(self, plan) -> None:
        payload = plan_payload(AuctionPlanCommand("plan-1", "table", plan))

        parts = payload.split(":")
        assert parts[0] == "table"
        assert not {"22", "fixed", "ask", "limit"} & set(parts)

    def test_the_payloads_of_different_plans_differ(self) -> None:
        plans = [BidLimit(22, FIXED), BidLimit(22, ASK), BidLimit(23, FIXED), PassAhead(), None]

        payloads = {plan_payload(AuctionPlanCommand("plan-1", "table", plan)) for plan in plans}

        assert len(payloads) == len(plans)


class TestThePlanEnds:
    def test_a_passed_in_hand_keeps_no_plan(self, seated: Seated) -> None:
        plan_as(seated, FOREHAND, BidLimit(30, ASK))
        play_out(seated, [(MIDDLEHAND, PASS), (REARHAND, PASS), (FOREHAND, PASS)])

        assert (seated.table().hand, seated.table().progress.plans) == (None, frozenset())

    def test_at_the_next_deal(self, seated: Seated) -> None:
        plan_as(seated, FOREHAND, BidLimit(30, ASK))
        table = seated.table()

        next_deal = dealt(table, drawn_hand(table, random.Random(1)), version=table.version + 1)  # noqa: S311 - a seeded deal with no secret

        assert next_deal.progress.plans == frozenset()

    @pytest.mark.parametrize(
        ("someone_sits", "the_same_account"),
        [(False, False), (True, False), (True, True)],
        ids=["when-he-stands", "when-another-sits-down", "when-he-sits-again"],
    )
    def test_at_a_change_of_the_occupant(self, seated: Seated, someone_sits: bool, the_same_account: bool) -> None:
        plan_as(seated, FOREHAND, PassAhead())
        seat = seated.seat_of(seated.forehand)
        plan_as(seated, REARHAND, BidLimit(30, ASK), command_id="plan-rear")

        seated.service.stand(seated.forehand, StandUp("stand", seated.table_id), NOBODY_CONNECTED)
        if someone_sits:
            returning = seated.forehand if the_same_account else DORA
            seated.service.sit(returning, SitDown("sit", seated.table_id, seat), NOBODY_CONNECTED)

        remaining = seated.table().progress.plans
        assert remaining == frozenset({SeatPlan(seated.seat_of(seated.rearhand), BidLimit(30, ASK))})


class TestOnlyTheOwnerSeesThePlan:
    def view_of_plan(self, seated: Seated, viewer: Actor):
        view = seated.service.view(viewer, seated.table_id, NOBODY_CONNECTED)
        return view.hand.auction.plan

    def test_the_owners_view_carries_it_and_nobody_elses_does(self, seated: Seated) -> None:
        plan_as(seated, FOREHAND, BidLimit(20, ASK))

        viewers = {
            "forehand": seated.forehand,
            "middlehand": seated.middlehand,
            "rearhand": seated.rearhand,
            "onlooker": DORA,
            "agent-onlooker": AGENT,
        }
        plans = {name: self.view_of_plan(seated, viewer) for name, viewer in viewers.items()}

        assert plans == {
            "forehand": BidLimit(20, ASK),
            "middlehand": None,
            "rearhand": None,
            "onlooker": None,
            "agent-onlooker": None,
        }

    def test_the_owner_s_answer_to_the_command_carries_it(self, seated: Seated) -> None:
        result = plan_as(seated, FOREHAND, PassAhead())

        assert result.view.hand.auction.plan == PassAhead()

    def test_another_viewers_words_show_the_runner_s_step_as_the_owners_own_word(self, seated: Seated) -> None:
        plan_as(seated, FOREHAND, BidLimit(20, FIXED))
        play_out(seated, [(MIDDLEHAND, BID, 18)])

        words = seated.service.view(DORA, seated.table_id, NOBODY_CONNECTED).hand.auction.words

        assert AuctionWord(seated.seat_of(seated.forehand), HOLD, 18) in words

    def test_every_viewer_reads_each_step_two_plans_took_in_one_decision_as_its_chairs_own_in_order(
        self, seated: Seated
    ) -> None:
        plan_as(seated, MIDDLEHAND, BidLimit(20, FIXED))
        plan_as(seated, FOREHAND, BidLimit(20, FIXED), command_id="plan-2")
        middlehand, forehand = seated.seat_of(seated.middlehand), seated.seat_of(seated.forehand)

        for viewer in (seated.forehand, seated.middlehand, seated.rearhand, DORA, AGENT):
            assert seated.service.view(viewer, seated.table_id, NOBODY_CONNECTED).hand.auction.steps == (
                AuctionWord(middlehand, BID, 18),
                AuctionWord(forehand, HOLD, 18),
                AuctionWord(middlehand, BID, 20),
                AuctionWord(forehand, HOLD, 20),
                AuctionWord(middlehand, PASS, None),
            )
