"""A running hand with an open chair stands still, and whoever sits in the chair takes over its seat."""

from dataclasses import replace

import pytest

from skat.engine.bidding import Pass
from skat.engine.bock import BockOptions, BockOverlap, BockRounds, BockTrigger
from skat.engine.cards import DECK
from skat.engine.deal import seats_from
from skat.engine.declaration import Announcement, Declare, Stage
from skat.engine.games import GameKind
from skat.engine.kontra import Word, WordSaid
from skat.table.auction import AuctionAction, AuctionCommand, decide_step
from skat.table.declaring import DeclaringCommand, decide_declaring_step
from skat.table.game_list import ListEntry
from skat.table.kontra import KontraCommand, SeatedWord, decide_kontra
from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    PlayCardCommand,
    ThrowDownCommand,
    decide_agree_to_give_up,
    decide_card,
    decide_decline_give_up,
    decide_throw_down,
)
from skat.table.pushing import PushingCommand, PushingKind, decide_pushing_step
from skat.table.records import (
    GiveUpAsked,
    HandProgress,
    NewHand,
    NoWordSaid,
    OccupantKind,
    Refusal,
    SeatHeld,
    Series,
    TableOptions,
)
from skat.table.rules import (
    acting_position,
    dealt_next,
    decide_sit,
    decide_stand,
    free_seat_for,
    seat_held_in_hand,
    waiting_seat_of,
)
from skat.table.views import turn_seat_of, view_of
from tests.support.open_chairs import (
    FOREHAND,
    FOREHAND_SEAT,
    HAND_COMMANDS,
    KONTRA,
    MIDDLEHAND,
    MIDDLEHAND_SEAT,
    OWN_PUT_BACK,
    PHASES,
    RAMSCH,
    REARHAND,
    REARHAND_SEAT,
    account_of,
    actor_at,
    hand_command,
    newcomer,
    sent_away,
)
from tests.support.played_game import (
    an_entry,
    asked_by_the_declarer,
    before_the_last_card,
    declared_herz_hand,
    table_in,
    with_agents,
)

NOBODY = frozenset[str]()
BOCK = BockOptions(frozenset({BockTrigger.PASSED_IN}), BockOverlap.APPEND)
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
        assert (taken.hand, replace(taken.progress, seats_held=frozenset())) == (table.hand, table.progress)
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

        assert (taken.hand, taken.dealer, replace(taken.progress, seats_held=frozenset())) == (
            table.hand,
            table.dealer,
            table.progress,
        )
        assert not any(chair.ready for chair in taken.chairs)


class TestThePushingStageAfterATakeOver:
    def test_the_sitter_holds_the_twelve_cards_while_the_seat_holds_the_skat_and_puts_two_back(self):
        table, sitter = PHASES["pushing-after-the-take"](), newcomer()
        taken = decide_sit(sent_away(table, FOREHAND_SEAT), sitter, FOREHAND_SEAT, None).table

        hand = view_of(taken, sitter.account_id, NOBODY).hand
        put_back = PushingCommand("command-1", taken.id.value, taken.version, PushingKind.PUT_BACK, hand.own_cards[:2])
        decision = decide_pushing_step(taken, sitter, put_back)

        assert (len(hand.own_cards), hand.skat_count, hand.pushing.stage) == (12, 0, Stage.DISCARDING)
        assert decision.refusal is None

    def test_the_sitter_sees_no_card_the_seat_may_not_see_after_the_skat_was_pushed_on(self):
        table, sitter = PHASES["pushing-after-the-push"](), newcomer()
        taken = decide_sit(sent_away(table, MIDDLEHAND_SEAT), sitter, MIDDLEHAND_SEAT, None).table

        hand = view_of(taken, sitter.account_id, NOBODY).hand
        seats_own = view_of(table, account_of(MIDDLEHAND), NOBODY).hand

        assert (hand.own_cards, hand.skat_count) == (seats_own.own_cards, seats_own.skat_count)
        assert (hand.pushing.moves, hand.pushes) == (seats_own.pushing.moves, 1)

    def test_the_sitter_moves_the_stage_on_and_the_hand_goes_on(self):
        table, sitter = PHASES["pushing-start"](), newcomer()
        taken = decide_sit(sent_away(table, FOREHAND_SEAT), sitter, FOREHAND_SEAT, None).table
        push = PushingCommand("command-1", taken.id.value, taken.version, PushingKind.PUSH)

        pushed = decide_pushing_step(taken, sitter, push).table

        assert seat_on_turn(pushed) == MIDDLEHAND_SEAT
        assert view_of(pushed, sitter.account_id, NOBODY).hand.pushes == 1


class TestTheKontraWordAfterATakeOver:
    def test_the_sitter_in_an_opponents_seat_is_offered_the_word_and_has_it_accepted(self):
        table, sitter = table_in(declared_herz_hand(), KONTRA), newcomer()
        taken = decide_sit(sent_away(table, REARHAND_SEAT), sitter, REARHAND_SEAT, None).table

        offered = view_of(taken, sitter.account_id, NOBODY).hand.playing.kontra.my_word
        said = decide_kontra(taken, sitter, KontraCommand("command-1", taken.id.value, taken.version, Word.KONTRA))

        assert offered is Word.KONTRA
        assert said.refusal is None
        assert view_of(said.table, sitter.account_id, NOBODY).hand.playing.kontra.said == (
            SeatedWord(REARHAND_SEAT, Word.KONTRA),
        )

    def test_a_word_the_seat_said_stays_said_for_the_sitter(self):
        table = table_in(declared_herz_hand(), KONTRA)
        table = replace(table, progress=replace(table.progress, words=(WordSaid(REARHAND, Word.KONTRA, 0),)))
        sitter = newcomer()

        taken = decide_sit(sent_away(table, REARHAND_SEAT), sitter, REARHAND_SEAT, None).table

        before = view_of(table, account_of(MIDDLEHAND), NOBODY).hand.playing.kontra
        after = view_of(taken, sitter.account_id, NOBODY).hand.playing.kontra
        assert before.said == (SeatedWord(REARHAND_SEAT, Word.KONTRA),)
        assert (after.said, after.factor) == (before.said, before.factor)


class TestAStandingNoWord:
    def answered(self, *positions):
        table = table_in(declared_herz_hand(), KONTRA)
        no_words = frozenset(NoWordSaid(position, Word.KONTRA) for position in positions)
        return replace(table, progress=replace(table.progress, no_words=no_words))

    def test_a_seat_sent_away_takes_its_no_word_and_the_sitter_is_offered_the_word_unanswered(self):
        table, sitter = self.answered(REARHAND), newcomer()

        taken = decide_sit(sent_away(table, REARHAND_SEAT), sitter, REARHAND_SEAT, None).table

        kontra = view_of(taken, sitter.account_id, NOBODY).hand.playing.kontra
        assert taken.progress.no_words == frozenset()
        assert (kontra.my_word, kontra.my_word_answered) == (Word.KONTRA, False)

    def test_the_no_word_of_another_seat_stays(self):
        table = self.answered(REARHAND, FOREHAND)

        freed = sent_away(table, REARHAND_SEAT)

        assert freed.progress.no_words == frozenset({NoWordSaid(FOREHAND, Word.KONTRA)})

    def test_the_sitter_can_answer_no_word_again(self):
        table, sitter = self.answered(REARHAND), newcomer()
        taken = decide_sit(sent_away(table, REARHAND_SEAT), sitter, REARHAND_SEAT, None).table

        answered = decide_kontra(taken, sitter, KontraCommand("command-1", taken.id.value, taken.version, None))

        assert answered.table.version == taken.version + 1
        assert answered.table.progress.no_words == frozenset({NoWordSaid(REARHAND, Word.KONTRA)})


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


def before_the_last_game_of_a_bock_series():
    """The third game of three, in a Bock round, played but for its last card; the agent's seat earlier took part."""
    declared, last = before_the_last_card(table_in(HandProgress(), TableOptions(bock=BOCK)))
    earlier = an_entry((account_of(MIDDLEHAND), account_of(REARHAND), account_of(FOREHAND)))
    table = replace(declared, game_list=(earlier,), series=Series(3, 3), bock=BockRounds((3,)))
    return table, last, seats_from(table.dealer)[last.position]


def last_card(table, actor, last):
    return decide_card(table, actor, PlayCardCommand("command-1", table.id.value, table.version, last.card)).table


def totals_of(table):
    return {
        standing.account_id: standing.total for standing in view_of(table, "account-nobody", NOBODY).series.standings
    }


def stood_up(table, seat):
    """The table once the occupant of `seat` stood up."""
    decision = decide_stand(table, actor_at(table, seat))
    assert decision.refusal is None
    return decision.table


def sat(table, actor, seat):
    decision = decide_sit(table, actor, seat, None)
    assert decision.refusal is None
    return decision.table


OPENINGS = pytest.mark.parametrize("opening", [sent_away, stood_up], ids=["send-away", "stand-up"])


class TestAGameEndedAfterATakeOver:
    @OPENINGS
    def test_the_entry_names_the_account_and_name_of_the_one_who_finished_it_and_keeps_the_agents_earlier_games(
        self, opening
    ):
        declared, last = before_the_last_card(table_in(HandProgress()))
        earlier = an_entry((account_of(MIDDLEHAND), account_of(REARHAND), account_of(FOREHAND)))
        table = replace(declared, game_list=(earlier,))
        seat = seats_from(table.dealer)[last.position]
        sitter = newcomer(OccupantKind.PERSON, "Dora")

        taken = decide_sit(opening(table, seat), sitter, seat, None).table
        ended = decide_card(taken, sitter, PlayCardCommand("command-1", taken.id.value, taken.version, last.card))

        finished = ended.table.game_list[-1]
        assert ended.table.game_list[0] == earlier
        assert (finished.seat_accounts[seat - 1], finished.seat_names[seat - 1]) == (sitter.account_id, "Dora")
        assert isinstance(finished, ListEntry)

    def test_the_send_away_keeps_the_series_the_bock_rounds_and_the_list(self):
        table, _, seat = before_the_last_game_of_a_bock_series()

        freed = sent_away(table, seat)

        assert (freed.series, freed.bock, freed.game_list) == (table.series, table.bock, table.game_list)

    @OPENINGS
    def test_the_sitter_is_credited_the_game_and_the_former_agent_keeps_his_earlier_credit(self, opening):
        table, last, seat = before_the_last_game_of_a_bock_series()
        agent_account = actor_at(table, seat).account_id
        credit_before = view_of(table, "account-nobody", NOBODY).chairs[seat - 1].total
        sitter = newcomer()

        taken = decide_sit(opening(table, seat), sitter, seat, None).table
        ended = last_card(taken, sitter, last)
        agent_finishing = last_card(table, actor_at(table, seat), last)

        totals = totals_of(ended)
        assert totals[agent_account] == credit_before
        assert totals[sitter.account_id] == totals_of(agent_finishing)[agent_account] - credit_before

    @OPENINGS
    def test_the_game_scores_under_the_bock_factor_it_ran_under_as_if_the_agent_had_finished_it(self, opening):
        table, last, seat = before_the_last_game_of_a_bock_series()
        sitter = newcomer()

        taken = decide_sit(opening(table, seat), sitter, seat, None).table
        finished = last_card(taken, sitter, last).game_list[-1]
        by_agent = last_card(table, actor_at(table, seat), last).game_list[-1]

        assert finished.bock_factor > 1
        assert replace(finished, seat_accounts=by_agent.seat_accounts, seat_names=by_agent.seat_names) == by_agent

    def test_a_hand_all_pass_after_a_take_over_is_passed_in_and_fires_the_bock_trigger(self):
        table = table_in(THIRD_PASS_BY_FOREHAND, TableOptions(bock=BOCK))
        sitter = newcomer()
        taken = decide_sit(sent_away(table, FOREHAND_SEAT), sitter, FOREHAND_SEAT, None).table
        command = AuctionCommand("command-1", taken.id.value, taken.version, AuctionAction.PASS, None)

        ended = decide_step(taken, sitter, command).table

        assert ended.hand is None
        assert ended.bock != BockRounds.start()


def replaced(table, leaver_seat):
    """The leaver of `leaver_seat`, and the table once he stood up and a newcomer took his chair."""
    leaver = actor_at(table, leaver_seat)
    return leaver, sat(stood_up(table, leaver_seat), newcomer(), leaver_seat)


class TestAStandUpDuringAHand:
    @pytest.mark.parametrize("phase", PHASES)
    def test_frees_the_chair_in_one_version_leaves_the_hand_as_it_was_and_marks_the_leaver(self, phase):
        table = PHASES[phase]()
        leaver = actor_at(table, MIDDLEHAND_SEAT)

        decision = decide_stand(table, leaver)
        freed = decision.table

        assert decision.refusal is None
        assert freed.chairs[MIDDLEHAND_SEAT - 1].occupant is None
        assert (freed.version, waiting_seat_of(freed)) == (table.version + 1, MIDDLEHAND_SEAT)
        assert (freed.hand, freed.dealer, freed.game_list, freed.series, freed.bock) == (
            table.hand,
            table.dealer,
            table.game_list,
            table.series,
            table.bock,
        )
        assert replace(freed.progress, seats_held=frozenset(), former_holders=frozenset()) == table.progress
        assert freed.progress.seats_held == frozenset({SeatHeld(leaver.account_id, MIDDLEHAND_SEAT)})

    @pytest.mark.parametrize("phase", PHASES)
    def test_a_newcomer_who_took_over_stands_up_again_and_the_hand_waits_again(self, phase):
        table = waiting_in(phase)
        sitter = newcomer()

        left = stood_up(sat(table, sitter, REARHAND_SEAT), REARHAND_SEAT)

        assert waiting_seat_of(left) == REARHAND_SEAT
        assert SeatHeld(sitter.account_id, REARHAND_SEAT) in left.progress.seats_held

    def test_each_sitter_who_leaves_a_chair_in_turn_is_marked_for_that_chair(self):
        table = PHASES["in-a-trick"]()
        first, second = newcomer(name="Dora"), newcomer(name="Erik")

        taken = sat(stood_up(table, FOREHAND_SEAT), first, FOREHAND_SEAT)
        again = sat(stood_up(taken, FOREHAND_SEAT), second, FOREHAND_SEAT)
        left = stood_up(again, FOREHAND_SEAT)

        assert left.progress.seats_held == {
            SeatHeld(actor_at(table, FOREHAND_SEAT).account_id, FOREHAND_SEAT),
            SeatHeld(first.account_id, FOREHAND_SEAT),
            SeatHeld(second.account_id, FOREHAND_SEAT),
        }

    def test_a_newcomer_plays_a_trick_stands_up_and_the_next_sitter_resumes_the_advanced_hand(self):
        table = PHASES["in-a-trick"]()
        seat = seat_on_turn(table)
        first, second = newcomer(name="Dora"), newcomer(name="Erik")
        taken = sat(stood_up(table, seat), first, seat)

        played = taken
        while len(played.progress.plays) % 3:
            on_turn = seat_on_turn(played)
            actor = first if on_turn == seat else actor_at(played, on_turn)
            card = view_of(played, actor.account_id, NOBODY).hand.playing.legal_cards[0]
            command = PlayCardCommand("command-1", played.id.value, played.version, card)
            played = decide_card(played, actor, command).table
        left = stood_up(played, seat)
        resumed = sat(left, second, seat)

        assert len(played.progress.plays) == len(table.progress.plays) + 2
        assert waiting_seat_of(left) == seat
        assert waiting_seat_of(resumed) is None
        assert (resumed.progress.plays, seat_on_turn(resumed)) == (played.progress.plays, seat_on_turn(played))
        assert resumed.progress.seats_held == {
            SeatHeld(actor_at(table, seat).account_id, seat),
            SeatHeld(first.account_id, seat),
        }

    def test_a_second_leave_of_the_same_chair_is_the_same_mark(self):
        table = PHASES["auction"]()
        leaver = actor_at(table, MIDDLEHAND_SEAT)

        again = stood_up(sat(stood_up(table, MIDDLEHAND_SEAT), leaver, MIDDLEHAND_SEAT), MIDDLEHAND_SEAT)

        assert again.progress.seats_held == {SeatHeld(leaver.account_id, MIDDLEHAND_SEAT)}

    def test_a_stand_up_between_hands_writes_no_mark(self):
        between = replace(PHASES["auction"](), hand=None, progress=HandProgress())

        assert stood_up(between, MIDDLEHAND_SEAT).progress.seats_held == frozenset()

    def test_the_asker_of_a_standing_give_up_request_takes_it_with_him(self):
        assert stood_up(asked_by_the_declarer(), MIDDLEHAND_SEAT).progress.give_up is None

    def test_a_decliner_takes_his_no_and_the_other_opponent_can_still_answer(self):
        table = asked_by_the_declarer(declined_by=FOREHAND)

        taken = sat(stood_up(table, FOREHAND_SEAT), newcomer(), FOREHAND_SEAT)
        agreed = decide_agree_to_give_up(
            taken, actor_at(taken, REARHAND_SEAT), AgreeToGiveUpCommand("c", taken.id.value, taken.version)
        )

        assert taken.progress.give_up == GiveUpAsked(MIDDLEHAND, None)
        assert agreed.refusal is None


class TestOnlyTheOwnSeatUntilTheHandEnds:
    def setup_method(self):
        self.table = PHASES["auction"]()
        self.anna = actor_at(self.table, MIDDLEHAND_SEAT)
        self.ben = actor_at(self.table, REARHAND_SEAT)
        self.two_open = stood_up(stood_up(self.table, MIDDLEHAND_SEAT), REARHAND_SEAT)

    def test_a_leaver_is_refused_another_free_chair_and_nothing_changes(self):
        refused = decide_sit(self.two_open, self.anna, REARHAND_SEAT, None)

        assert (refused.refusal, refused.table, refused.holder) == (Refusal.OWN_SEAT_ONLY, self.two_open, None)

    def test_the_bar_is_refused_for_a_taken_chair_too_and_the_own_chair_when_taken_names_its_holder(self):
        one_open = stood_up(self.table, MIDDLEHAND_SEAT)
        own_taken = sat(self.two_open, newcomer(name="Dora"), MIDDLEHAND_SEAT)

        into_a_taken_chair = decide_sit(one_open, self.anna, FOREHAND_SEAT, None)
        into_the_own_taken_chair = decide_sit(own_taken, self.anna, MIDDLEHAND_SEAT, None)

        assert into_a_taken_chair.refusal is Refusal.OWN_SEAT_ONLY
        assert (into_the_own_taken_chair.refusal, into_the_own_taken_chair.holder) == (Refusal.SEAT_TAKEN, "Dora")

    def test_a_leaver_may_sit_again_in_the_chair_he_left_and_the_hand_moves_again(self):
        back = sat(stood_up(self.table, MIDDLEHAND_SEAT), self.anna, MIDDLEHAND_SEAT)

        assert waiting_seat_of(back) is None
        assert back.progress.auction == self.table.progress.auction

    def test_a_seated_account_is_still_refused_as_already_seated(self):
        one_open = stood_up(self.table, MIDDLEHAND_SEAT)

        assert decide_sit(one_open, self.ben, MIDDLEHAND_SEAT, None).refusal is Refusal.ALREADY_SEATED

    def test_an_account_that_held_no_chair_of_the_hand_takes_every_open_chair_a_leavers_included(self):
        into_the_first = decide_sit(self.two_open, newcomer(), MIDDLEHAND_SEAT, None)
        into_the_second = decide_sit(self.two_open, newcomer(), REARHAND_SEAT, None)

        assert (into_the_first.refusal, into_the_second.refusal) == (None, None)

    def test_two_leavers_may_each_take_only_their_own_chair(self):
        crossed = [
            decide_sit(self.two_open, self.anna, REARHAND_SEAT, None).refusal,
            decide_sit(self.two_open, self.ben, MIDDLEHAND_SEAT, None).refusal,
        ]
        own = [
            decide_sit(self.two_open, self.anna, MIDDLEHAND_SEAT, None).refusal,
            decide_sit(self.two_open, self.ben, REARHAND_SEAT, None).refusal,
        ]

        assert (crossed, own) == ([Refusal.OWN_SEAT_ONLY] * 2, [None, None])

    def test_all_three_who_left_come_back_each_only_to_their_own_chair_and_the_hand_moves_once_all_sit(self):
        holders = {seat: actor_at(self.table, seat) for seat in (MIDDLEHAND_SEAT, REARHAND_SEAT, FOREHAND_SEAT)}
        empty = stood_up(self.two_open, FOREHAND_SEAT)

        crossed = {seat: decide_sit(empty, holder, 1 + seat % 3, None).refusal for seat, holder in holders.items()}
        back = empty
        for seat, holder in holders.items():
            back = sat(back, holder, seat)

        assert set(crossed.values()) == {Refusal.OWN_SEAT_ONLY}
        assert decide_sit(empty, newcomer(), FOREHAND_SEAT, None).refusal is None
        assert waiting_seat_of(back) is None

    def test_the_account_is_offered_its_held_chair_only_and_none_while_it_is_taken(self):
        own_taken = sat(self.two_open, newcomer(), REARHAND_SEAT)

        assert free_seat_for(self.two_open, self.ben.account_id) == REARHAND_SEAT
        assert free_seat_for(own_taken, self.ben.account_id) is None
        assert free_seat_for(self.two_open, newcomer().account_id) == MIDDLEHAND_SEAT

    def test_a_record_between_hands_that_still_carries_a_mark_bars_nobody(self):
        mark = SeatHeld(self.anna.account_id, MIDDLEHAND_SEAT)
        between = replace(self.two_open, hand=None, progress=HandProgress(seats_held=frozenset({mark})))

        assert seat_held_in_hand(between, self.anna.account_id) is None
        assert decide_sit(between, self.anna, REARHAND_SEAT, None).refusal is None


def may_sit_in_another_chair(ended, leaver):
    """The hand is over: the leaver, no longer seated, takes a chair that another account freed."""
    freed = stood_up(ended, FOREHAND_SEAT)
    return decide_sit(freed, leaver, FOREHAND_SEAT, None).refusal is None


class TestTheMarkEndsWithTheHand:
    def test_a_game_played_out_clears_the_marks(self):
        declared, last = before_the_last_card(table_in(HandProgress()))
        finisher = seats_from(declared.dealer)[last.position]
        leaver, marked = replaced(declared, MIDDLEHAND_SEAT if finisher != MIDDLEHAND_SEAT else REARHAND_SEAT)

        ended = last_card(marked, actor_at(marked, finisher), last)

        assert marked.progress.seats_held
        assert (ended.hand, ended.progress.seats_held) == (None, frozenset())
        assert may_sit_in_another_chair(ended, leaver)

    def test_a_game_given_up_clears_the_marks(self):
        leaver, marked = replaced(asked_by_the_declarer(), FOREHAND_SEAT)

        ended = decide_agree_to_give_up(
            marked, actor_at(marked, REARHAND_SEAT), AgreeToGiveUpCommand("c", marked.id.value, marked.version)
        ).table

        assert marked.progress.seats_held
        assert (ended.hand, ended.progress.seats_held) == (None, frozenset())
        assert may_sit_in_another_chair(ended, leaver)

    def test_a_game_thrown_down_clears_the_marks(self):
        leaver, marked = replaced(table_in(declared_herz_hand()), REARHAND_SEAT)

        ended = decide_throw_down(
            marked, actor_at(marked, MIDDLEHAND_SEAT), ThrowDownCommand("c", marked.id.value, marked.version)
        ).table

        assert marked.progress.seats_held
        assert (ended.hand, ended.progress.seats_held) == (None, frozenset())
        assert may_sit_in_another_chair(ended, leaver)

    def test_a_hand_passed_in_without_ramsch_clears_the_marks_though_it_keeps_the_auction_steps(self):
        leaver, marked = replaced(table_in(THIRD_PASS_BY_FOREHAND), MIDDLEHAND_SEAT)
        command = AuctionCommand("command-1", marked.id.value, marked.version, AuctionAction.PASS, None)

        ended = decide_step(marked, actor_at(marked, FOREHAND_SEAT), command).table

        assert marked.progress.seats_held
        assert (ended.hand, bool(ended.progress.auction), ended.progress.seats_held) == (None, True, frozenset())
        assert may_sit_in_another_chair(ended, leaver)

    def test_a_hand_passed_in_with_ramsch_keeps_the_marks_for_the_ramsch(self):
        _leaver, marked = replaced(table_in(THIRD_PASS_BY_FOREHAND, RAMSCH), MIDDLEHAND_SEAT)
        command = AuctionCommand("command-1", marked.id.value, marked.version, AuctionAction.PASS, None)

        ramsch = decide_step(marked, actor_at(marked, FOREHAND_SEAT), command).table

        assert ramsch.hand is not None
        assert ramsch.progress.seats_held == marked.progress.seats_held

    def test_the_next_deal_starts_without_marks(self):
        table = PHASES["auction"]()
        _, marked = replaced(table, MIDDLEHAND_SEAT)

        dealt = dealt_next(replace(marked, hand=None), NewHand(1, table.hand))

        assert dealt.progress.seats_held == frozenset()
