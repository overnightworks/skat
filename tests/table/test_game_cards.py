from dataclasses import replace

from skat.engine.bidding import Pass
from skat.engine.cards import DECK
from skat.engine.deal import Position, seats_from
from skat.engine.declaration import PutBack, TakeSkat
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring, play_ramsch_card
from skat.engine.schieberamsch import GrandHandRule, Push, PushingRule, Put, Take
from skat.engine.tricks import CardPlayed
from skat.table.game_cards import GameCards, SeatedCard
from skat.table.hand_state import game_of
from skat.table.playing import PlayCardCommand, ThrowDownCommand, decide_card, decide_throw_down
from skat.table.records import Actor, HandProgress, RamschOccasion, RamschSetting, TableOptions
from tests.support.played_game import HERZ_HAND, a_whole_game, declared_herz_hand, table_in

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# table_in deals from seat 2: forehand sits in seat 3, middlehand in seat 1, rearhand in seat 2.
SEATS = seats_from(2)
RECKONING = RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120)
DEALT = (DECK[10:20], DECK[20:30], DECK[0:10])
SKAT = DECK[30:32]


def actor_of(position):
    return Actor(account_id=f"account-{position.name.lower()}", display_name=position.name)


def a_card(table, card, position):
    command = PlayCardCommand("command-1", table.id.value, table.version, card)
    return decide_card(table, actor_of(position), command)


def in_threes(plays):
    return tuple(
        tuple(SeatedCard(SEATS[play.position], play.card) for play in plays[start : start + 3])
        for start in range(0, len(plays), 3)
    )


def with_the_plays(table, plays):
    return replace(table, progress=replace(table.progress, plays=plays))


def finished_by_the_last_card(table):
    plays = a_whole_game(table)
    return a_card(with_the_plays(table, plays[:-1]), plays[-1].card, plays[-1].position).table


def ramsch_options(pushing=None):
    ramsch = RamschSetting(RamschOccasion.PASSED_IN, RECKONING, pushing, GrandHandRule.OFF)
    return TableOptions(ramsch=ramsch)


def all_pass():
    return (Pass(MIDDLEHAND), Pass(REARHAND), Pass(FOREHAND))


def a_whole_ramsch(table):
    state = game_of(table)
    plays = []
    while state.result is None:
        position = state.turn
        card = next(
            each
            for each in DECK
            if each in state.hands[position] and play_ramsch_card(state, position, each).refusal is None
        )
        state = play_ramsch_card(state, position, card).state
        plays.append(CardPlayed(position, card))
    return tuple(plays)


def a_ramsch_ended_by_its_last_card(table):
    plays = a_whole_ramsch(table)
    before = with_the_plays(table, plays[:-1])
    return a_card(before, plays[-1].card, plays[-1].position).table, plays


class TestAGamePlayedOut:
    def test_keeps_every_seats_dealt_ten_the_skat_and_the_tricks_in_the_order_played(self):
        table = table_in(declared_herz_hand())
        plays = a_whole_game(table)

        ended = finished_by_the_last_card(table)

        assert ended.game_list[-1].cards == GameCards(hands=DEALT, skat=SKAT, put_away=(), tricks=in_threes(plays))

    def test_a_declarer_who_took_the_skat_keeps_the_two_cards_he_put_away_under_his_seat(self):
        put_away = (DECK[10], DECK[31])
        picked = replace(
            declared_herz_hand(),
            declaring=(TakeSkat(), PutBack(put_away), replace(HERZ_HAND, hand=False)),
        )

        ended = finished_by_the_last_card(table_in(picked))

        cards = ended.game_list[-1].cards
        assert cards.put_away == tuple(SeatedCard(SEATS[MIDDLEHAND], card) for card in put_away)
        assert (cards.hands, cards.skat) == (DEALT, SKAT)


class TestAGameEndedEarly:
    def test_a_trick_the_end_interrupted_keeps_the_cards_played_to_it(self):
        table = table_in(declared_herz_hand())
        plays = a_whole_game(table)[:4]
        interrupted = with_the_plays(table, plays)

        ended = decide_throw_down(
            interrupted, actor_of(MIDDLEHAND), ThrowDownCommand("command-1", table.id.value, table.version)
        ).table

        cards = ended.game_list[-1].cards
        assert cards.tricks == in_threes(plays)
        assert cards.hands == DEALT


class TestARamsch:
    def test_keeps_the_hands_the_skat_as_it_lay_and_the_tricks(self):
        table = table_in(HandProgress(auction=all_pass()), ramsch_options())

        ended, plays = a_ramsch_ended_by_its_last_card(table)

        assert ended.game_list[-1].cards == GameCards(hands=DEALT, skat=SKAT, put_away=(), tricks=in_threes(plays))

    def test_a_schieberamsch_keeps_what_each_seat_put_away_and_the_hands_it_played_from(self):
        taken = (DECK[0], DECK[1])
        steps = (Take(FOREHAND), Put(FOREHAND, taken), Push(MIDDLEHAND), Push(REARHAND))
        table = table_in(HandProgress(auction=all_pass(), pushing=steps), ramsch_options(PushingRule.JACKS_STAY))

        ended, plays = a_ramsch_ended_by_its_last_card(table)

        cards = ended.game_list[-1].cards
        assert cards.put_away == tuple(SeatedCard(SEATS[FOREHAND], card) for card in taken)
        assert cards.skat == taken
        assert cards.hands == (*DEALT[:2], (*DECK[2:10], *SKAT))
        assert cards.tricks == in_threes(plays)
