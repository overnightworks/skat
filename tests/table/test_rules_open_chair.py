"""A running hand with an open chair stands still, and whoever sits in the chair takes over its seat."""

from dataclasses import replace

import pytest

from skat.engine.bidding import Pass
from skat.engine.bock import BockOptions, BockOverlap, BockRounds, BockTrigger
from skat.engine.cards import DECK
from skat.engine.deal import seats_from
from skat.engine.declaration import Announcement, Declare
from skat.engine.games import GameKind
from skat.table.auction import AuctionAction, AuctionCommand, decide_step
from skat.table.declaring import DeclaringCommand, decide_declaring_step
from skat.table.game_list import ListEntry
from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    PlayCardCommand,
    decide_agree_to_give_up,
    decide_card,
    decide_decline_give_up,
)
from skat.table.records import GiveUpAsked, HandProgress, NewHand, OccupantKind, Refusal, TableOptions
from skat.table.rules import acting_position, decide_sit, decide_stand, waiting_seat_of
from skat.table.views import turn_seat_of, view_of
from tests.support.open_chairs import (
    FOREHAND,
    FOREHAND_SEAT,
    HAND_COMMANDS,
    MIDDLEHAND,
    MIDDLEHAND_SEAT,
    OWN_PUT_BACK,
    PHASES,
    REARHAND,
    REARHAND_SEAT,
    account_of,
    actor_at,
    hand_command,
    newcomer,
    sent_away,
)
from tests.support.played_game import an_entry, asked_by_the_declarer, before_the_last_card, table_in, with_agents

NOBODY = frozenset[str]()
THIRD_PASS_BY_FOREHAND = HandProgress(auction=(Pass(MIDDLEHAND), Pass(REARHAND)))


def without_occupants(table, *seats):
    chairs = tuple(replace(chair, occupant=None) if chair.seat in seats else chair for chair in table.chairs)
    return replace(table, chairs=chairs)


def waiting_in(phase):
    """The phase's hand with the agent of seat 2 sent away; the persons of seat 1 and the agent of seat 3 stay."""
    return sent_away(with_agents(PHASES[phase](), FOREHAND_SEAT), REARHAND_SEAT)


def seat_on_turn(table):
    return turn_seat_of(view_of(table, "account-nobody", NOBODY).hand)


class TestTheWaitingSeat:
    @pytest.mark.parametrize(
        ("free", "waiting"),
        [
            pytest.param((), None, id="all-seated"),
            pytest.param((2,), 2, id="one-open"),
            pytest.param((3, 2), 2, id="the-lowest-of-two"),
            pytest.param((3, 1), 1, id="the-lowest-of-two-with-the-first"),
            pytest.param((1, 2, 3), 1, id="all-three"),
        ],
    )
    def test_names_the_lowest_free_seat_while_a_hand_runs(self, free, waiting):
        assert waiting_seat_of(without_occupants(PHASES["auction"](), *free)) == waiting

    def test_names_none_while_no_hand_runs(self):
        between_hands = replace(without_occupants(PHASES["auction"](), 2), hand=None, progress=HandProgress())

        assert waiting_seat_of(between_hands) is None


class TestEveryHandCommandIsRefused:
    @pytest.mark.parametrize("command", HAND_COMMANDS)
    @pytest.mark.parametrize("phase", PHASES)
    @pytest.mark.parametrize("seat", [MIDDLEHAND_SEAT, FOREHAND_SEAT], ids=["a-person", "an-agent"])
    def test_seat_open_for_a_seated_person_and_agent_and_nothing_changes(self, phase, command, seat):
        table = waiting_in(phase)

        decision = hand_command(command, table, actor_at(table, seat))

        assert (decision.refusal, decision.table) == (Refusal.SEAT_OPEN, table)

    def test_a_stale_version_is_still_refused_as_stale(self):
        table = waiting_in("auction")

        assert acting_position(table, actor_at(table, MIDDLEHAND_SEAT), table.version - 1) is Refusal.STALE_VERSION

    def test_a_watcher_is_still_refused_as_not_seated(self):
        table = waiting_in("auction")

        assert acting_position(table, newcomer(), table.version) is Refusal.NOT_SEATED

    def test_a_table_without_a_hand_is_still_refused_as_having_no_hand(self):
        table = replace(waiting_in("auction"), hand=None, dealer=None)

        assert acting_position(table, actor_at(table, MIDDLEHAND_SEAT), table.version) is Refusal.NO_HAND

    @pytest.mark.parametrize("phase", PHASES)
    def test_a_newcomers_stand_up_is_refused_as_a_hand_running(self, phase):
        table = waiting_in(phase)
        taken = decide_sit(table, newcomer(), REARHAND_SEAT, None).table

        assert decide_stand(taken, newcomer()).refusal is Refusal.HAND_RUNNING

    def test_a_second_chair_is_refused_to_a_seated_person(self):
        table = waiting_in("auction")

        assert decide_sit(table, actor_at(table, MIDDLEHAND_SEAT), REARHAND_SEAT, None).refusal is (
            Refusal.ALREADY_SEATED
        )


class TestTwoOpenChairs:
    def setup_method(self):
        self.table = without_occupants(PHASES["auction"](), 1, 2)

    def test_the_lowest_is_named_and_the_number_moves_to_the_other_when_the_first_is_filled(self):
        first = decide_sit(self.table, newcomer(), MIDDLEHAND_SEAT, None).table

        assert (waiting_seat_of(self.table), waiting_seat_of(first)) == (1, 2)

    def test_the_hand_stands_still_until_both_are_filled(self):
        first = decide_sit(self.table, newcomer(), MIDDLEHAND_SEAT, None).table
        both = decide_sit(first, newcomer(name="Erik"), REARHAND_SEAT, None).table
        pass_at = AuctionCommand("command-1", both.id.value, both.version, AuctionAction.PASS, None)

        assert hand_command("auction-step", first, actor_at(first, FOREHAND_SEAT)).refusal is Refusal.SEAT_OPEN
        assert waiting_seat_of(both) is None
        assert decide_step(both, actor_at(both, FOREHAND_SEAT), pass_at).refusal is None

    def test_a_table_with_all_three_chairs_open_waits_for_a_sitter_and_takes_any_sit(self):
        table = without_occupants(PHASES["auction"](), 1, 2, 3)

        taken = decide_sit(table, newcomer(), FOREHAND_SEAT, None)

        assert (waiting_seat_of(table), taken.refusal, waiting_seat_of(taken.table)) == (1, None, 1)


class TestTheTakeOver:
    @pytest.mark.parametrize("kind", list(OccupantKind))
    @pytest.mark.parametrize("phase", PHASES)
    def test_the_sitter_holds_the_seats_cards_bids_role_and_turn_and_sees_what_the_seat_saw(self, phase, kind):
        table = with_agents(PHASES[phase](), seat_on_turn(PHASES[phase]()))
        seat = seat_on_turn(table)
        agent = actor_at(table, seat)
        sitter = newcomer(kind)

        taken = decide_sit(sent_away(table, seat), sitter, seat, None).table

        assert view_of(taken, sitter.account_id, NOBODY).hand == view_of(table, agent.account_id, NOBODY).hand
        assert view_of(taken, sitter.account_id, NOBODY).hand.own_cards

    @pytest.mark.parametrize("phase", PHASES)
    def test_the_sit_moves_the_hand_again_for_the_sitter_and_the_others(self, phase):
        table = PHASES[phase]()
        seat = seat_on_turn(table)
        sitter = newcomer()

        taken = decide_sit(sent_away(table, seat), sitter, seat, None).table

        assert waiting_seat_of(taken) is None
        assert (taken.hand, taken.progress) == (table.hand, table.progress)
        assert seat_on_turn(taken) == seat

    def test_the_sitter_in_the_auction_bids_for_the_seat(self):
        table = PHASES["auction"]()
        seat = seat_on_turn(table)
        sitter = newcomer()
        taken = decide_sit(sent_away(table, seat), sitter, seat, None).table
        command = AuctionCommand("command-1", taken.id.value, taken.version, AuctionAction.PASS, None)

        decision = decide_step(taken, sitter, command)

        assert decision.refusal is None
        assert decision.table.progress.auction[-1] == Pass(FOREHAND)

    def test_the_sitter_in_a_trick_plays_a_legal_card_of_the_seat(self):
        table = PHASES["in-a-trick"]()
        seat = seat_on_turn(table)
        sitter = newcomer()
        taken = decide_sit(sent_away(table, seat), sitter, seat, None).table
        card = view_of(taken, sitter.account_id, NOBODY).hand.playing.legal_cards[0]

        decision = decide_card(taken, sitter, PlayCardCommand("command-1", taken.id.value, taken.version, card))

        assert decision.refusal is None
        assert decision.table.progress.plays[-1].card == card

    def test_the_other_viewers_see_the_new_name_and_kind_on_the_chair(self):
        table = PHASES["auction"]()
        sitter = newcomer(OccupantKind.AGENT, "Mozart")

        taken = decide_sit(sent_away(table, FOREHAND_SEAT), sitter, FOREHAND_SEAT, None).table

        chair = view_of(taken, account_of(MIDDLEHAND), NOBODY).chairs[FOREHAND_SEAT - 1]
        assert (chair.occupant_name, chair.occupant_kind, chair.is_mine) == ("Mozart", OccupantKind.AGENT, False)

    def test_the_sit_marks_nobody_ready_and_deals_nothing(self):
        table = PHASES["auction"]()
        new_hand = NewHand(1, table.hand)

        taken = decide_sit(sent_away(table, FOREHAND_SEAT), newcomer(), FOREHAND_SEAT, new_hand).table

        assert taken.hand == table.hand
        assert not any(chair.ready for chair in taken.chairs)


class TestTheDeclarersSkat:
    def test_the_sitter_holds_the_picked_up_skat_while_it_is_taken_and_not_put_back(self):
        table, sitter = PHASES["after-the-take"](), newcomer()

        taken = decide_sit(sent_away(table, MIDDLEHAND_SEAT), sitter, MIDDLEHAND_SEAT, None).table

        hand = view_of(taken, sitter.account_id, NOBODY).hand
        expected = {*DECK[10:20], *DECK[30:32]}
        assert (set(hand.own_cards), hand.skat_count) == (expected, 0)

    def test_the_sitter_puts_back_two_cards_like_the_declarer_would(self):
        table, sitter = PHASES["after-the-take"](), newcomer()
        taken = decide_sit(sent_away(table, MIDDLEHAND_SEAT), sitter, MIDDLEHAND_SEAT, None).table

        decision = decide_declaring_step(
            taken, sitter, DeclaringCommand("command-1", taken.id.value, taken.version, OWN_PUT_BACK)
        )

        assert decision.refusal is None

    def test_the_put_back_is_shown_to_the_sitter_as_it_is_to_nobody(self):
        table, sitter = PHASES["after-the-put-back"](), newcomer()

        taken = decide_sit(sent_away(table, MIDDLEHAND_SEAT), sitter, MIDDLEHAND_SEAT, None).table

        hand = view_of(taken, sitter.account_id, NOBODY).hand
        assert not set(OWN_PUT_BACK.cards) & set(hand.own_cards)
        assert len(hand.own_cards) == 10
        assert hand.skat_count == 2

    def test_the_sitter_declares_the_game_after_the_put_back(self):
        table, sitter = PHASES["after-the-put-back"](), newcomer()
        taken = decide_sit(sent_away(table, MIDDLEHAND_SEAT), sitter, MIDDLEHAND_SEAT, None).table
        herz = Declare(GameKind.HERZ, hand=False, ouvert=False, announcement=Announcement.NONE)

        decision = decide_declaring_step(
            taken, sitter, DeclaringCommand("command-1", taken.id.value, taken.version, herz)
        )

        assert decision.refusal is None

    def test_the_sitter_is_not_the_declarer_in_a_seat_that_is_not_the_declarers(self):
        table, sitter = PHASES["after-the-take"](), newcomer()

        taken = decide_sit(sent_away(table, FOREHAND_SEAT), sitter, FOREHAND_SEAT, None).table
        decision = decide_declaring_step(
            taken, sitter, DeclaringCommand("command-1", taken.id.value, taken.version, OWN_PUT_BACK)
        )

        assert decision.refusal is Refusal.NOT_DECLARER


class TestAStandingGiveUpRequest:
    def test_the_asker_sent_away_takes_the_request_with_him(self):
        table = asked_by_the_declarer()

        freed = sent_away(table, MIDDLEHAND_SEAT)

        assert freed.progress.give_up is None

    def test_the_request_stays_gone_for_the_sitter(self):
        table = asked_by_the_declarer()
        sitter = newcomer()

        taken = decide_sit(sent_away(table, MIDDLEHAND_SEAT), sitter, MIDDLEHAND_SEAT, None).table

        assert taken.progress.give_up is None

    def test_a_decliner_sent_away_takes_his_no_and_the_request_stands_for_the_other_opponent(self):
        table = asked_by_the_declarer(declined_by=FOREHAND)

        freed = sent_away(table, FOREHAND_SEAT)

        assert freed.progress.give_up == GiveUpAsked(MIDDLEHAND, None)

    def test_the_other_opponent_can_still_answer_and_the_sitter_can_say_no_again(self):
        table = asked_by_the_declarer(declined_by=FOREHAND)
        sitter = newcomer()
        taken = decide_sit(sent_away(table, FOREHAND_SEAT), sitter, FOREHAND_SEAT, None).table

        by_sitter = decide_decline_give_up(taken, sitter, DeclineGiveUpCommand("c", taken.id.value, taken.version))
        by_other = decide_agree_to_give_up(
            taken, actor_at(taken, REARHAND_SEAT), AgreeToGiveUpCommand("c", taken.id.value, taken.version)
        )

        assert by_sitter.table.progress.give_up == GiveUpAsked(MIDDLEHAND, FOREHAND)
        assert by_other.refusal is None
        assert by_other.table.hand is None

    def test_the_request_of_a_chair_not_in_it_stays(self):
        table = asked_by_the_declarer(declined_by=FOREHAND)

        freed = sent_away(table, REARHAND_SEAT)

        assert freed.progress.give_up == table.progress.give_up


class TestAGameEndedAfterATakeOver:
    def test_the_entry_names_the_account_and_name_of_the_one_who_finished_it_and_keeps_the_agents_earlier_games(self):
        declared, last = before_the_last_card(table_in(HandProgress()))
        earlier = an_entry((account_of(MIDDLEHAND), account_of(REARHAND), account_of(FOREHAND)))
        table = replace(declared, game_list=(earlier,))
        seat = seats_from(table.dealer)[last.position]
        sitter = newcomer(OccupantKind.PERSON, "Dora")

        taken = decide_sit(sent_away(table, seat), sitter, seat, None).table
        ended = decide_card(taken, sitter, PlayCardCommand("command-1", taken.id.value, taken.version, last.card))

        finished = ended.table.game_list[-1]
        assert ended.table.game_list[0] == earlier
        assert (finished.seat_accounts[seat - 1], finished.seat_names[seat - 1]) == (sitter.account_id, "Dora")
        assert isinstance(finished, ListEntry)

    def test_a_hand_all_pass_after_a_take_over_is_passed_in_and_fires_the_bock_trigger(self):
        bock = BockOptions(frozenset({BockTrigger.PASSED_IN}), BockOverlap.APPEND)
        table = table_in(THIRD_PASS_BY_FOREHAND, TableOptions(bock=bock))
        sitter = newcomer()
        taken = decide_sit(sent_away(table, FOREHAND_SEAT), sitter, FOREHAND_SEAT, None).table
        command = AuctionCommand("command-1", taken.id.value, taken.version, AuctionAction.PASS, None)

        ended = decide_step(taken, sitter, command).table

        assert ended.hand is None
        assert ended.bock != BockRounds.start()
