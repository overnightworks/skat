from skat.engine.cards import Card
from skat.engine.games import GameKind, Trump


def legal_cards(hand: tuple[Card, ...], first: Card | None, kind: GameKind) -> tuple[Card, ...]:
    """The cards of the hand that may be played, given the trick's first card (None for a lead)."""
    if first is None:
        return hand
    led = kind.playing_suit(first)
    following = tuple(card for card in hand if kind.playing_suit(card) == led)
    return following or hand


def trick_winner(trick: tuple[Card, Card, Card], kind: GameKind) -> int:
    """The play-order index of the highest trump in the trick, else of the highest card of the suit led."""
    led = kind.playing_suit(trick[0])

    def beats(index: int) -> tuple[bool, int]:
        card = trick[index]
        suit = kind.playing_suit(card)
        return suit is Trump.TRUMP, kind.strength(card) if suit == led or suit is Trump.TRUMP else -1

    return max(range(3), key=beats)
