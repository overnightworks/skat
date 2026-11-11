from itertools import combinations_with_replacement

import pytest

from skat.engine.bidding import Declared, PassedIn
from skat.engine.bock import (
    BockOptions,
    BockOverlap,
    BockRounds,
    BockTrigger,
    TotalChange,
    advance,
    bock_factor,
    bock_settlement,
    bock_triggered,
    games_left,
)
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declaring, declare, put_back, take_skat
from skat.engine.games import GameKind, Trump
from skat.engine.kontra import Doubling, KontraReach, Word, doubled_reckoning
from skat.engine.ramsch import RamschPlayedOut
from skat.engine.score import Reckoning, Settlement, settle
from skat.engine.tricks import CompletedTrick, PlayedOut

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
HERZ, KREUZ, GRAND = GameKind.HERZ, GameKind.KREUZ, GameKind.GRAND
KONTRA, RE, SUPRA = Word.KONTRA, Word.RE, Word.SUPRA
SIXTY_SIXTY, WON_GRAND_HAND, LOST_AFTER_KONTRA, RE_SAID = (
    BockTrigger.SIXTY_SIXTY,
    BockTrigger.WON_GRAND_HAND,
    BockTrigger.LOST_AFTER_KONTRA,
    BockTrigger.RE,
)
PASSED_IN, SCHNEIDER, SCHWARZ, TOTAL_IN_00 = (
    BockTrigger.PASSED_IN,
    BockTrigger.SCHNEIDER,
    BockTrigger.SCHWARZ,
    BockTrigger.TOTAL_ENDING_IN_00,
)
APPEND, MULTIPLY, IGNORE = BockOverlap.APPEND, BockOverlap.MULTIPLY, BockOverlap.IGNORE
CLUBS_JACK = Card(Suit.KREUZ, Rank.JACK)
CARD_POINTS = (0, 2, 3, 4, 10, 11)
RANKS_BY_POINTS = {0: Rank.SEVEN, 2: Rank.JACK, 3: Rank.QUEEN, 4: Rank.KING, 10: Rank.TEN, 11: Rank.ACE}
LOST = (30, 20)  # 50 points
WIN = (30, 30, 20)  # 80 points, the opponents 40
WIN_SCHNEIDER = (30, 30, 30, 5)  # 95 points
SIXTY = (30, 30)
SEVENTY = (30, 30, 10)
ALL_TRICKS = (12,) * 10
NO_TRICKS: tuple[int, ...] = ()
NO_TOTALS: tuple[TotalChange, ...] = ()
NO_WORDS = Doubling.start()
A_RAMSCH = RamschPlayedOut(tricks=(), skat=())
EVERY_OTHER_TRIGGER = (SIXTY_SIXTY, WON_GRAND_HAND, LOST_AFTER_KONTRA, RE_SAID, SCHNEIDER, SCHWARZ)


def trick_worth(points: int) -> tuple[Card, Card, Card]:
    for combination in combinations_with_replacement(CARD_POINTS, 3):
        if sum(combination) == points:
            first, second, third = (Card(Suit.KARO, RANKS_BY_POINTS[each]) for each in combination)
            return first, second, third
    raise AssertionError(points)


def game(
    kind: GameKind,
    declarer_tricks: tuple[int, ...],
    *,
    trumps: tuple[Card, ...] = (),
    hand: bool = False,
    announcement: Announcement = Announcement.NONE,
) -> PlayedOut:
    """Middlehand declares the kind with the trumps in his hand, a zero-point skat and the tricks worth these points."""
    plain = [card for card in DECK if kind.playing_suit(card) is not Trump.TRUMP and card not in trumps]
    skat = tuple(card for card in plain if card.points == 0)[:2]
    twelve = (*trumps, *(card for card in plain if card not in skat))[:10] + skat
    rest = iter(card for card in DECK if card not in twelve)
    the_deal = Deal(tuple(next(rest) for _ in range(10)), twelve[:10], tuple(next(rest) for _ in range(10)), skat)
    state = Declaring.start(Declared(MIDDLEHAND, 18), the_deal)
    if not hand:
        state = put_back(take_skat(state).state, skat).state
    outcome = declare(state, kind, hand=hand, ouvert=False, announcement=announcement)
    assert outcome.refusal is None
    tricks = tuple(CompletedTrick(FOREHAND, trick_worth(points), MIDDLEHAND) for points in declarer_tricks) + tuple(
        CompletedTrick(FOREHAND, trick_worth(0), REARHAND) for _ in range(10 - len(declarer_tricks))
    )
    return PlayedOut(outcome.state, tricks)


def said(*words: Word) -> Doubling:
    return Doubling(words=words, kontra_by=FOREHAND if words else None, next_speaker_cards=0)


def options_of(*triggers: BockTrigger, overlap: BockOverlap = APPEND) -> BockOptions:
    return BockOptions(triggers=frozenset(triggers), overlap=overlap)


GRAND_HAND_WON = game(GRAND, WIN, hand=True)
GRAND_HAND_LOST = game(GRAND, LOST, hand=True)
HERZ_WON = game(HERZ, WIN)
HERZ_LOST = game(HERZ, LOST)
HERZ_SIXTY = game(HERZ, SIXTY)
SCHNEIDER_WON = game(HERZ, WIN_SCHNEIDER)
SCHNEIDER_LOST = game(HERZ, (20,))
SCHNEIDER_ANNOUNCED_MISSED = game(HERZ, SEVENTY, hand=True, announcement=Announcement.SCHNEIDER)
SCHWARZ_WON = game(HERZ, ALL_TRICKS)
SCHWARZ_LOST = game(HERZ, NO_TRICKS)
SCHWARZ_ANNOUNCED_MISSED = game(HERZ, WIN_SCHNEIDER, hand=True, announcement=Announcement.SCHWARZ)


@pytest.mark.parametrize(
    ("triggers", "ended", "doubling", "totals", "expected"),
    [
        pytest.param((SIXTY_SIXTY,), HERZ_SIXTY, NO_WORDS, NO_TOTALS, True, id="1-sixty-sixty"),
        pytest.param((SIXTY_SIXTY,), game(HERZ, (30, 31)), NO_WORDS, NO_TOTALS, False, id="2-sixty-one"),
        pytest.param((WON_GRAND_HAND,), GRAND_HAND_WON, NO_WORDS, NO_TOTALS, True, id="3-grand-hand-won"),
        pytest.param((WON_GRAND_HAND,), game(GRAND, WIN), NO_WORDS, NO_TOTALS, False, id="4-grand-won-after-skat"),
        pytest.param((WON_GRAND_HAND,), GRAND_HAND_LOST, NO_WORDS, NO_TOTALS, False, id="4-grand-hand-lost"),
        pytest.param((LOST_AFTER_KONTRA,), HERZ_LOST, said(KONTRA), NO_TOTALS, True, id="5-lost-with-kontra"),
        pytest.param((LOST_AFTER_KONTRA,), HERZ_WON, said(KONTRA), NO_TOTALS, False, id="6-won-with-kontra"),
        pytest.param((LOST_AFTER_KONTRA,), HERZ_LOST, NO_WORDS, NO_TOTALS, False, id="6-lost-with-no-word"),
        pytest.param((RE_SAID,), HERZ_WON, said(KONTRA, RE), NO_TOTALS, True, id="7-re-won"),
        pytest.param((RE_SAID,), HERZ_LOST, said(KONTRA, RE), NO_TOTALS, True, id="7-re-lost"),
        pytest.param((RE_SAID,), HERZ_WON, said(KONTRA, RE, SUPRA), NO_TOTALS, True, id="7-supra-after-re"),
        pytest.param((RE_SAID,), HERZ_LOST, said(KONTRA), NO_TOTALS, False, id="8-only-kontra"),
        pytest.param((PASSED_IN,), PassedIn(), NO_WORDS, NO_TOTALS, True, id="9-passed-in"),
        pytest.param((SCHNEIDER,), SCHNEIDER_WON, NO_WORDS, NO_TOTALS, True, id="10-schneider-reached-won"),
        pytest.param((SCHNEIDER,), SCHNEIDER_LOST, NO_WORDS, NO_TOTALS, True, id="10-schneider-reached-lost"),
        pytest.param((SCHNEIDER,), SCHNEIDER_ANNOUNCED_MISSED, NO_WORDS, NO_TOTALS, True, id="10-schneider-announced"),
        pytest.param((SCHNEIDER,), HERZ_WON, NO_WORDS, NO_TOTALS, False, id="10-no-schneider"),
        pytest.param((SCHWARZ,), SCHWARZ_WON, NO_WORDS, NO_TOTALS, True, id="11-schwarz-reached-won"),
        pytest.param((SCHWARZ,), SCHWARZ_LOST, NO_WORDS, NO_TOTALS, True, id="11-schwarz-reached-lost"),
        pytest.param((SCHWARZ,), SCHWARZ_ANNOUNCED_MISSED, NO_WORDS, NO_TOTALS, True, id="11-schwarz-announced"),
        pytest.param((SCHWARZ,), SCHNEIDER_WON, NO_WORDS, NO_TOTALS, False, id="11-schneider-only"),
        pytest.param((TOTAL_IN_00,), HERZ_WON, NO_WORDS, (TotalChange(150, 200),), True, id="12-150-to-200"),
        pytest.param((TOTAL_IN_00,), HERZ_WON, NO_WORDS, (TotalChange(-150, -200),), True, id="12-minus-150-to-200"),
        pytest.param((TOTAL_IN_00,), HERZ_WON, NO_WORDS, (TotalChange(200, 200),), False, id="13-unchanged-200"),
        pytest.param((TOTAL_IN_00,), HERZ_WON, NO_WORDS, (TotalChange(190, 210),), False, id="13-190-to-210"),
        pytest.param((TOTAL_IN_00,), HERZ_WON, NO_WORDS, (TotalChange(50, 0),), False, id="13-down-to-zero"),
        pytest.param(
            (TOTAL_IN_00,),
            HERZ_WON,
            NO_WORDS,
            (TotalChange(200, 200), TotalChange(90, 100)),
            True,
            id="12-one-of-three-seats",
        ),
        pytest.param((PASSED_IN,), A_RAMSCH, NO_WORDS, NO_TOTALS, True, id="17-ramsch-meets-passed-in"),
        pytest.param(EVERY_OTHER_TRIGGER, A_RAMSCH, NO_WORDS, NO_TOTALS, False, id="17-ramsch-meets-no-other-trigger"),
        pytest.param((TOTAL_IN_00,), A_RAMSCH, NO_WORDS, (TotalChange(0, 100),), True, id="17-ramsch-to-100"),
        pytest.param((TOTAL_IN_00,), A_RAMSCH, NO_WORDS, (TotalChange(0, 0),), False, id="17-ramsch-left-at-0"),
        pytest.param((TOTAL_IN_00,), A_RAMSCH, NO_WORDS, (TotalChange(100, 100),), False, id="17-ramsch-left-at-100"),
        pytest.param(
            (PASSED_IN, TOTAL_IN_00), A_RAMSCH, NO_WORDS, (TotalChange(0, -100),), True, id="17-ramsch-meets-both"
        ),
        pytest.param((SIXTY_SIXTY,), HERZ_WON, NO_WORDS, NO_TOTALS, False, id="14-trigger-off"),
        pytest.param((), HERZ_SIXTY, said(KONTRA, RE), (TotalChange(150, 200),), False, id="14-empty-set"),
        pytest.param(
            (SCHNEIDER, SCHWARZ, TOTAL_IN_00, PASSED_IN, WON_GRAND_HAND),
            HERZ_SIXTY,
            NO_WORDS,
            NO_TOTALS,
            False,
            id="14-sixty-sixty-off",
        ),
        pytest.param(
            (SIXTY_SIXTY, WON_GRAND_HAND, LOST_AFTER_KONTRA, RE_SAID),
            SCHNEIDER_WON,
            NO_WORDS,
            NO_TOTALS,
            False,
            id="15-schneider-game",
        ),
        pytest.param(
            (SIXTY_SIXTY, WON_GRAND_HAND, LOST_AFTER_KONTRA, RE_SAID),
            HERZ_WON,
            said(KONTRA, RE),
            NO_TOTALS,
            True,
            id="15-game-with-re",
        ),
        pytest.param((SIXTY_SIXTY,), HERZ_WON, said(KONTRA, RE), NO_TOTALS, False, id="16-re-in-the-only-60-set"),
        pytest.param((SIXTY_SIXTY,), HERZ_SIXTY, NO_WORDS, NO_TOTALS, True, id="16-sixty-sixty-in-the-only-60-set"),
        pytest.param((SIXTY_SIXTY,), game(GameKind.NULL, NO_TRICKS), NO_WORDS, NO_TOTALS, False, id="null-no-points"),
    ],
)
def test_a_hand_triggers_a_bock_round_when_it_meets_a_trigger_the_table_has_on(
    triggers: tuple[BockTrigger, ...],
    ended: PlayedOut | PassedIn | RamschPlayedOut,
    doubling: Doubling,
    totals: tuple[TotalChange, ...],
    expected: bool,
) -> None:
    assert bock_triggered(frozenset(triggers), ended, doubling, totals) is expected


def test_a_hand_that_meets_two_triggers_starts_one_round() -> None:
    triggers = frozenset({RE_SAID, LOST_AFTER_KONTRA, SCHNEIDER, SCHWARZ})
    triggered = bock_triggered(triggers, SCHWARZ_LOST, said(KONTRA, RE), NO_TOTALS)
    assert factors_over(APPEND, (triggered, False, False, False, False)) == [1, 2, 2, 2, 1]


def factors_over(overlap: BockOverlap, hands: tuple[bool, ...]) -> list[int]:
    """The factor of each hand dealt, where a hand's flag says whether it triggers a round."""
    rounds, factors = BockRounds.start(), []
    for triggered in hands:
        factors.append(bock_factor(rounds, overlap))
        rounds = advance(rounds, overlap, triggered=triggered)
    return factors


@pytest.mark.parametrize(
    ("overlap", "hands", "expected"),
    [
        pytest.param(APPEND, (True, False, False, False, False), [1, 2, 2, 2, 1], id="18-none-pending"),
        pytest.param(
            APPEND,
            (True, False, True, False, False, False, False, False),
            [1, 2, 2, 2, 2, 2, 2, 1],
            id="19-trigger-in-the-second-bock-game",
        ),
        pytest.param(
            APPEND,
            (True, False, False, True, False, False, False, False),
            [1, 2, 2, 2, 2, 2, 2, 1],
            id="20-trigger-in-the-third-bock-game",
        ),
        pytest.param(
            MULTIPLY, (True, False, True, False, False, False, False), [1, 2, 2, 4, 2, 2, 1], id="22-multiply"
        ),
        pytest.param(IGNORE, (True, False, True, False, False), [1, 2, 2, 2, 1], id="23-trigger-in-the-second-game"),
        pytest.param(IGNORE, (True, False, False, True, False), [1, 2, 2, 2, 1], id="23-trigger-in-the-last-game"),
        pytest.param(IGNORE, (True, False, False, False, False), [1, 2, 2, 2, 1], id="24-none-pending"),
        pytest.param(MULTIPLY, (True, False, False, False, False), [1, 2, 2, 2, 1], id="22-multiply-none-pending"),
    ],
)
def test_a_bock_round_is_the_next_three_games_and_a_trigger_inside_one_acts_by_the_overlap_option(
    overlap: BockOverlap, hands: tuple[bool, ...], expected: list[int]
) -> None:
    assert factors_over(overlap, hands) == expected


def test_a_passed_in_hand_uses_up_a_bock_game() -> None:
    options = options_of(SIXTY_SIXTY)
    rounds = advance(
        BockRounds.start(),
        options.overlap,
        triggered=bock_triggered(options.triggers, HERZ_SIXTY, NO_WORDS, NO_TOTALS),
    )
    factors = []
    for _ in range(4):
        factors.append(bock_factor(rounds, options.overlap))
        rounds = advance(
            rounds, options.overlap, triggered=bock_triggered(options.triggers, PassedIn(), NO_WORDS, NO_TOTALS)
        )
    assert factors == [2, 2, 2, 1]


@pytest.mark.parametrize(
    ("ended", "last_word", "reach", "expected_score", "doubled_score", "expected_reckoning"),
    [
        pytest.param(
            game(KREUZ, WIN, trumps=(CLUBS_JACK,)), None, KontraReach.KONTRA_RE, 48, 48, Reckoning(98, 0), id="25"
        ),
        pytest.param(
            game(KREUZ, LOST, trumps=(CLUBS_JACK,)), None, KontraReach.KONTRA_RE, -96, -96, Reckoning(-146, 40), id="26"
        ),
        pytest.param(
            game(KREUZ, WIN, trumps=(CLUBS_JACK,)),
            Word.KONTRA,
            KontraReach.KONTRA_RE,
            48,
            96,
            Reckoning(146, 0),
            id="27",
        ),
        pytest.param(
            game(KREUZ, WIN, trumps=(CLUBS_JACK,)),
            Word.KONTRA,
            KontraReach.KONTRA_RE_STANDINGS,
            48,
            96,
            Reckoning(196, 0),
            id="28",
        ),
        pytest.param(
            game(KREUZ, LOST, trumps=(CLUBS_JACK,)),
            Word.KONTRA,
            KontraReach.KONTRA_RE_STANDINGS,
            -96,
            -192,
            Reckoning(-292, 80),
            id="29",
        ),
    ],
)
def test_a_bock_game_doubles_the_list_score_and_leaves_the_value_and_the_standings_to_kontra(
    ended: PlayedOut,
    last_word: Word | None,
    reach: KontraReach,
    expected_score: int,
    doubled_score: int,
    expected_reckoning: Reckoning,
) -> None:
    rounds = advance(BockRounds.start(), APPEND, triggered=True)
    settlement = bock_settlement(settle(ended, ended.declared.bid), rounds, APPEND)
    assert settlement.value == 24
    assert settlement.score == expected_score
    doubled = Settlement(settlement.won, settlement.value, doubled_score)
    assert doubled_reckoning(doubled, last_word, reach) == expected_reckoning


def test_a_game_outside_every_bock_round_keeps_its_settlement() -> None:
    settlement = settle(HERZ_WON, HERZ_WON.declared.bid)
    assert bock_settlement(settlement, BockRounds.start(), APPEND) == settlement


@pytest.mark.parametrize(
    ("overlap", "rounds", "expected"),
    [
        pytest.param(APPEND, (), 0, id="none-pending"),
        pytest.param(APPEND, (2, 3), 5, id="append-sums-the-rounds"),
        pytest.param(IGNORE, (3,), 3, id="ignore-has-one-round"),
        pytest.param(MULTIPLY, (2, 3), 3, id="multiply-runs-the-rounds-side-by-side"),
        pytest.param(MULTIPLY, (), 0, id="multiply-none-pending"),
    ],
)
def test_the_games_left_are_what_the_pending_rounds_still_deal(
    overlap: BockOverlap, rounds: tuple[int, ...], expected: int
) -> None:
    assert games_left(BockRounds(rounds), overlap) == expected
