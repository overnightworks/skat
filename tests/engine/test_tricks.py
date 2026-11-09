import random
from dataclasses import dataclass
from itertools import combinations_with_replacement

import pytest

from skat.engine.bidding import Declared
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position, deal
from skat.engine.declaration import (
    Announcement,
    Declaring,
    declare,
    put_back,
    take_skat,
)
from skat.engine.games import GameKind
from skat.engine.giving_up import give_up, throw_down
from skat.engine.score import Reckoning, Settlement, reckon, settle
from skat.engine.tricks import (
    CardPlayed,
    CompletedTrick,
    Ending,
    PlayedOut,
    Playing,
    PlayOutcome,
    PlayRefusal,
    Sides,
    Tally,
    play_card,
    playing_after,
    start_play,
)

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
HERZ, GRAND, NULL, KREUZ = GameKind.HERZ, GameKind.GRAND, GameKind.NULL, GameKind.KREUZ
BID = 30
OVER, NOT_YOUR_TURN = PlayRefusal.OVER, PlayRefusal.NOT_YOUR_TURN
NOT_IN_HAND, MUST_FOLLOW = PlayRefusal.NOT_IN_HAND, PlayRefusal.MUST_FOLLOW
DECLARER_TAKES, OPPONENTS_TAKE = True, False
KARO_SEVEN, KARO_EIGHT, KARO_ACE = Card(Suit.KARO, Rank.SEVEN), Card(Suit.KARO, Rank.EIGHT), Card(Suit.KARO, Rank.ACE)
KARO_TEN, PIK_ACE = Card(Suit.KARO, Rank.TEN), Card(Suit.PIK, Rank.ACE)
HERZ_ACE, HERZ_QUEEN = Card(Suit.HERZ, Rank.ACE), Card(Suit.HERZ, Rank.QUEEN)
CARD_POINTS = (0, 2, 3, 4, 10, 11)
ZERO_CARD, JACK_CARD = KARO_SEVEN, Card(Suit.KARO, Rank.JACK)


def dealt(
    forehand: tuple[Card, ...] = (),
    middlehand: tuple[Card, ...] = (),
    rearhand: tuple[Card, ...] = (),
    skat: tuple[Card, ...] = (),
) -> Deal:
    """A deal holding the chosen cards first in each hand, the rest filled in deck order."""
    chosen = {*forehand, *middlehand, *rearhand, *skat}
    rest = iter(card for card in DECK if card not in chosen)
    sizes = (10, 10, 10, 2)
    filled = [
        (*prefix, *(next(rest) for _ in range(size - len(prefix))))
        for prefix, size in zip((forehand, middlehand, rearhand, skat), sizes, strict=True)
    ]
    return Deal(*filled)


def declared_by(
    the_deal: Deal,
    declarer: Position = FOREHAND,
    kind: GameKind = GRAND,
    *,
    pick_up: tuple[Card, ...] = (),
    bid: int = BID,
    ouvert: bool = False,
    announcement: Announcement = Announcement.NONE,
) -> Declaring:
    state = Declaring.start(Declared(declarer, bid), the_deal)
    if pick_up:
        state = put_back(take_skat(state).state, pick_up).state
    outcome = declare(state, kind, hand=not pick_up, ouvert=ouvert, announcement=announcement)
    assert outcome.refusal is None
    return outcome.state


def started(the_deal: Deal | None = None, declarer: Position = FOREHAND, kind: GameKind = GRAND) -> Playing:
    the_deal = the_deal or dealt(forehand=(KARO_SEVEN,), middlehand=(KARO_ACE, PIK_ACE), rearhand=(KARO_EIGHT,))
    return start_play(declared_by(the_deal, declarer, kind), the_deal)


def ok(outcome: PlayOutcome) -> Playing:
    assert outcome.refusal is None
    return outcome.state


def refused(outcome: PlayOutcome, reason: PlayRefusal, before: Playing) -> None:
    assert outcome.refusal is reason
    assert outcome.state == before


def first_trick_taken_by_middlehand() -> Playing:
    state = ok(play_card(started(), FOREHAND, KARO_SEVEN))
    state = ok(play_card(state, MIDDLEHAND, KARO_ACE))
    return ok(play_card(state, REARHAND, KARO_EIGHT))


def first_accepted(state: Playing) -> Playing:
    """The player on turn plays the first card of its hand that is accepted."""
    position = state.turn
    return next(
        outcome.state for card in state.hands[position] if (outcome := play_card(state, position, card)).refusal is None
    )


def play_out(state: Playing) -> Playing:
    while state.result is None:
        state = first_accepted(state)
    return state


def played_out_game(seed: int, kind: GameKind) -> Playing:
    the_deal = deal(random.Random(seed))  # noqa: S311 - seeded shuffle keeps the deal reproducible
    declarer = list(Position)[seed % 3]
    return play_out(start_play(declared_by(the_deal, declarer, kind), the_deal))


def declarer_trick_points(state: Playing) -> int:
    assert state.result is not None
    declarer = state.result.declared.declarer
    return sum(card.points for trick in state.result.tricks if trick.taker is declarer for card in trick.cards)


def cards_worth(points: int, size: int = 3) -> tuple[Card, ...]:
    suits = iter(Suit)
    for combination in combinations_with_replacement(CARD_POINTS, size):
        if sum(combination) == points:
            ranks = {0: Rank.SEVEN, 2: Rank.JACK, 3: Rank.QUEEN, 4: Rank.KING, 10: Rank.TEN, 11: Rank.ACE}
            return tuple(Card(next(suits, Suit.KARO), ranks[each]) for each in combination)
    raise AssertionError(points)


def played_out(
    takes: tuple[tuple[bool, int], ...],
    kind: GameKind = HERZ,
    skat_points: int = 0,
    ending: Ending = Ending.PLAYED_OUT,
) -> PlayedOut:
    """Chosen tricks of the declarer (middlehand) and the opponents, each worth the given points."""
    the_deal = dealt(skat=cards_worth(skat_points, 2))
    declared = declared_by(the_deal, MIDDLEHAND, kind)
    tricks = tuple(
        CompletedTrick(
            leader=FOREHAND,
            cards=cards_worth(points),
            taker=MIDDLEHAND if by_declarer else REARHAND,
        )
        for by_declarer, points in takes
    )
    return PlayedOut(declared, tricks, ending)


def takes(declarer: tuple[int, ...], opponents: tuple[int, ...] = ()) -> tuple[tuple[bool, int], ...]:
    """The declarer's tricks, then the opponents'; zero-point opponent tricks fill the ten."""
    filler = (0,) * (10 - len(declarer) - len(opponents))
    return tuple((DECLARER_TAKES, points) for points in declarer) + tuple(
        (OPPONENTS_TAKE, points) for points in (*opponents, *filler)
    )


def test_forehand_leads_the_first_trick_and_the_declarer_holds_the_declared_ten_cards() -> None:
    the_deal = dealt()
    declared = declared_by(the_deal, MIDDLEHAND, GRAND)
    state = start_play(declared, the_deal)
    assert state.turn is FOREHAND
    assert state.hands[MIDDLEHAND] == declared.hand
    assert state.hands[FOREHAND] == the_deal.forehand
    assert state.hands[REARHAND] == the_deal.rearhand


def test_a_card_before_forehand_has_led_is_refused_as_not_your_turn() -> None:
    state = started()
    refused(play_card(state, MIDDLEHAND, KARO_ACE), NOT_YOUR_TURN, state)


def test_a_card_the_position_does_not_hold_is_refused_as_not_in_hand() -> None:
    state = started()
    refused(play_card(state, FOREHAND, PIK_ACE), NOT_IN_HAND, state)


def test_a_card_that_does_not_follow_the_suit_led_is_refused_as_must_follow() -> None:
    state = ok(play_card(started(), FOREHAND, KARO_SEVEN))
    refused(play_card(state, MIDDLEHAND, PIK_ACE), MUST_FOLLOW, state)


def test_the_taker_of_a_trick_leads_the_next_one() -> None:
    state = first_trick_taken_by_middlehand()
    assert state.tricks[0].taker is MIDDLEHAND
    assert state.leader is MIDDLEHAND
    refused(play_card(state, FOREHAND, state.hands[FOREHAND][0]), NOT_YOUR_TURN, state)
    assert play_card(state, MIDDLEHAND, PIK_ACE).refusal is None


def test_each_card_of_the_trick_in_progress_is_named_with_the_position_that_played_it() -> None:
    state = ok(play_card(started(), FOREHAND, KARO_SEVEN))
    state = ok(play_card(state, MIDDLEHAND, KARO_ACE))
    assert state.current_plays == (CardPlayed(FOREHAND, KARO_SEVEN), CardPlayed(MIDDLEHAND, KARO_ACE))


def test_the_trick_after_a_taken_one_names_its_cards_from_the_taker_on() -> None:
    state = first_trick_taken_by_middlehand()
    assert state.current_plays == ()
    state = first_accepted(first_accepted(state))
    assert [play.position for play in state.current_plays] == [MIDDLEHAND, REARHAND]
    assert tuple(play.card for play in state.current_plays) == state.current


@pytest.mark.parametrize("kind", [HERZ, GRAND])
@pytest.mark.parametrize("seed", range(5))
def test_a_game_is_ten_tricks_of_three_cards_and_leaves_every_hand_empty(seed: int, kind: GameKind) -> None:
    state = played_out_game(seed, kind)
    assert state.result is not None
    assert all(hand == () for hand in state.hands.values())
    assert len(state.result.tricks) == 10
    assert all(len(trick.cards) == 3 for trick in state.result.tricks)
    assert len({card for trick in state.result.tricks for card in trick.cards}) == 30


def test_any_card_after_the_tenth_trick_is_refused_as_over() -> None:
    state = played_out_game(1, HERZ)
    refused(play_card(state, FOREHAND, KARO_SEVEN), OVER, state)


@pytest.mark.parametrize("kind", [HERZ, GRAND, NULL])
@pytest.mark.parametrize("seed", range(20))
def test_the_two_sides_add_up_to_120_points_and_ten_tricks(seed: int, kind: GameKind) -> None:
    result = played_out_game(seed, kind).result
    assert result is not None
    assert result.declarer_points + result.opponents_points == 120
    assert result.declarer_tricks + result.opponents_tricks == 10


def test_the_running_tally_names_each_side_s_tricks_and_their_card_points() -> None:
    assert first_trick_taken_by_middlehand().tally == Tally(tricks=Sides(0, 1), points=Sides(0, 11))


@pytest.mark.parametrize("kind", [HERZ, GRAND])
@pytest.mark.parametrize("seed", range(5))
def test_the_running_tally_after_the_tenth_trick_is_the_result_s_with_the_skat_left_out(
    seed: int, kind: GameKind
) -> None:
    state = played_out_game(seed, kind)
    assert state.result is not None
    skat_points = sum(card.points for card in state.result.declared.skat)
    assert state.tally == state.result.tally
    assert state.tally.tricks == Sides(state.result.declarer_tricks, state.result.opponents_tricks)
    assert state.tally.points == Sides(state.result.declarer_points - skat_points, state.result.opponents_points)


def test_a_skat_put_back_after_pick_up_counts_for_the_declarer() -> None:
    the_deal = dealt(forehand=(HERZ_ACE, HERZ_QUEEN))
    declared = declared_by(the_deal, FOREHAND, HERZ, pick_up=(HERZ_ACE, HERZ_QUEEN))
    state = play_out(start_play(declared, the_deal))
    assert state.result is not None
    assert state.result.declarer_points == declarer_trick_points(state) + 14


def test_an_untouched_skat_in_a_hand_game_counts_for_the_declarer() -> None:
    the_deal = dealt(skat=(KARO_ACE, KARO_TEN))
    state = play_out(start_play(declared_by(the_deal, FOREHAND, HERZ), the_deal))
    assert state.result is not None
    assert state.result.declarer_points == declarer_trick_points(state) + 21


@pytest.mark.parametrize(("trick_points", "won"), [((22, 22, 13), True), ((22, 22, 12), False)])
def test_a_suit_game_is_won_by_play_with_61_points_the_skat_included(trick_points: tuple[int, ...], won: bool) -> None:
    assert played_out(takes(trick_points), HERZ, skat_points=4).won_by_play is won


@pytest.mark.parametrize(
    ("declarer_tricks", "skat_points", "declarer_schneider", "opponents_schneider"),
    [
        ((22, 22, 22, 22), 2, False, True),
        ((22, 22, 22, 21), 2, False, False),
        ((22, 8), 0, True, False),
        ((22, 9), 0, False, False),
    ],
)
def test_a_side_with_30_points_or_fewer_is_schneider(
    declarer_tricks: tuple[int, ...], skat_points: int, declarer_schneider: bool, opponents_schneider: bool
) -> None:
    result = played_out(takes(declarer_tricks), HERZ, skat_points)
    assert result.declarer_schneider is declarer_schneider
    assert result.opponents_schneider is opponents_schneider


@pytest.mark.parametrize(
    ("chosen", "declarer_schwarz", "opponents_schwarz", "opponents_schneider"),
    [
        (takes((11,) * 10), False, True, True),
        (takes((11,) * 9, (0,)), False, False, True),
        (takes(()), True, False, False),
    ],
)
def test_a_side_is_schwarz_when_it_took_no_trick_however_few_points_it_holds(
    chosen: tuple[tuple[bool, int], ...], declarer_schwarz: bool, opponents_schwarz: bool, opponents_schneider: bool
) -> None:
    result = played_out(chosen)
    assert result.declarer_schwarz is declarer_schwarz
    assert result.opponents_schwarz is opponents_schwarz
    assert result.opponents_schneider is opponents_schneider


@pytest.mark.parametrize(
    ("chosen", "ending", "won"),
    [
        (
            ((OPPONENTS_TAKE, 0),) * 3 + ((DECLARER_TAKES, 0),),
            Ending.DECIDED,
            False,
        ),
        (takes(()), Ending.PLAYED_OUT, True),
    ],
)
def test_a_null_game_is_won_by_play_only_if_the_declarer_takes_no_trick(
    chosen: tuple[tuple[bool, int], ...], ending: Ending, won: bool
) -> None:
    result = played_out(chosen, NULL, ending=ending)
    assert result.won_by_play is won


def test_over_is_refused_before_not_your_turn_and_not_your_turn_before_not_in_hand() -> None:
    finished = played_out_game(2, HERZ)
    refused(play_card(finished, REARHAND, KARO_SEVEN), OVER, finished)
    running = started()
    foreign = running.hands[REARHAND][0]
    refused(play_card(running, MIDDLEHAND, foreign), NOT_YOUR_TURN, running)


def test_starting_play_before_the_declaration_is_an_error() -> None:
    the_deal = dealt()
    still_declaring = Declaring.start(Declared(FOREHAND, BID), the_deal)
    with pytest.raises(ValueError, match="declaration"):
        start_play(still_declaring, the_deal)


def card_log(finished: Playing) -> tuple[CardPlayed, ...]:
    """The cards of a finished game in the order they fell, read from its tricks."""
    assert finished.result is not None
    log = []
    for trick in finished.result.tricks:
        start = list(Position).index(trick.leader)
        log.extend(CardPlayed(list(Position)[(start + offset) % 3], card) for offset, card in enumerate(trick.cards))
    return tuple(log)


def test_an_empty_card_log_replays_to_the_start_state() -> None:
    assert playing_after(started(), ()) == started()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_whole_game_of_thirty_cards_replays_to_the_direct_calls_with_the_result_set(seed: int) -> None:
    finished = played_out_game(seed, HERZ)
    log = card_log(finished)
    the_deal = deal(random.Random(seed))  # noqa: S311 - seeded shuffle keeps the deal reproducible
    declarer = list(Position)[seed % 3]
    start = start_play(declared_by(the_deal, declarer, HERZ), the_deal)
    assert len(log) == 30
    assert playing_after(start, log) == finished
    assert finished.result is not None


def first_trick_log() -> tuple[CardPlayed, ...]:
    return (CardPlayed(FOREHAND, KARO_SEVEN), CardPlayed(MIDDLEHAND, KARO_ACE), CardPlayed(REARHAND, KARO_EIGHT))


def test_a_card_log_replays_to_the_state_after_the_direct_calls() -> None:
    assert playing_after(started(), first_trick_log()) == first_trick_taken_by_middlehand()


def test_a_card_played_out_of_turn_raises_naming_the_refusal_and_the_place() -> None:
    start = started()
    log = (CardPlayed(MIDDLEHAND, KARO_ACE),)
    with pytest.raises(ValueError, match=r"step 1.*not-your-turn"):
        playing_after(start, log)


def test_a_card_not_in_hand_raises_naming_the_refusal_and_the_place() -> None:
    start = started()
    log = (CardPlayed(FOREHAND, KARO_SEVEN), CardPlayed(MIDDLEHAND, KARO_SEVEN))
    with pytest.raises(ValueError, match=r"step 2.*not-in-hand"):
        playing_after(start, log)


def test_a_card_against_the_duty_to_follow_raises_naming_the_refusal_and_the_place() -> None:
    start = started()
    log = (CardPlayed(FOREHAND, KARO_SEVEN), CardPlayed(MIDDLEHAND, PIK_ACE))
    with pytest.raises(ValueError, match=r"step 2.*must-follow"):
        playing_after(start, log)


def test_a_thirty_first_card_raises_naming_the_refusal_and_the_place() -> None:
    log = (*card_log(played_out_game(2, HERZ)), CardPlayed(FOREHAND, KARO_SEVEN))
    the_deal = deal(random.Random(2))  # noqa: S311 - seeded shuffle keeps the deal reproducible
    start = start_play(declared_by(the_deal, list(Position)[2 % 3], HERZ), the_deal)
    with pytest.raises(ValueError, match=r"step 31.*over"):
        playing_after(start, log)


def holding(text: str) -> tuple[Card, ...]:
    """Cards from a suit letter (C, S, H, D) and a rank letter (7, 8, 9, T, J, Q, K, A); slashes part tricks."""
    suits = {"C": Suit.KREUZ, "S": Suit.PIK, "H": Suit.HERZ, "D": Suit.KARO}
    ranks = dict(zip("789TJQKA", Rank, strict=True))
    return tuple(Card(suits[each[0]], ranks[each[1]]) for each in text.split() if each != "/")


@dataclass(frozen=True)
class Scene:
    """A declared game; each hand starts with the cards named and the rest is dealt in deck order."""

    kind: GameKind
    hands: tuple[str, ...]
    script: str = ""
    bid: int = 18
    declarer: Position = FOREHAND
    picks_up: bool = False
    ouvert: bool = False
    announcement: Announcement = Announcement.NONE

    def started(self) -> Playing:
        the_deal = dealt(*(holding(text) for text in self.hands))
        declared = declared_by(
            the_deal,
            self.declarer,
            self.kind,
            pick_up=the_deal.skat if self.picks_up else (),
            bid=self.bid,
            ouvert=self.ouvert,
            announcement=self.announcement,
        )
        return start_play(declared, the_deal)

    def played(self) -> Playing:
        state = self.started()
        for each in holding(self.script):
            state = ok(play_card(state, state.turn, each))
        return state


def result_of(state: Playing) -> PlayedOut:
    assert state.result is not None
    return state.result


@pytest.mark.parametrize(
    ("scene", "tricks", "settlement", "reckoning"),
    [
        pytest.param(
            Scene(NULL, ("SA", "S7", "S8"), "SA S7 S8", bid=23, picks_up=True),
            1,
            Settlement(won=False, value=23, score=-46),
            Reckoning(declarer=-96, each_opponent=40),
            id="null: the declarer takes trick 1",
        ),
        pytest.param(
            Scene(
                NULL,
                (
                    "D9 H8 ST S9 DJ C8 CQ CJ CA H7",
                    "S8 HT DK SQ HK C7 HQ DQ CK SJ",
                    "HJ HA SK SA CT DA C9 D7 D8 DT",
                    "H9 S7",
                ),
                "D9 DQ DA / DT DJ DK",
                declarer=MIDDLEHAND,
            ),
            2,
            Settlement(won=False, value=35, score=-70),
            Reckoning(declarer=-120, each_opponent=40),
            id="null hand: rearhand takes trick 1, the declarer trick 2",
        ),
        pytest.param(
            Scene(
                NULL,
                ("S7 H8 DA", "SK H9 D8", "S8 HQ D7"),
                "S7 SK S8 / H9 HQ H8 / D7 DA D8",
                bid=46,
                picks_up=True,
                ouvert=True,
            ),
            3,
            Settlement(won=False, value=46, score=-92),
            Reckoning(declarer=-142, each_opponent=40),
            id="null ouvert: the declarer's first trick is trick 3",
        ),
        pytest.param(
            Scene(NULL, ("SA", "S7", "S8"), "SA S7 S8", bid=59, ouvert=True),
            1,
            Settlement(won=False, value=59, score=-118),
            Reckoning(declarer=-168, each_opponent=40),
            id="null ouvert hand: the declarer takes trick 1",
        ),
        pytest.param(
            Scene(
                GRAND,
                ("CJ SJ C7", "HJ CA", "C8"),
                "C7 CA C8",
                announcement=Announcement.SCHWARZ,
            ),
            1,
            Settlement(won=False, value=192, score=-384),
            Reckoning(declarer=-434, each_opponent=40),
            id="grand hand mit 2 announced schwarz: the opponents take trick 1",
        ),
        pytest.param(
            Scene(
                KREUZ,
                ("CJ SJ DA HA SA D9", "HJ D7 H7 S7 DT", "D8 H8 S8 DQ"),
                "DA D7 D8 / HA H7 H8 / SA S7 S8 / D9 DT DQ",
                announcement=Announcement.SCHWARZ,
            ),
            4,
            Settlement(won=False, value=96, score=-192),
            Reckoning(declarer=-242, each_opponent=40),
            id="kreuz hand mit 2 announced schwarz: the opponents take trick 4",
        ),
        pytest.param(
            Scene(
                KREUZ,
                ("CJ SJ DA HA S9", "HJ D7 H7 SA", "D8 H8 S8"),
                "DA D7 D8 / HA H7 H8 / S9 SA S8",
                ouvert=True,
            ),
            3,
            Settlement(won=False, value=108, score=-216),
            Reckoning(declarer=-266, each_opponent=40),
            id="kreuz ouvert mit 2: the opponents take trick 3",
        ),
    ],
)
class TestAGameDecidedByATrick:
    def test_it_ends_at_that_trick_and_is_lost_in_the_value_it_was_declared_at(
        self, scene: Scene, tricks: int, settlement: Settlement, reckoning: Reckoning
    ) -> None:
        result = result_of(scene.played())
        assert (result.ending, len(result.tricks)) == (Ending.DECIDED, tricks)
        assert settle(result, scene.bid) == settlement
        assert reckon(settle(result, scene.bid)) == reckoning

    def test_every_further_move_is_refused_as_over_and_changes_nothing(
        self, scene: Scene, tricks: int, settlement: Settlement, reckoning: Reckoning
    ) -> None:
        state = scene.played()
        refused(play_card(state, state.turn, KARO_SEVEN), OVER, state)
        refused(give_up(state, consented=True), OVER, state)
        for position in Position:
            refused(throw_down(state, position), OVER, state)


@pytest.mark.parametrize(
    ("scene", "declarer_points", "opponents_points", "declarer_tricks", "opponents_tricks"),
    [
        pytest.param(Scene(NULL, ("SA", "S7", "S8"), "SA S7 S8", bid=23, picks_up=True), 120, 0, 10, 0, id="null"),
        pytest.param(
            Scene(
                NULL,
                (
                    "D9 H8 ST S9 DJ C8 CQ CJ CA H7",
                    "S8 HT DK SQ HK C7 HQ DQ CK SJ",
                    "HJ HA SK SA CT DA C9 D7 D8 DT",
                    "H9 S7",
                ),
                "D9 DQ DA / DT DJ DK",
                declarer=MIDDLEHAND,
            ),
            106,
            14,
            9,
            1,
            id="null hand",
        ),
        pytest.param(
            Scene(GRAND, ("CJ SJ C7", "HJ CA", "C8"), "C7 CA C8", announcement=Announcement.SCHWARZ),
            109,
            11,
            9,
            1,
            id="grand hand announced schwarz",
        ),
    ],
)
def test_after_an_early_end_the_opponents_keep_what_they_took_and_the_rest_counts_for_the_declarer(
    scene: Scene, declarer_points: int, opponents_points: int, declarer_tricks: int, opponents_tricks: int
) -> None:
    result = result_of(scene.played())
    assert (result.declarer_points, result.opponents_points) == (declarer_points, opponents_points)
    assert (result.declarer_tricks, result.opponents_tricks) == (declarer_tricks, opponents_tricks)


def test_a_null_game_goes_on_when_the_opponents_take_trick_1_and_the_taker_leads_trick_2() -> None:
    state = Scene(NULL, ("S7", "SK", "S8"), "S7 SK S8", bid=23, picks_up=True).played()
    assert state.result is None
    assert state.leader is MIDDLEHAND


def test_a_null_game_the_declarer_never_takes_a_trick_in_is_won_after_ten_tricks() -> None:
    scene = Scene(NULL, ("D7 D8 D9 H7 H8 H9 S7 S8 S9 C7",), bid=23, picks_up=True)
    result = result_of(play_out(scene.started()))
    assert (result.ending, len(result.tricks)) == (Ending.PLAYED_OUT, 10)
    assert settle(result, scene.bid) == Settlement(won=True, value=23, score=23)
    assert reckon(settle(result, scene.bid)) == Reckoning(declarer=73, each_opponent=0)


def test_a_game_announced_schwarz_that_the_declarer_wins_every_trick_of_is_won_after_ten_tricks() -> None:
    scene = Scene(
        KREUZ,
        ("CJ SJ CA CT CK CQ C9 C8 C7 DA", "HJ", "DJ"),
        announcement=Announcement.SCHWARZ,
    )
    result = result_of(play_out(scene.started()))
    assert (result.ending, len(result.tricks)) == (Ending.PLAYED_OUT, 10)
    assert settle(result, scene.bid) == Settlement(won=True, value=96, score=96)
    assert reckon(settle(result, scene.bid)) == Reckoning(declarer=146, each_opponent=0)


@pytest.mark.parametrize(
    "scene",
    [
        pytest.param(
            Scene(KREUZ, ("CJ SJ D7", "HJ DA", "D8"), "D7 DA D8", announcement=Announcement.SCHNEIDER),
            id="announced schneider, the opponents take trick 1",
        ),
        pytest.param(
            Scene(KREUZ, ("CJ SJ D7", "HJ DA", "D8"), "D7 DA D8", picks_up=True),
            id="no announcement, the opponents take trick 1",
        ),
    ],
)
def test_a_game_not_announced_schwarz_plays_on_to_its_tenth_trick_after_an_opponents_trick(scene: Scene) -> None:
    state = scene.played()
    assert state.result is None
    assert len(result_of(play_out(state)).tricks) == 10


def test_a_game_the_declarer_already_holds_61_in_plays_on_to_its_tenth_trick() -> None:
    state = Scene(KREUZ, ("CJ SJ CA CT CK CQ C9 C8 C7 DA", "HJ", "DJ"), picks_up=True).started()
    states = [state]
    while states[-1].result is None:
        states.append(first_accepted(states[-1]))
    after_nine = next(each for each in states if len(each.tricks) == 9)
    assert after_nine.result is None
    assert after_nine.tally.points.declarer + sum(card.points for card in after_nine.declared.skat) >= 61
    assert len(result_of(states[-1]).tricks) == 10
