from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from skat.engine.cards import Card, Rank, Suit
from skat.engine.declaration import Announcement
from skat.engine.games import GameKind
from skat.engine.giving_up import opponent_plays_open
from skat.engine.score import Settlement, settle
from skat.engine.tricks import Ending, Playing, PlayRefusal, play_card
from tests.support.playing_scenes import FOREHAND, JACKS, MIDDLEHAND, REARHAND, scenario

if TYPE_CHECKING:
    from skat.engine.deal import Position

DECLARER, SHORTENER, PARTNER = FOREHAND, MIDDLEHAND, REARHAND
SUITS = {"s": Suit.PIK, "h": Suit.HERZ, "c": Suit.KREUZ}
RANKS = {
    "7": Rank.SEVEN,
    "8": Rank.EIGHT,
    "9": Rank.NINE,
    "T": Rank.TEN,
    "Q": Rank.QUEEN,
    "K": Rank.KING,
    "A": Rank.ACE,
}

GRAND_MIT_2 = {"kind": GameKind.GRAND, "bid": 18, "jacks": JACKS[:2]}
KREUZ_MIT_2 = {"kind": GameKind.KREUZ, "bid": 18, "jacks": JACKS[:2]}
NULL_23 = {"kind": GameKind.NULL, "bid": 23, "jacks": ()}
HEARTS_EXAMPLE = ("h7 h8", "hA hT", "hK hQ")
HEARTS_COUNTER = ("hA h8", "h7 hT", "hK hQ")


def cards(text: str) -> tuple[Card, ...]:
    return tuple(Card(SUITS[each[0]], RANKS[each[1]]) for each in text.split())


def spread(points: int, tricks: int) -> list[int]:
    """`points` split as evenly as whole numbers allow over `tricks` tricks."""
    return [points // tricks + (1 if place < points % tricks else 0) for place in range(tricks)]


def position(
    setup: dict[str, object],
    completed: tuple[int, int],
    hands: tuple[str, str, str],
    *,
    leader: Position = DECLARER,
    current: str = "",
    declarer_tricks: int = 4,
    tricks: int = 8,
) -> Playing:
    """Completed tricks worth `completed` points to the declarer and the opponents, then the hands and the trick."""
    declarer_points, opponents_points = completed
    taken = tuple((DECLARER, points) for points in spread(declarer_points, declarer_tricks)) + tuple(
        (SHORTENER, points) for points in spread(opponents_points, tricks - declarer_tricks)
    )
    state = scenario(**setup, taken=taken)  # type: ignore[arg-type]
    held = dict(zip((DECLARER, SHORTENER, PARTNER), (cards(each) for each in hands), strict=True))
    return replace(state, hands=held, leader=leader, current=cards(current))


# Hands are listed declarer, shortener, partner; "40/52" is the points of the completed tricks, declarer first.
ROWS = [
    pytest.param(
        position(GRAND_MIT_2, (40, 52), HEARTS_EXAMPLE),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 40, Settlement(won=False, value=72, score=-144)),
        id="1 the rule's example: the declarer's two hearts fall under ace and ten, king and queen",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 52), HEARTS_COUNTER),
        SHORTENER,
        (Ending.CONCEDED, 68, Settlement(won=True, value=72, score=72)),
        id="2 the declarer's ace takes a trick: his shown count holds the rest",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 52), ("sK s7", "sA s8", "sQ s9")),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 40, Settlement(won=False, value=72, score=-144)),
        id="3 the shortener answers each lead of the declarer with the card that beats it",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 52), ("sK h7", "s7 hA", "sA s8")),
        SHORTENER,
        (Ending.CONCEDED, 68, Settlement(won=True, value=72, score=72)),
        id="4 the partner can let the declarer's king win",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 52), ("sK h7", "s7 hA", "sA h8")),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 40, Settlement(won=False, value=72, score=-144)),
        id="5 the partner has to overtake with his only spade",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 52), ("", "s8", ""), leader=PARTNER, current="s7 sK", tricks=9, declarer_tricks=4),
        SHORTENER,
        (Ending.CONCEDED, 68, Settlement(won=True, value=72, score=72)),
        id="6 in a trick in progress the shortener's eight cannot beat the king",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 52), ("", "sA", ""), leader=PARTNER, current="s7 sK", tricks=9, declarer_tricks=4),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 40, Settlement(won=False, value=72, score=-144)),
        id="7 in a trick in progress the shortener's ace beats the king",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 52), ("", "s7", "sA"), current="sK", tricks=9, declarer_tricks=4),
        PARTNER,
        (Ending.REST_TO_OPPONENTS, 40, Settlement(won=False, value=72, score=-144)),
        id="8 the opponent who is not on turn plays open and his partner's ace takes the king",
    ),
    pytest.param(
        position(KREUZ_MIT_2, (40, 52), ("c7 c8", "sA sK", "s7 s8"), leader=SHORTENER),
        SHORTENER,
        (Ending.CONCEDED, 68, Settlement(won=True, value=36, score=36)),
        id="9 in a suit game the declarer ruffs the opponents' spades",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 52), ("c7 c8", "sA sK", "s7 s8"), leader=SHORTENER),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 40, Settlement(won=False, value=72, score=-144)),
        id="10 the same cards in Grand: the declarer has no trump to ruff with",
    ),
    pytest.param(
        position(NULL_23, (0, 92), HEARTS_EXAMPLE, declarer_tricks=0),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 0, Settlement(won=True, value=23, score=23)),
        id="11 Null: the declarer takes no trick, so he wins it",
    ),
    pytest.param(
        position(NULL_23, (0, 92), HEARTS_COUNTER, declarer_tricks=0),
        SHORTENER,
        (Ending.CONCEDED, 28, Settlement(won=True, value=23, score=23)),
        id="12 Null: a wrong open play is scored for the declarer, who wins it",
    ),
    pytest.param(
        position({**KREUZ_MIT_2, "bid": 48}, (40, 25), HEARTS_COUNTER),
        SHORTENER,
        (Ending.CONCEDED, 95, Settlement(won=True, value=48, score=48)),
        id="13a the level the bid forces is awarded while the opponents have not reached it",
    ),
    pytest.param(
        position({**KREUZ_MIT_2, "bid": 48}, (40, 52), HEARTS_COUNTER),
        SHORTENER,
        (Ending.DECIDED, 68, Settlement(won=False, value=48, score=-96)),
        id="13b the level the bid forces is out of reach once the opponents hold 52 points",
    ),
    pytest.param(
        position(GRAND_MIT_2, (70, 22), HEARTS_COUNTER),
        SHORTENER,
        (Ending.DECIDED_WON, 70, Settlement(won=True, value=72, score=72)),
        id="14 a won game keeps its real result when the check fails",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 61), HEARTS_COUNTER),
        SHORTENER,
        (Ending.DECIDED, 59, Settlement(won=False, value=72, score=-144)),
        id="15 a lost game stays lost when the check fails",
    ),
    pytest.param(
        position(GRAND_MIT_2, (70, 22), HEARTS_EXAMPLE),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 70, Settlement(won=True, value=72, score=72)),
        id="16 a won game is won with the declarer's points so far when the check holds",
    ),
    pytest.param(
        position(GRAND_MIT_2, (31, 61), HEARTS_EXAMPLE),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 31, Settlement(won=False, value=72, score=-144)),
        id="17 a lost game stays lost when the check holds",
    ),
    pytest.param(
        position(GRAND_MIT_2, (20, 72), HEARTS_EXAMPLE),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 20, Settlement(won=False, value=96, score=-192)),
        id="18 the declarer's 20 points are Schneider",
    ),
    pytest.param(
        position(GRAND_MIT_2, (0, 92), HEARTS_EXAMPLE, declarer_tricks=0),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 0, Settlement(won=False, value=120, score=-240)),
        id="19 a declarer without a trick is Schwarz",
    ),
    pytest.param(
        position(
            {**GRAND_MIT_2, "hand": True, "announcement": Announcement.SCHWARZ},
            (92, 0),
            ("s7 hA", "sA h7", "s8 h8"),
            leader=SHORTENER,
            declarer_tricks=8,
        ),
        SHORTENER,
        (Ending.REST_TO_OPPONENTS, 92, Settlement(won=False, value=192, score=-384)),
        id="20 an announced Schwarz ends at the opponents' first trick, so the search stops there",
    ),
    pytest.param(
        position(GRAND_MIT_2, (40, 52), HEARTS_EXAMPLE),
        PARTNER,
        (Ending.REST_TO_OPPONENTS, 40, Settlement(won=False, value=72, score=-144)),
        id="21 the other opponent plays open",
    ),
]


@pytest.mark.parametrize(("state", "shortener", "expected"), ROWS)
def test_an_opponent_playing_open_ends_the_game_as_the_rule_scores_it(
    state: Playing, shortener: Position, expected: tuple[Ending, int, Settlement]
) -> None:
    outcome = opponent_plays_open(state, shortener)
    assert outcome.refusal is None
    assert outcome.state.result is not None
    ending, declarer_points, settlement = expected
    assert (outcome.state.result.ending, outcome.state.result.declarer_points) == (ending, declarer_points)
    assert settle(outcome.state.result, state.declared.bid) == settlement


def test_a_game_that_is_over_refuses_an_opponent_playing_open_and_nothing_changes() -> None:
    over = opponent_plays_open(position(GRAND_MIT_2, (40, 52), HEARTS_EXAMPLE), SHORTENER).state
    outcome = opponent_plays_open(over, SHORTENER)
    assert (outcome.refusal, outcome.state) == (PlayRefusal.OVER, over)


def test_the_declarer_cannot_play_open_and_nothing_changes() -> None:
    state = position(GRAND_MIT_2, (40, 52), HEARTS_EXAMPLE)
    outcome = opponent_plays_open(state, DECLARER)
    assert (outcome.refusal, outcome.state) == (PlayRefusal.NOT_AN_OPPONENT, state)


def test_a_card_cannot_be_played_after_an_opponent_played_open() -> None:
    state = position(GRAND_MIT_2, (40, 52), HEARTS_EXAMPLE)
    over = opponent_plays_open(state, SHORTENER).state
    assert play_card(over, DECLARER, cards("h7")[0]).refusal is PlayRefusal.OVER
