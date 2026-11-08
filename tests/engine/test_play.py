import random

import pytest

from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.games import GameKind, Trump
from skat.engine.play import legal_cards, trick_winner

_SUITS = {"K": Suit.KARO, "H": Suit.HERZ, "P": Suit.PIK, "C": Suit.KREUZ}
_RANKS = {
    "A": Rank.ACE,
    "10": Rank.TEN,
    "K": Rank.KING,
    "Q": Rank.QUEEN,
    "J": Rank.JACK,
    "9": Rank.NINE,
    "8": Rank.EIGHT,
    "7": Rank.SEVEN,
}


def cards(text: str) -> tuple[Card, ...]:
    """Cards written as suit letter plus rank, such as 'HA PJ C10'."""
    return tuple(Card(_SUITS[word[0]], _RANKS[word[1:]]) for word in text.split())


def card(text: str) -> Card:
    return cards(text)[0]


@pytest.mark.parametrize(
    ("kind", "trick", "winner"),
    [
        (GameKind.HERZ, "HA KJ H10", 1),
        (GameKind.GRAND, "HA H10 KJ", 2),
        (GameKind.NULL, "H10 HJ H9", 1),
        (GameKind.HERZ, "PA P10 PK", 0),
        (GameKind.HERZ, "P7 CA P8", 2),
        (GameKind.HERZ, "KJ HA CJ", 2),
        (GameKind.GRAND, "PJ CJ HJ", 1),
    ],
)
def test_the_highest_trump_takes_the_trick_else_the_highest_card_of_the_suit_led(
    kind: GameKind, trick: str, winner: int
) -> None:
    first, second, third = cards(trick)
    assert trick_winner((first, second, third), kind) == winner


@pytest.mark.parametrize(
    ("kind", "hand", "first", "legal"),
    [
        (GameKind.HERZ, "P7 CA H7", "PA", "P7"),
        (GameKind.HERZ, "CA H7 K8", "PA", "CA H7 K8"),
        (GameKind.HERZ, "PJ P7", "PK", "P7"),
        (GameKind.HERZ, "H7 KJ CA", "CJ", "H7 KJ"),
        (GameKind.GRAND, "KJ PA", "PJ", "KJ"),
        (GameKind.NULL, "H7 CJ", "HJ", "H7"),
        (GameKind.HERZ, "CA H7", "H9", "H7"),
    ],
)
def test_a_player_follows_the_suit_led_or_trump_when_he_can_else_plays_any_card(
    kind: GameKind, hand: str, first: str, legal: str
) -> None:
    assert legal_cards(cards(hand), card(first), kind) == cards(legal)


def test_a_lead_may_play_any_card() -> None:
    hand = cards("P7 CA H7")
    assert legal_cards(hand, None, GameKind.HERZ) == hand


@pytest.mark.parametrize("kind", [GameKind.KARO, GameKind.HERZ, GameKind.PIK, GameKind.KREUZ])
def test_a_suit_game_ranks_the_jacks_then_the_trump_suit_above_the_plain_suits(kind: GameKind) -> None:
    suit = kind.suit
    assert suit is not None
    suit_ranks = (Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.NINE, Rank.EIGHT, Rank.SEVEN)
    trumps = cards("CJ PJ HJ KJ") + tuple(Card(suit, rank) for rank in suit_ranks)
    assert len(trumps) == 11
    assert all(kind.playing_suit(trump) is Trump.TRUMP for trump in trumps)
    strengths = [kind.strength(trump) for trump in trumps]
    assert strengths == sorted(strengths, reverse=True)
    assert len(set(strengths)) == 11
    assert sum(kind.playing_suit(candidate) is Trump.TRUMP for candidate in DECK) == 11


def test_grand_has_only_the_four_jacks_as_trump() -> None:
    trumps = [candidate for candidate in DECK if GameKind.GRAND.playing_suit(candidate) is Trump.TRUMP]
    assert trumps == list(cards("CJ PJ HJ KJ"))
    strengths = [GameKind.GRAND.strength(trump) for trump in trumps]
    assert strengths == sorted(strengths, reverse=True)
    assert len(set(strengths)) == 4


@pytest.mark.parametrize(
    ("kind", "order"),
    [
        (GameKind.HERZ, [Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.NINE, Rank.EIGHT, Rank.SEVEN]),
        (GameKind.GRAND, [Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.NINE, Rank.EIGHT, Rank.SEVEN]),
        (GameKind.NULL, [Rank.ACE, Rank.KING, Rank.QUEEN, Rank.JACK, Rank.TEN, Rank.NINE, Rank.EIGHT, Rank.SEVEN]),
    ],
)
def test_plain_suits_rank_by_the_games_order(kind: GameKind, order: list[Rank]) -> None:
    plain = [Card(Suit.PIK, rank) for rank in order]
    assert all(kind.playing_suit(each) is Suit.PIK for each in plain)
    strengths = [kind.strength(each) for each in plain]
    assert strengths == sorted(strengths, reverse=True)
    assert len(set(strengths)) == len(order)


@pytest.mark.parametrize("kind", list(GameKind))
def test_legal_cards_are_a_non_empty_part_of_the_hand_for_many_seeded_hands(kind: GameKind) -> None:
    generator = random.Random(37)  # noqa: S311 - seeded for repeatable hands and no secrets
    for _ in range(200):
        dealt = generator.sample(DECK, 11)
        hand, first = tuple(dealt[:10]), dealt[10]
        legal = legal_cards(hand, first, kind)
        assert legal
        assert [each for each in hand if each in legal] == list(legal)
        assert set(legal_cards(hand, None, kind)) == set(hand)
