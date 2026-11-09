from dataclasses import replace
from itertools import combinations

from skat.engine.bidding import Declared
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declaring, declare, put_back, take_skat
from skat.engine.games import GameKind
from skat.engine.tricks import CompletedTrick, Playing, start_play

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
KARO, KREUZ = GameKind.KARO, GameKind.KREUZ
CLUBS_JACK, SPADES_JACK, HEARTS_JACK = (Card(suit, Rank.JACK) for suit in (Suit.KREUZ, Suit.PIK, Suit.HERZ))
JACKS = (CLUBS_JACK, SPADES_JACK, HEARTS_JACK)
KARO_SEVEN, KARO_EIGHT = Card(Suit.KARO, Rank.SEVEN), Card(Suit.KARO, Rank.EIGHT)


def dealt(forehand: tuple[Card, ...], middlehand: tuple[Card, ...], rearhand: tuple[Card, ...]) -> Deal:
    """A deal holding the chosen cards first in each hand, the rest filled in deck order."""
    chosen = {*forehand, *middlehand, *rearhand}
    rest = iter(card for card in DECK if card not in chosen)
    hands = [(*prefix, *(next(rest) for _ in range(10 - len(prefix)))) for prefix in (forehand, middlehand, rearhand)]
    return Deal(*hands, tuple(next(rest) for _ in range(2)))


def started(
    kind: GameKind = KARO,
    bid: int = 20,
    *,
    jacks: tuple[Card, ...] = (CLUBS_JACK,),
    hand: bool = False,
    ouvert: bool = False,
    announcement: Announcement = Announcement.NONE,
    cards: tuple[tuple[Card, ...], tuple[Card, ...], tuple[Card, ...]] = ((), (), ()),
) -> Playing:
    """The forehand declares; he holds exactly `jacks` of the jacks, middlehand holds the others."""
    forehand, middlehand, rearhand = cards
    the_deal = dealt((*jacks, *forehand), (*(jack for jack in JACKS if jack not in jacks), *middlehand), rearhand)
    state = Declaring.start(Declared(FOREHAND, bid), the_deal)
    if not hand:
        state = put_back(take_skat(state).state, the_deal.skat).state
    outcome = declare(state, kind, hand=hand, ouvert=ouvert, announcement=announcement)
    assert outcome.refusal is None
    return start_play(outcome.state, the_deal)


def stand_in_trick(taker: Position, points: int) -> CompletedTrick:
    """A completed trick worth `points` to its taker; only the points and the taker matter to the count."""
    cards = next(combo for combo in combinations(DECK, 3) if sum(card.points for card in combo) == points)
    return CompletedTrick(FOREHAND, cards, taker)


def scenario(kind: GameKind, bid: int, taken: tuple[tuple[Position, int], ...] = (), **declaration: object) -> Playing:
    """A game with a skat of no points, in which the listed tricks are completed and the declarer holds the rest."""
    state = started(kind, bid, **declaration)  # type: ignore[arg-type]
    declared = replace(state.declared, skat=(KARO_SEVEN, KARO_EIGHT))
    tricks = tuple(stand_in_trick(taker, points) for taker, points in taken)
    declarer_hand = state.hands[FOREHAND][: 10 - len(tricks)]
    return replace(state, declared=declared, tricks=tricks, hands={**state.hands, FOREHAND: declarer_hand})
