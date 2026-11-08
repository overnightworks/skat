from skat.engine.cards import DECK, Suit


def test_deck_is_thirty_two_distinct_cards_of_four_suits_of_eight():
    assert len(DECK) == 32
    assert len(set(DECK)) == 32
    for suit in Suit:
        assert sum(card.suit is suit for card in DECK) == 8


def test_suits_rank_kreuz_pik_herz_karo():
    assert [suit.name for suit in sorted(Suit, key=lambda suit: -suit.value)] == [
        "KREUZ",
        "PIK",
        "HERZ",
        "KARO",
    ]


def test_card_points_follow_the_isko_and_the_deck_holds_120():
    points_by_rank = {card.rank.name: card.points for card in DECK}
    assert points_by_rank == {
        "ACE": 11,
        "TEN": 10,
        "KING": 4,
        "QUEEN": 3,
        "JACK": 2,
        "NINE": 0,
        "EIGHT": 0,
        "SEVEN": 0,
    }
    assert sum(card.points for card in DECK) == 120
