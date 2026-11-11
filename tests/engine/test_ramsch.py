import random
from functools import cache
from itertools import pairwise, permutations

import pytest

from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position, deal
from skat.engine.ramsch import (
    DurchmarschRule,
    JungfrauRule,
    RamschOptions,
    RamschPlayedOut,
    RamschPlaying,
    RamschScoring,
    play_ramsch_card,
    ramsch_after,
    reckon_ramsch,
    start_ramsch,
)
from skat.engine.tricks import CardPlayed, CompletedTrick, PlayRefusal

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
POSITIONS = (FOREHAND, MIDDLEHAND, REARHAND)
JACKS_BY_STRENGTH = tuple(Card(suit, Rank.JACK) for suit in (Suit.KREUZ, Suit.PIK, Suit.HERZ, Suit.KARO))
SUIT_ORDER = (Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.NINE, Rank.EIGHT, Rank.SEVEN)
HERZ_KING, PIK_SEVEN = Card(Suit.HERZ, Rank.KING), Card(Suit.PIK, Rank.SEVEN)
HERZ_SEVEN, HERZ_JACK = Card(Suit.HERZ, Rank.SEVEN), Card(Suit.HERZ, Rank.JACK)
KARO_JACK, KREUZ_ACE = Card(Suit.KARO, Rank.JACK), Card(Suit.KREUZ, Rank.ACE)
KARO_ACE, KARO_TEN = Card(Suit.KARO, Rank.ACE), Card(Suit.KARO, Rank.TEN)


def cards_of(suit: Suit, *ranks: Rank) -> tuple[Card, ...]:
    return tuple(Card(suit, rank) for rank in ranks)


def lying_deal() -> Deal:
    """Forehand holds the four jacks and the Kreuz suit from the Ace to the Eight; the skat is Karo Ace and Ten."""
    forehand = (
        *JACKS_BY_STRENGTH,
        *cards_of(Suit.KREUZ, Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.NINE, Rank.EIGHT),
    )
    skat = (KARO_ACE, KARO_TEN)
    rest = [card for card in DECK if card not in {*forehand, *skat}]
    return Deal(forehand=forehand, middlehand=tuple(rest[:10]), rearhand=tuple(rest[10:]), skat=skat)


def holding(forehand: tuple[Card, ...], middlehand: tuple[Card, ...], rearhand: tuple[Card, ...]) -> RamschPlaying:
    """A Ramsch in which each player holds only the given cards, forehand to lead."""
    return RamschPlaying(
        hands={FOREHAND: forehand, MIDDLEHAND: middlehand, REARHAND: rearhand},
        leader=FOREHAND,
        current=(),
        tricks=(),
        result=None,
        skat=(),
    )


def play_all(state: RamschPlaying, plays: tuple[Card, ...]) -> RamschPlaying:
    for card in plays:
        outcome = play_ramsch_card(state, state.turn, card)
        assert outcome.refusal is None
        state = outcome.state
    return state


def play_out(state: RamschPlaying) -> tuple[RamschPlaying, tuple[CardPlayed, ...]]:
    """Play every turn the first card of the hand that the rules accept."""
    steps: list[CardPlayed] = []
    while state.result is None:
        for card in state.hands[state.turn]:
            outcome = play_ramsch_card(state, state.turn, card)
            if outcome.refusal is None:
                steps.append(CardPlayed(state.turn, card))
                state = outcome.state
                break
    return state, tuple(steps)


def test_a_ramsch_starts_with_forehand_to_lead_and_the_skat_in_no_hand() -> None:
    cards = lying_deal()

    state = start_ramsch(cards)

    assert state.turn is FOREHAND
    assert dict(state.hands) == dict(cards.hands)
    assert state.skat == cards.skat
    assert all(len(hand) == 10 for hand in state.hands.values())
    assert not any(card in hand for hand in state.hands.values() for card in cards.skat)


def test_the_karo_jack_takes_a_trick_against_the_ace_of_the_suit_led() -> None:
    state = holding((KARO_ACE,), (KARO_JACK,), (PIK_SEVEN,))

    state = play_all(state, (KARO_ACE, KARO_JACK, PIK_SEVEN))

    assert state.tricks[0].taker is MIDDLEHAND


@pytest.mark.parametrize(
    "trick",
    [pytest.param(trick, id=" ".join(f"{c.suit.name}" for c in trick)) for trick in permutations(JACKS_BY_STRENGTH, 3)],
)
def test_the_jacks_rank_kreuz_pik_herz_karo(trick: tuple[Card, Card, Card]) -> None:
    state = holding((trick[0],), (trick[1],), (trick[2],))
    strongest = min(trick, key=JACKS_BY_STRENGTH.index)

    state = play_all(state, trick)

    assert state.tricks[0].taker is POSITIONS[trick.index(strongest)]


@pytest.mark.parametrize(("higher", "lower"), list(pairwise(SUIT_ORDER)))
def test_a_card_higher_in_the_suit_order_takes_the_trick_without_trump(higher: Rank, lower: Rank) -> None:
    state = holding((Card(Suit.HERZ, lower),), (Card(Suit.HERZ, higher),), (PIK_SEVEN,))

    state = play_all(state, (Card(Suit.HERZ, lower), Card(Suit.HERZ, higher), PIK_SEVEN))

    assert state.tricks[0].taker is MIDDLEHAND


def test_a_player_holding_the_suit_led_must_follow_it() -> None:
    state = play_all(holding((HERZ_KING,), (HERZ_SEVEN, PIK_SEVEN), (KARO_ACE,)), (HERZ_KING,))

    outcome = play_ramsch_card(state, MIDDLEHAND, PIK_SEVEN)

    assert outcome.refusal is PlayRefusal.MUST_FOLLOW
    assert outcome.state == state


@pytest.mark.parametrize("card", [HERZ_JACK, PIK_SEVEN])
def test_the_herz_jack_is_trump_so_a_player_holding_no_other_herz_may_play_any_card(card: Card) -> None:
    state = play_all(holding((HERZ_KING,), (HERZ_JACK, PIK_SEVEN), (KARO_ACE,)), (HERZ_KING,))

    outcome = play_ramsch_card(state, MIDDLEHAND, card)

    assert outcome.refusal is None


@pytest.mark.parametrize(
    ("position", "card", "refusal"),
    [
        (MIDDLEHAND, PIK_SEVEN, PlayRefusal.NOT_YOUR_TURN),
        (FOREHAND, HERZ_JACK, PlayRefusal.NOT_IN_HAND),
    ],
)
def test_a_card_out_of_turn_or_out_of_hand_changes_nothing(
    position: Position, card: Card, refusal: PlayRefusal
) -> None:
    state = holding((HERZ_KING,), (PIK_SEVEN,), (KARO_ACE,))

    outcome = play_ramsch_card(state, position, card)

    assert (outcome.refusal, outcome.state) == (refusal, state)


def test_each_trick_counts_for_its_own_taker_and_the_taker_leads_next() -> None:
    karo, herz, pik = (
        Card(suit, rank) for suit, rank in ((Suit.KARO, Rank.SEVEN), (Suit.HERZ, Rank.SEVEN), (Suit.PIK, Rank.SEVEN))
    )
    state = holding(
        (karo, Card(Suit.HERZ, Rank.EIGHT), Card(Suit.PIK, Rank.NINE)),
        (Card(Suit.KARO, Rank.NINE), herz, Card(Suit.PIK, Rank.EIGHT)),
        (Card(Suit.KARO, Rank.EIGHT), Card(Suit.HERZ, Rank.NINE), pik),
    )
    leaders = []

    for plays in (
        (karo, Card(Suit.KARO, Rank.NINE), Card(Suit.KARO, Rank.EIGHT)),
        (herz, Card(Suit.HERZ, Rank.NINE), Card(Suit.HERZ, Rank.EIGHT)),
        (pik, Card(Suit.PIK, Rank.NINE), Card(Suit.PIK, Rank.EIGHT)),
    ):
        state = play_all(state, plays)
        leaders.append(state.leader)

    assert [trick.taker for trick in state.tricks] == [MIDDLEHAND, REARHAND, FOREHAND]
    assert leaders == [MIDDLEHAND, REARHAND, FOREHAND]


def test_the_tenth_trick_ends_the_ramsch_with_every_count() -> None:
    cards = lying_deal()

    state, _ = play_out(start_ramsch(cards))

    result = state.result
    assert result is not None
    assert [result.tricks_of(position) for position in POSITIONS] == [10, 0, 0]
    assert [result.points_of(position) for position in POSITIONS] == [99, 0, 0]
    assert result.last_trick_taker is FOREHAND
    assert result.skat == cards.skat


@pytest.mark.parametrize("seed", range(5))
def test_all_card_points_are_the_players_or_the_skats(seed: int) -> None:
    cards = deal(random.Random(seed))  # noqa: S311 - seeded shuffle keeps the deal reproducible

    state, _ = play_out(start_ramsch(cards))

    result = state.result
    assert result is not None
    assert sum(result.tricks_of(position) for position in POSITIONS) == 10
    skat_points = sum(card.points for card in cards.skat)
    assert sum(result.points_of(position) for position in POSITIONS) == 120 - skat_points


def test_a_card_after_the_tenth_trick_is_refused_as_over() -> None:
    state, _ = play_out(start_ramsch(lying_deal()))

    outcome = play_ramsch_card(state, FOREHAND, KREUZ_ACE)

    assert outcome.refusal is PlayRefusal.OVER


@pytest.mark.parametrize("seed", range(3))
def test_a_stored_log_of_thirty_cards_replays_to_the_same_state(seed: int) -> None:
    start = start_ramsch(deal(random.Random(seed)))  # noqa: S311 - seeded shuffle keeps the deal reproducible
    played, steps = play_out(start)

    assert len(steps) == 30
    assert ramsch_after(start, steps) == played


def test_a_log_the_rules_refuse_raises_naming_the_step_and_the_reason() -> None:
    start = holding((HERZ_KING,), (HERZ_SEVEN, PIK_SEVEN), (KARO_ACE,))
    steps = (CardPlayed(FOREHAND, HERZ_KING), CardPlayed(MIDDLEHAND, PIK_SEVEN))

    with pytest.raises(ValueError, match="step 2 refused: must-follow"):
        ramsch_after(start, steps)


POINT_RANKS = ((11, Rank.ACE), (10, Rank.TEN), (4, Rank.KING), (3, Rank.QUEEN), (2, Rank.JACK))
DEFAULT_OPTIONS = RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120)


@cache
def point_ranks(total: int, slots: int) -> tuple[Rank, ...] | None:
    if total == 0:
        return ()
    if slots == 0:
        return None
    for value, rank in POINT_RANKS:
        rest = point_ranks(total - value, slots - 1) if value <= total else None
        if rest is not None:
            return (rank, *rest)
    return None


def cards_worth(total: int, slots: int) -> tuple[Card, ...]:
    ranks = point_ranks(total, slots)
    assert ranks is not None
    return tuple(Card(Suit.KARO, rank) for rank in (*ranks, *[Rank.SEVEN] * (slots - len(ranks))))


def played_out(
    points: tuple[int, int, int],
    tricks: tuple[int, int, int],
    skat: int,
    last: Position | None = None,
) -> RamschPlayedOut:
    """A finished Ramsch in which each player took the given tricks worth the given card points."""
    last = last or next(position for position, count in zip(POSITIONS, tricks, strict=True) if count)
    takers = [position for position, count in zip(POSITIONS, tricks, strict=True) for _ in range(count)]
    takers.remove(last)
    takers.append(last)
    cards = {
        position: cards_worth(worth, 3 * count)
        for position, worth, count in zip(POSITIONS, points, tricks, strict=True)
    }
    completed = []
    for taker in takers:
        taken, cards[taker] = cards[taker][:3], cards[taker][3:]
        completed.append(CompletedTrick(leader=FOREHAND, cards=(taken[0], taken[1], taken[2]), taker=taker))
    return RamschPlayedOut(tuple(completed), cards_worth(skat, 2))


def with_options(
    scoring: RamschScoring = RamschScoring.POINTS,
    jungfrau: JungfrauRule = JungfrauRule.DOUBLES_LOSER,
    durchmarsch: DurchmarschRule = DurchmarschRule.WINS_120,
) -> RamschOptions:
    return RamschOptions(scoring, jungfrau, durchmarsch)


ROW_2 = played_out((57, 30, 23), (5, 3, 2), 10, FOREHAND)
ROW_10 = played_out((67, 43, 0), (6, 4, 0), 10, MIDDLEHAND)
ROW_15 = played_out((99, 0, 0), (10, 0, 0), 21, FOREHAND)
BY_TEN, SKAT_TO_LOSER = RamschScoring.POINTS_BY_TEN, RamschScoring.SKAT_TO_LOSER
JUNGFRAU_OFF, DURCHMARSCH_OFF = JungfrauRule.OFF, DurchmarschRule.OFF

RECKONINGS = {
    "the loser is the player with most points, the skat added from the last trick": (
        played_out((47, 40, 23), (4, 4, 2), 10, MIDDLEHAND),
        with_options(),
        1,
        (0, -50, 0),
    ),
    "the skat goes to the last trick's taker, who may then lose": (ROW_2, with_options(), 1, (-67, 0, 0)),
    "tied players with most points both lose in full": (
        played_out((50, 40, 20), (4, 4, 2), 10, MIDDLEHAND),
        with_options(),
        1,
        (-50, -50, 0),
    ),
    "the skat breaks no tie it did not make": (
        played_out((45, 45, 20), (4, 4, 2), 10, FOREHAND),
        with_options(),
        1,
        (-55, 0, 0),
    ),
    "a three-way tie makes all three lose their own points": (
        played_out((30, 40, 40), (3, 4, 3), 10, FOREHAND),
        with_options(),
        1,
        (-40, -40, -40),
    ),
    "dividing by ten rounds the loser's points down": (
        played_out((47, 30, 33), (4, 3, 3), 10, MIDDLEHAND),
        with_options(BY_TEN),
        1,
        (-4, 0, 0),
    ),
    "the loser is judged on unrounded points when dividing by ten": (
        played_out((45, 44, 31), (4, 3, 3), 0),
        with_options(BY_TEN),
        1,
        (-4, 0, 0),
    ),
    "adding the skat to the points loses the most points without it": (
        played_out((50, 40, 20), (4, 4, 2), 10, MIDDLEHAND),
        with_options(SKAT_TO_LOSER),
        1,
        (-60, 0, 0),
    ),
    "adding the skat makes each tied loser pay it": (
        played_out((50, 50, 10), (4, 4, 2), 10, REARHAND),
        with_options(SKAT_TO_LOSER),
        1,
        (-60, -60, 0),
    ),
    "a player with no trick doubles the loser's score": (ROW_10, with_options(), 1, (-134, 0, 0)),
    "a player with no trick changes nothing when Jungfrau is off": (
        ROW_10,
        with_options(jungfrau=JUNGFRAU_OFF),
        1,
        (-67, 0, 0),
    ),
    "a player with a trick in hand leaves the score single": (
        played_out((67, 43, 0), (5, 4, 1), 10, MIDDLEHAND),
        with_options(),
        1,
        (-67, 0, 0),
    ),
    "two players with no trick double the tied losers' score once": (
        played_out((60, 60, 0), (5, 5, 0), 0),
        with_options(),
        1,
        (-120, -120, 0),
    ),
    "all ten tricks score 120 for the taker and nothing for the others": (
        played_out((120, 0, 0), (10, 0, 0), 0),
        with_options(),
        1,
        (120, 0, 0),
    ),
    "a Durchmarsch scores 120 whatever the skat holds": (ROW_15, with_options(), 1, (120, 0, 0)),
    "a Durchmarsch by rearhand scores for rearhand": (
        played_out((0, 0, 99), (0, 0, 10), 21, REARHAND),
        with_options(),
        1,
        (0, 0, 120),
    ),
    "all ten tricks score as a loser when Durchmarsch is off": (
        ROW_15,
        with_options(jungfrau=JUNGFRAU_OFF, durchmarsch=DURCHMARSCH_OFF),
        1,
        (-120, 0, 0),
    ),
    "all ten tricks double as a loser under Jungfrau when Durchmarsch is off": (
        ROW_15,
        with_options(durchmarsch=DURCHMARSCH_OFF),
        1,
        (-240, 0, 0),
    ),
    "a loser with all tricks divides by ten": (
        ROW_15,
        with_options(BY_TEN, JUNGFRAU_OFF, DURCHMARSCH_OFF),
        1,
        (-12, 0, 0),
    ),
    "a loser with all tricks divides by ten before Jungfrau doubles": (
        ROW_15,
        with_options(BY_TEN, durchmarsch=DURCHMARSCH_OFF),
        1,
        (-24, 0, 0),
    ),
    "a loser with all tricks pays the skat added to the points": (
        ROW_15,
        with_options(SKAT_TO_LOSER, JUNGFRAU_OFF, DURCHMARSCH_OFF),
        1,
        (-120, 0, 0),
    ),
    "pushes multiply the loser's score": (ROW_2, with_options(), 8, (-536, 0, 0)),
    "four pushes multiply the loser's score sixteenfold": (ROW_2, with_options(), 16, (-1072, 0, 0)),
    "pushes multiply the Jungfrau-doubled score": (ROW_10, with_options(), 16, (-2144, 0, 0)),
    "Bock's doubling multiplies a Ramsch with no push": (ROW_2, with_options(), 2, (-134, 0, 0)),
    "pushes and Bock's multiplying setting multiply together": (ROW_2, with_options(), 32, (-2144, 0, 0)),
    "a Durchmarsch is multiplied by default": (ROW_15, with_options(), 16, (1920, 0, 0)),
    "a flat Durchmarsch stays 120 under a multiplier": (
        ROW_15,
        with_options(durchmarsch=DurchmarschRule.WINS_120_FLAT),
        16,
        (120, 0, 0),
    ),
    "dividing by ten comes before Jungfrau and the multiplier": (
        played_out((67, 43, 0), (6, 4, 0), 10, FOREHAND),
        with_options(BY_TEN),
        2,
        (-28, 0, 0),
    ),
    "a Durchmarsch scores 120 at a table dividing by ten": (ROW_15, with_options(BY_TEN), 1, (120, 0, 0)),
}


@pytest.mark.parametrize(("played", "options", "multiplier", "gains"), RECKONINGS.values(), ids=RECKONINGS.keys())
def test_a_ramsch_is_reckoned_as_each_table_sets_it(
    played: RamschPlayedOut, options: RamschOptions, multiplier: int, gains: tuple[int, int, int]
) -> None:
    reckoning = reckon_ramsch(played, options, multiplier=multiplier)

    assert dict(reckoning.gains) == dict(zip(POSITIONS, gains, strict=True))


@pytest.mark.parametrize(
    ("durchmarsch", "jungfrau", "gain", "losers"),
    [
        (DurchmarschRule.WINS_120, JungfrauRule.DOUBLES_LOSER, 120, frozenset()),
        (DurchmarschRule.OFF, JungfrauRule.OFF, -120, frozenset({FOREHAND})),
    ],
    ids=["durchmarsch-wins", "durchmarsch-off"],
)
def test_the_reckoning_of_real_play_names_the_winner_or_the_loser(
    durchmarsch: DurchmarschRule, jungfrau: JungfrauRule, gain: int, losers: frozenset[Position]
) -> None:
    finished, _ = play_out(start_ramsch(lying_deal()))
    assert finished.result is not None

    reckoning = reckon_ramsch(finished.result, with_options(jungfrau=jungfrau, durchmarsch=durchmarsch), multiplier=1)

    assert (reckoning.gains[FOREHAND], reckoning.losers) == (gain, losers)


COUNTED = {
    "the skat goes to the last trick's taker under points": (
        played_out((47, 40, 23), (4, 4, 2), 10, REARHAND),
        with_options(),
        (47, 40, 33),
    ),
    "the skat goes to the last trick's taker under points divided by ten": (
        played_out((47, 40, 23), (4, 4, 2), 10, REARHAND),
        with_options(BY_TEN),
        (47, 40, 33),
    ),
    "the skat goes to the seat with the most trick points under skat to loser": (
        played_out((47, 40, 23), (4, 4, 2), 10, REARHAND),
        with_options(SKAT_TO_LOSER),
        (57, 40, 23),
    ),
    "each tied seat with the most trick points adds the skat under skat to loser": (
        played_out((45, 45, 20), (4, 4, 2), 10, REARHAND),
        with_options(SKAT_TO_LOSER),
        (55, 55, 20),
    ),
    "a seat without the most trick points adds no skat under skat to loser even as the last trick's taker": (
        played_out((30, 50, 40), (3, 4, 3), 10, FOREHAND),
        with_options(SKAT_TO_LOSER),
        (30, 60, 40),
    ),
    "a sweep counts 120 under points": (ROW_15, with_options(), (120, 0, 0)),
    "a sweep counts 120 under points divided by ten": (ROW_15, with_options(BY_TEN), (120, 0, 0)),
    "a sweep counts 120 under skat to loser": (ROW_15, with_options(SKAT_TO_LOSER), (120, 0, 0)),
}


@pytest.mark.parametrize(("played", "options", "points"), COUNTED.values(), ids=COUNTED.keys())
def test_each_seat_counts_the_points_its_scoring_gives_it(
    played: RamschPlayedOut, options: RamschOptions, points: tuple[int, int, int]
) -> None:
    reckoning = reckon_ramsch(played, options, multiplier=1)

    assert dict(reckoning.counted_points) == dict(zip(POSITIONS, points, strict=True))


def test_a_reckoning_cannot_be_changed_by_its_reader() -> None:
    reckoning = reckon_ramsch(ROW_2, with_options(), multiplier=1)

    with pytest.raises(TypeError):
        reckoning.gains[FOREHAND] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        reckoning.counted_points[FOREHAND] = 0  # type: ignore[index]
