from typing import TYPE_CHECKING

import pytest

from skat.engine.cards import Card, Rank, Suit
from skat.engine.declaration import Announcement
from skat.engine.games import GameKind
from skat.engine.giving_up import give_up, opponent_gives_up, shorten, throw_down
from skat.engine.score import Reckoning, Settlement, reckon, settle
from skat.engine.tricks import Ending, PlayedOut, Playing, PlayRefusal, play_card
from tests.support.playing_scenes import (
    FOREHAND,
    JACKS,
    KARO,
    KARO_EIGHT,
    KARO_SEVEN,
    MIDDLEHAND,
    REARHAND,
    scenario,
    started,
)

if TYPE_CHECKING:
    from skat.engine.deal import Position

KREUZ, HERZ, GRAND, NULL = GameKind.KREUZ, GameKind.HERZ, GameKind.GRAND, GameKind.NULL
KARO_ACE, KARO_TEN = Card(Suit.KARO, Rank.ACE), Card(Suit.KARO, Rank.TEN)


def ok(state: Playing, position: Position, card: Card) -> Playing:
    outcome = play_card(state, position, card)
    assert outcome.refusal is None
    return outcome.state


def next_card(state: Playing) -> Playing:
    """The player on turn plays the first card of its hand that is accepted."""
    position = state.turn
    return next(
        outcome.state for card in state.hands[position] if (outcome := play_card(state, position, card)).refusal is None
    )


def after_first_trick(*, declarer_takes: bool) -> Playing:
    """Karo mit 1; the first trick goes to the declarer's ace (21 points) or to middlehand's ace."""
    own_ace = (KARO_ACE,) if declarer_takes else ()
    state = started(cards=((*own_ace, KARO_SEVEN), (KARO_TEN, KARO_EIGHT) if declarer_takes else (KARO_ACE,), ()))
    lead = KARO_ACE if declarer_takes else KARO_SEVEN
    state = ok(state, FOREHAND, lead)
    state = ok(state, MIDDLEHAND, KARO_TEN if declarer_takes else KARO_ACE)
    return next_card(state)


def given_up(state: Playing, *, consented: bool = False) -> PlayedOut:
    outcome = give_up(state, consented=consented)
    assert outcome.refusal is None
    assert outcome.state.result is not None
    return outcome.state.result


def test_karo_mit_1_bid_20_given_up_before_the_first_card_is_lost_at_27() -> None:
    result = given_up(started())
    assert settle(result, 20) == Settlement(won=False, value=27, score=-54)


def test_the_declarer_can_give_up_after_the_first_trick_while_holding_nine_cards() -> None:
    state = after_first_trick(declarer_takes=True)
    assert settle(given_up(state), 20) == Settlement(won=False, value=27, score=-54)


def test_the_declarer_can_give_up_in_the_second_trick_before_his_own_card() -> None:
    state = after_first_trick(declarer_takes=False)
    while state.turn is not FOREHAND:
        state = next_card(state)
    assert (len(state.hands[FOREHAND]), len(state.current)) == (9, 2)
    assert settle(given_up(state), 20) == Settlement(won=False, value=27, score=-54)


def declarer_holding_eight_cards() -> Playing:
    """Karo mit 1 at bid 20 after the declarer played his card to the second trick."""
    state = after_first_trick(declarer_takes=False)
    while len(state.hands[FOREHAND]) == 9:
        state = next_card(state)
    assert len(state.hands[FOREHAND]) == 8
    return state


def test_after_the_declarer_played_his_card_to_the_second_trick_giving_up_needs_consent_and_play_goes_on() -> None:
    state = declarer_holding_eight_cards()
    outcome = give_up(state)
    assert outcome.refusal is PlayRefusal.NEEDS_CONSENT
    assert outcome.state == state
    assert next_card(state).result is None


def test_with_an_opponents_consent_the_declarer_holding_eight_cards_gives_up_lost_at_27() -> None:
    result = given_up(declarer_holding_eight_cards(), consented=True)
    assert settle(result, 20) == Settlement(won=False, value=27, score=-54)


def test_a_bid_of_30_overbid_after_pick_up_is_given_up_at_once_as_lost_at_30() -> None:
    result = given_up(started(HERZ, 30))
    assert settle(result, 30) == Settlement(won=False, value=30, score=-60)


@pytest.mark.parametrize(
    ("kind", "jacks", "bid", "declaration", "score"),
    [
        pytest.param(KREUZ, JACKS[:2], 18, {"hand": True}, -96, id="hand counts: (2 + 2) * 12"),
        pytest.param(
            KREUZ,
            JACKS[:2],
            18,
            {"hand": True, "announcement": Announcement.SCHNEIDER},
            -144,
            id="announced schneider counts: (2 + 4) * 12",
        ),
        pytest.param(
            GRAND,
            JACKS[:2],
            18,
            {"hand": True, "ouvert": True, "announcement": Announcement.SCHWARZ},
            -432,
            id="ouvert counts all seven levels: (2 + 7) * 24",
        ),
        pytest.param(NULL, (), 23, {}, -46, id="null"),
        pytest.param(NULL, (), 59, {"hand": True, "ouvert": True}, -118, id="null ouvert hand"),
        pytest.param(NULL, JACKS[:1], 27, {}, -54, id="overbid null costs the cheapest game reaching the bid"),
    ],
)
def test_a_given_up_game_is_valued_by_its_declared_levels_and_lost(
    kind: GameKind, jacks: tuple[Card, ...], bid: int, declaration: dict[str, object], score: int
) -> None:
    result = given_up(started(kind, bid, jacks=jacks, **declaration))  # type: ignore[arg-type]
    assert settle(result, bid) == Settlement(won=False, value=-score // 2, score=score)


def test_schneider_is_not_counted_for_a_declarer_holding_21_points_who_gives_up() -> None:
    state = after_first_trick(declarer_takes=True)
    assert settle(given_up(state), 18) == Settlement(won=False, value=18, score=-36)


def test_a_lost_given_up_game_gives_the_declarer_minus_50_and_each_opponent_40() -> None:
    settlement = settle(given_up(started()), 20)
    assert reckon(settlement) == Reckoning(declarer=-54 - 50, each_opponent=40)


def test_a_game_already_given_up_or_played_out_refuses_giving_up_and_any_card_as_over() -> None:
    over = give_up(started()).state
    played_out = started()
    while played_out.result is None:
        played_out = next_card(played_out)
    for state in (over, played_out):
        assert give_up(state).refusal is PlayRefusal.OVER
        assert give_up(state).state == state
    assert play_card(over, FOREHAND, over.hands[FOREHAND][0]).refusal is PlayRefusal.OVER


def test_a_given_up_result_keeps_the_tricks_taken_so_far_and_a_played_out_one_is_played_out() -> None:
    state = after_first_trick(declarer_takes=True)
    result = given_up(state)
    assert (result.ending, result.tricks, result.won_by_play) == (Ending.GIVEN_UP, state.tricks, False)
    assert len(state.tricks) == 1
    played_out = started()
    while played_out.result is None:
        played_out = next_card(played_out)
    assert played_out.result.ending is Ending.PLAYED_OUT


def thrown_down(state: Playing, position: Position) -> PlayedOut:
    outcome = throw_down(state, position)
    assert outcome.refusal is None
    assert outcome.state.result is not None
    return outcome.state.result


KREUZ_MIT_2 = {"kind": KREUZ, "bid": 18, "jacks": JACKS[:2]}
DECLARER_20_IN_FOUR_TRICKS = ((FOREHAND, 20), (MIDDLEHAND, 21), (MIDDLEHAND, 22), (REARHAND, 23))
DECLARER_70 = ((FOREHAND, 24), (FOREHAND, 23), (FOREHAND, 23))
OPPONENTS_25 = ((MIDDLEHAND, 12), (REARHAND, 13))
OPPONENTS_60 = ((MIDDLEHAND, 20), (REARHAND, 20), (MIDDLEHAND, 20))


@pytest.mark.parametrize(
    ("scene", "expected"),
    [
        pytest.param(
            {**KREUZ_MIT_2, "taken": (*DECLARER_20_IN_FOUR_TRICKS, (REARHAND, 0))},
            Settlement(won=False, value=36, score=-72),
            id="schneider is not counted for 20 points: (2 + 1) * 12",
        ),
        pytest.param(
            {"kind": KARO, "bid": 20, "taken": DECLARER_70},
            Settlement(won=False, value=27, score=-54),
            id="70 points do not win an overbid game: 18 < 20",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": DECLARER_70, "hand": True, "announcement": Announcement.SCHNEIDER},
            Settlement(won=False, value=72, score=-144),
            id="announced schneider is not yet won at 61 to 89: (2 + 4) * 12",
        ),
    ],
)
def test_a_declarer_whose_game_is_not_yet_won_gives_up_with_consent_lost_by_its_declared_levels(
    scene: dict[str, object], expected: Settlement
) -> None:
    state = scenario(**scene)  # type: ignore[arg-type]
    assert settle(given_up(state, consented=True), state.declared.bid) == expected


@pytest.mark.parametrize("consented", [False, True])
@pytest.mark.parametrize(
    "scene",
    [
        pytest.param({**KREUZ_MIT_2, "taken": ((FOREHAND, 21), (FOREHAND, 21), (FOREHAND, 20))}, id="61 points win"),
        pytest.param(
            {"kind": KARO, "bid": 20, "taken": ((FOREHAND, 32), (FOREHAND, 32), (FOREHAND, 26))},
            id="90 points make schneider: (1 + 2) * 9 = 27 reaches the bid",
        ),
    ],
)
def test_a_game_already_won_cannot_be_given_up_and_nothing_changes(
    scene: dict[str, object], *, consented: bool
) -> None:
    state = scenario(**scene)  # type: ignore[arg-type]
    outcome = give_up(state, consented=consented)
    assert outcome.refusal is PlayRefusal.ALREADY_WON
    assert outcome.state == state


@pytest.mark.parametrize(
    ("scene", "thrower", "expected"),
    [
        pytest.param(
            {**KREUZ_MIT_2, "taken": DECLARER_20_IN_FOUR_TRICKS},
            FOREHAND,
            Settlement(won=False, value=48, score=-96),
            id="declarer at 20 points with a trick: schneider, not schwarz",
        ),
        pytest.param(
            KREUZ_MIT_2,
            FOREHAND,
            Settlement(won=False, value=60, score=-120),
            id="declarer before the first card: schneider and schwarz",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": DECLARER_70},
            FOREHAND,
            Settlement(won=True, value=36, score=36),
            id="declarer at 70 points wins at spiel",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": OPPONENTS_25},
            MIDDLEHAND,
            Settlement(won=True, value=48, score=48),
            id="opponents at 25 points are schneider, not schwarz",
        ),
        pytest.param(
            KREUZ_MIT_2,
            REARHAND,
            Settlement(won=True, value=60, score=60),
            id="opponents before the first card are schneider and schwarz",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": OPPONENTS_60},
            MIDDLEHAND,
            Settlement(won=False, value=36, score=-72),
            id="opponents at 60 points: the declarer reaches 60 and wins nothing",
        ),
        pytest.param(
            {"kind": NULL, "bid": 23, "jacks": ()},
            FOREHAND,
            Settlement(won=False, value=23, score=-46),
            id="null declarer throwing down loses",
        ),
        pytest.param(
            {"kind": NULL, "bid": 23, "jacks": ()},
            MIDDLEHAND,
            Settlement(won=True, value=23, score=23),
            id="null won when an opponent throws and the declarer has no trick",
        ),
    ],
)
def test_a_side_throwing_its_cards_down_ends_the_game_with_the_counts_it_brought_in(
    scene: dict[str, object], thrower: Position, expected: Settlement
) -> None:
    state = scenario(**scene)  # type: ignore[arg-type]
    assert settle(thrown_down(state, thrower), state.declared.bid) == expected


def test_a_card_led_and_not_yet_in_a_completed_trick_counts_for_the_opponents_when_the_declarer_throws_down() -> None:
    taken = ((FOREHAND, 24), (FOREHAND, 17), (FOREHAND, 14))
    state = scenario(KREUZ, 18, taken, jacks=JACKS[:2], cards=((KARO_TEN,), (), ()))
    state = ok(state, FOREHAND, KARO_TEN)
    assert settle(thrown_down(state, FOREHAND), 18) == Settlement(won=False, value=36, score=-72)


@pytest.mark.parametrize(
    ("thrower", "ending"),
    [
        (FOREHAND, Ending.DECLARER_THREW_DOWN),
        (MIDDLEHAND, Ending.OPPONENTS_THREW_DOWN),
        (REARHAND, Ending.OPPONENTS_THREW_DOWN),
    ],
)
def test_a_thrown_down_result_keeps_the_completed_tricks_and_names_the_side_that_threw(
    thrower: Position, ending: Ending
) -> None:
    state = scenario(**KREUZ_MIT_2, taken=DECLARER_70)  # type: ignore[arg-type]
    result = thrown_down(state, thrower)
    assert (result.ending, result.tricks) == (ending, state.tricks)


@pytest.mark.parametrize(
    "how", ["declarer threw down", "opponent threw down", "given up", "opponent gave up", "shortened", "played out"]
)
def test_a_game_that_is_over_refuses_throwing_down_giving_up_and_any_card(how: str) -> None:
    state = started()
    match how:
        case "declarer threw down":
            state = throw_down(state, FOREHAND).state
        case "opponent threw down":
            state = throw_down(state, MIDDLEHAND).state
        case "given up":
            state = give_up(state).state
        case "opponent gave up":
            state = opponent_gives_up(state).state
        case "shortened":
            state = shorten(state, all_agreed=True).state
        case _:
            while state.result is None:
                state = next_card(state)
    assert state.result is not None
    assert throw_down(state, MIDDLEHAND).refusal is PlayRefusal.OVER
    assert throw_down(state, MIDDLEHAND).state == state
    assert give_up(state, consented=True).refusal is PlayRefusal.OVER
    assert give_up(state, consented=True).state == state
    assert opponent_gives_up(state).refusal is PlayRefusal.OVER
    assert opponent_gives_up(state).state == state
    assert shorten(state, all_agreed=True).refusal is PlayRefusal.OVER
    assert shorten(state, all_agreed=True).state == state
    assert play_card(state, FOREHAND, KARO_ACE).refusal is PlayRefusal.OVER


def opponent_gave_up(state: Playing) -> PlayedOut:
    outcome = opponent_gives_up(state)
    assert outcome.refusal is None
    assert outcome.state.result is not None
    return outcome.state.result


DECLARER_90 = ((FOREHAND, 32), (FOREHAND, 32), (FOREHAND, 26))
OPPONENTS_35 = ((MIDDLEHAND, 17), (REARHAND, 18))
NULL_23 = {"kind": NULL, "bid": 23, "jacks": ()}


@pytest.mark.parametrize(
    ("scene", "expected", "ending"),
    [
        pytest.param(
            KREUZ_MIT_2,
            Settlement(won=True, value=36, score=36),
            Ending.CONCEDED,
            id="undecided: won at spiel only, (2 + 1) * 12",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "bid": 20, "hand": True, "announcement": Announcement.SCHNEIDER},
            Settlement(won=True, value=72, score=72),
            Ending.CONCEDED,
            id="undecided: declared hand and announced schneider, (2 + 4) * 12",
        ),
        pytest.param(
            {"kind": KARO, "bid": 24},
            Settlement(won=True, value=27, score=27),
            Ending.CONCEDED,
            id="undecided, bid-forced: schneider awarded, (1 + 2) * 9",
        ),
        pytest.param(
            {"kind": KARO, "bid": 36},
            Settlement(won=True, value=36, score=36),
            Ending.CONCEDED,
            id="undecided, bid-forced: schwarz awarded, (1 + 3) * 9",
        ),
        pytest.param(
            {"kind": KARO, "bid": 24, "taken": ((MIDDLEHAND, 10),)},
            Settlement(won=True, value=27, score=27),
            Ending.CONCEDED,
            id="undecided: the forced schneider is still open after one opponent trick of 10 points",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "hand": True, "announcement": Announcement.SCHWARZ},
            Settlement(won=True, value=96, score=96),
            Ending.CONCEDED,
            id="undecided: announced schwarz, (2 + 6) * 12",
        ),
        pytest.param(
            {"kind": KARO, "bid": 24, "taken": OPPONENTS_35},
            Settlement(won=False, value=27, score=-54),
            Ending.DECIDED,
            id="decided against: the opponents are out of schneider and 18 stays short of 24",
        ),
        pytest.param(
            {"kind": KARO, "bid": 36, "taken": ((MIDDLEHAND, 10),)},
            Settlement(won=False, value=36, score=-72),
            Ending.DECIDED,
            id="decided against: the forced schwarz is out of reach after one opponent trick",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": OPPONENTS_60},
            Settlement(won=False, value=36, score=-72),
            Ending.DECIDED,
            id="decided against: the declarer reaches only 60 with every remaining card",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "hand": True, "announcement": Announcement.SCHNEIDER, "taken": OPPONENTS_35},
            Settlement(won=False, value=72, score=-144),
            Ending.DECIDED,
            id="decided against: announced schneider after the opponents have missed it, (2 + 4) * 12",
        ),
        pytest.param(
            {"kind": KARO, "bid": 45, "hand": True, "taken": ((MIDDLEHAND, 10),)},
            Settlement(won=False, value=45, score=-90),
            Ending.DECIDED,
            id="decided against: the forced schwarz of a hand game is out of reach after one opponent trick",
        ),
        pytest.param(
            {"kind": KARO, "bid": 20, "taken": DECLARER_90},
            Settlement(won=True, value=27, score=27),
            Ending.DECIDED_WON,
            id="decided for the declarer: 90 points make schneider, (1 + 2) * 9",
        ),
        pytest.param(
            NULL_23,
            Settlement(won=True, value=23, score=23),
            Ending.CONCEDED,
            id="null before the declarer's first trick stands won",
        ),
        pytest.param(
            {**NULL_23, "taken": ((FOREHAND, 0),)},
            Settlement(won=False, value=23, score=-46),
            Ending.DECIDED,
            id="null after the declarer's first trick is lost",
        ),
    ],
)
def test_an_opponent_giving_up_ends_the_game_valued_by_how_far_it_was_decided(
    scene: dict[str, object], expected: Settlement, ending: Ending
) -> None:
    state = scenario(**scene)  # type: ignore[arg-type]
    result = opponent_gave_up(state)
    assert result.ending is ending
    assert result.tricks == state.tricks
    assert settle(result, state.declared.bid) == expected


def shortened(state: Playing, *, claim: Announcement = Announcement.NONE) -> PlayedOut:
    outcome = shorten(state, all_agreed=True, claim=claim)
    assert outcome.refusal is None
    assert outcome.state.result is not None
    return outcome.state.result


SCHNEIDER, SCHWARZ = Announcement.SCHNEIDER, Announcement.SCHWARZ
OPPONENTS_30 = ((MIDDLEHAND, 15), (REARHAND, 15))
OPPONENTS_31 = ((MIDDLEHAND, 15), (REARHAND, 16))
KARO_MIT_1_BID_24 = {"kind": KARO, "bid": 24}


@pytest.mark.parametrize(
    ("scene", "claim", "ending", "expected"),
    [
        pytest.param(
            KREUZ_MIT_2,
            Announcement.NONE,
            Ending.SHORTENED,
            Settlement(won=True, value=36, score=36),
            id="1: (2 + 1) * 12",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": OPPONENTS_25},
            Announcement.NONE,
            Ending.SHORTENED,
            Settlement(won=True, value=36, score=36),
            id="2: schneider reached by the opponents' 25 points is not counted unclaimed",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "hand": True},
            Announcement.NONE,
            Ending.SHORTENED,
            Settlement(won=True, value=48, score=48),
            id="3: declared hand counts, (2 + 2) * 12",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "hand": True, "announcement": SCHNEIDER},
            Announcement.NONE,
            Ending.SHORTENED,
            Settlement(won=True, value=72, score=72),
            id="4: announced schneider counts, (2 + 4) * 12",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "hand": True, "announcement": SCHWARZ},
            Announcement.NONE,
            Ending.SHORTENED,
            Settlement(won=True, value=96, score=96),
            id="5: announced schwarz counts six levels, (2 + 6) * 12",
        ),
        pytest.param(
            {"kind": GRAND, "bid": 18, "jacks": JACKS[:2], "hand": True, "ouvert": True, "announcement": SCHWARZ},
            Announcement.NONE,
            Ending.SHORTENED,
            Settlement(won=True, value=216, score=216),
            id="6: ouvert counts seven levels, (2 + 7) * 24",
        ),
        pytest.param(
            NULL_23, Announcement.NONE, Ending.SHORTENED, Settlement(won=True, value=23, score=23), id="7: null"
        ),
        pytest.param(
            {**KREUZ_MIT_2},
            SCHNEIDER,
            Ending.SHORTENED,
            Settlement(won=True, value=48, score=48),
            id="9: demanded schneider, (2 + 2) * 12",
        ),
        pytest.param(
            KREUZ_MIT_2,
            SCHWARZ,
            Ending.SHORTENED,
            Settlement(won=True, value=60, score=60),
            id="10: demanded schwarz, (2 + 3) * 12",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "hand": True, "announcement": SCHNEIDER},
            SCHWARZ,
            Ending.SHORTENED,
            Settlement(won=True, value=84, score=84),
            id="11: announced schneider and demanded schwarz, (2 + 5) * 12",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "hand": True, "announcement": SCHWARZ},
            SCHNEIDER,
            Ending.SHORTENED,
            Settlement(won=True, value=96, score=96),
            id="12: the higher announced level stands over a lower demand",
        ),
        pytest.param(
            KARO_MIT_1_BID_24,
            Announcement.NONE,
            Ending.SHORTENED,
            Settlement(won=False, value=27, score=-54),
            id="13: a level nobody demanded does not reach the bid, (1 + 1) * 9 < 24",
        ),
        pytest.param(
            KARO_MIT_1_BID_24,
            SCHNEIDER,
            Ending.SHORTENED,
            Settlement(won=True, value=27, score=27),
            id="14: demanded schneider reaches the bid, (1 + 2) * 9",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": OPPONENTS_30},
            SCHNEIDER,
            Ending.SHORTENED,
            Settlement(won=True, value=48, score=48),
            id="15: schneider is still reachable at exactly 30 opponent points",
        ),
        pytest.param(
            {"kind": KARO, "bid": 20, "taken": DECLARER_90},
            Announcement.NONE,
            Ending.DECIDED_WON,
            Settlement(won=True, value=27, score=27),
            id="18: already won with 90 points, schneider counts, (1 + 2) * 9",
        ),
        pytest.param(
            {**KARO_MIT_1_BID_24, "taken": DECLARER_90},
            Announcement.NONE,
            Ending.DECIDED_WON,
            Settlement(won=True, value=27, score=27),
            id="19: already won is not overbid, 27 >= 24",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": DECLARER_70},
            Announcement.NONE,
            Ending.DECIDED_WON,
            Settlement(won=True, value=36, score=36),
            id="20: already won at 70 points, (2 + 1) * 12",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": DECLARER_70},
            SCHNEIDER,
            Ending.SHORTENED,
            Settlement(won=True, value=48, score=48),
            id="21: a demand in a won game counts, (2 + 2) * 12",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "taken": OPPONENTS_60},
            Announcement.NONE,
            Ending.DECIDED,
            Settlement(won=False, value=36, score=-72),
            id="22: already lost stays lost, (2 + 1) * 12",
        ),
        pytest.param(
            {**KARO_MIT_1_BID_24, "taken": OPPONENTS_35},
            Announcement.NONE,
            Ending.DECIDED,
            Settlement(won=False, value=27, score=-54),
            id="23: already lost and overbid, raised to 27",
        ),
        pytest.param(
            {**KREUZ_MIT_2, "hand": True, "announcement": SCHNEIDER, "taken": OPPONENTS_35},
            Announcement.NONE,
            Ending.DECIDED,
            Settlement(won=False, value=72, score=-144),
            id="24: lost in the announced level, (2 + 4) * 12",
        ),
    ],
)
def test_the_declarer_shortening_with_every_yes_ends_the_game_valued_by_how_far_it_was_decided(
    scene: dict[str, object], claim: Announcement, ending: Ending, expected: Settlement
) -> None:
    state = scenario(**scene)  # type: ignore[arg-type]
    result = shortened(state, claim=claim)
    assert result.ending is ending
    assert settle(result, state.declared.bid) == expected


@pytest.mark.parametrize(
    ("scene", "declarer_points", "opponents_points", "declarer_tricks", "opponents_tricks"),
    [
        pytest.param(KREUZ_MIT_2, 120, 0, 10, 0, id="before the first card the declarer claims everything"),
        pytest.param({**KREUZ_MIT_2, "taken": OPPONENTS_25}, 95, 25, 8, 2, id="the cards still out count for him"),
    ],
)
def test_a_shortened_game_counts_the_cards_still_out_for_the_declarer(
    scene: dict[str, object],
    declarer_points: int,
    opponents_points: int,
    declarer_tricks: int,
    opponents_tricks: int,
) -> None:
    result = shortened(scenario(**scene))  # type: ignore[arg-type]
    assert result.declarer_points == declarer_points
    assert result.opponents_points == opponents_points
    assert result.declarer_tricks == declarer_tricks
    assert result.opponents_tricks == opponents_tricks


def test_a_shortened_game_reckons_the_declarer_plus_86_and_the_opponents_nothing() -> None:
    result = shortened(scenario(**KREUZ_MIT_2))  # type: ignore[arg-type]
    assert reckon(settle(result, 18)) == Reckoning(declarer=86, each_opponent=0)


def test_a_decided_lost_game_reckons_the_declarer_minus_122_and_each_opponent_40() -> None:
    result = shortened(scenario(**KREUZ_MIT_2, taken=OPPONENTS_60))  # type: ignore[arg-type]
    assert reckon(settle(result, 18)) == Reckoning(declarer=-122, each_opponent=40)


def test_a_card_led_and_not_completed_is_not_in_the_shortened_result() -> None:
    state = scenario(KREUZ, 18, jacks=JACKS[:2], cards=((KARO_TEN,), (), ()))
    state = ok(state, FOREHAND, KARO_TEN)
    result = shortened(state)
    assert (result.tricks, result.ending, result.declarer_points) == (state.tricks, Ending.SHORTENED, 120)
    assert settle(result, 18) == Settlement(won=True, value=36, score=36)


@pytest.mark.parametrize("all_agreed", [False, True])
@pytest.mark.parametrize(
    ("scene", "claim"),
    [
        pytest.param(
            {**KREUZ_MIT_2, "taken": ((MIDDLEHAND, 15), (REARHAND, 16))}, SCHNEIDER, id="schneider at 31 points"
        ),
        pytest.param({**KREUZ_MIT_2, "taken": ((MIDDLEHAND, 0),)}, SCHWARZ, id="schwarz after an opponent trick"),
    ],
)
def test_a_level_the_opponents_put_out_of_reach_cannot_be_demanded_and_nothing_changes(
    scene: dict[str, object], claim: Announcement, *, all_agreed: bool
) -> None:
    state = scenario(**scene)  # type: ignore[arg-type]
    outcome = shorten(state, all_agreed=all_agreed, claim=claim)
    assert outcome.refusal is PlayRefusal.CLAIM_OUT_OF_REACH
    assert outcome.state == state


@pytest.mark.parametrize(
    ("scene", "claim"),
    [
        pytest.param(KREUZ_MIT_2, SCHNEIDER, id="a demand lapses with the no"),
        pytest.param({**KREUZ_MIT_2, "taken": DECLARER_70}, Announcement.NONE, id="a won game plays on"),
        pytest.param({**KREUZ_MIT_2, "taken": OPPONENTS_60}, Announcement.NONE, id="a lost game plays on"),
    ],
)
def test_a_shortening_without_every_yes_needs_consent_and_the_game_goes_on(
    scene: dict[str, object], claim: Announcement
) -> None:
    state = scenario(**scene)  # type: ignore[arg-type]
    outcome = shorten(state, claim=claim)
    assert outcome.refusal is PlayRefusal.NEEDS_CONSENT
    assert outcome.state == state
    assert next_card(state).result is None


def test_a_game_played_on_after_a_refused_shortening_is_scored_as_if_nobody_asked() -> None:
    asked = started()
    outcome = shorten(asked, claim=SCHNEIDER)
    assert outcome.refusal is PlayRefusal.NEEDS_CONSENT
    asked = outcome.state
    unasked = started()
    while asked.result is None:
        asked, unasked = next_card(asked), next_card(unasked)
    assert asked.result is not None
    assert unasked.result is not None
    assert asked.result.ending is Ending.PLAYED_OUT
    assert settle(asked.result, 20) == settle(unasked.result, 20)
