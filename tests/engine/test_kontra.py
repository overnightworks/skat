from itertools import cycle

import pytest

from skat.engine.bidding import AuctionStep, Bid, Declared, Hold, Pass, Play
from skat.engine.cards import DECK
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declaring, declare, put_back, take_skat
from skat.engine.games import GameKind
from skat.engine.giving_up import give_up, throw_down
from skat.engine.kontra import (
    Doubling,
    KontraOptions,
    KontraReach,
    KontraRefusal,
    KontraSayer,
    Word,
    bidders_of,
    doubled_reckoning,
    say,
)
from skat.engine.score import Reckoning, Settlement, reckon
from skat.engine.tricks import Playing, play_card, start_play

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
KONTRA, RE, SUPRA, HIRSCH = Word.KONTRA, Word.RE, Word.SUPRA, Word.HIRSCH
ANY, BIDDERS = KontraSayer.ANY_OPPONENT, KontraSayer.BIDDERS_ONLY
KONTRA_RE, WITH_STANDINGS, UP_TO_HIRSCH = (
    KontraReach.KONTRA_RE,
    KontraReach.KONTRA_RE_STANDINGS,
    KontraReach.UP_TO_HIRSCH,
)
OVER, BEYOND_REACH, NOT_YOUR_WORD, DID_NOT_BID, TOO_LATE = (
    KontraRefusal.OVER,
    KontraRefusal.BEYOND_REACH,
    KontraRefusal.NOT_YOUR_WORD,
    KontraRefusal.DID_NOT_BID,
    KontraRefusal.TOO_LATE,
)
CARD = "a card is played by whoever is on turn"
TENTH_TRICK = "the game is played to its tenth trick"
GIVE_UP = "the declarer gives up"
THROW_DOWN = "forehand throws down"

# Middlehand bids 18 and 20, forehand holds 18 and passes at 20, rearhand passes at once.
MIDDLEHAND_DECLARES = (Bid(MIDDLEHAND, 18), Hold(FOREHAND), Bid(MIDDLEHAND, 20), Pass(FOREHAND), Pass(REARHAND))
FOREHAND_PLAYS = (Pass(MIDDLEHAND), Pass(REARHAND), Play(FOREHAND))
REARHAND_BID_IN_THE_SECOND_PAIR = (
    Bid(MIDDLEHAND, 18),
    Pass(FOREHAND),
    Bid(REARHAND, 22),
    Hold(MIDDLEHAND),
    Pass(REARHAND),
)


def playing_with(declarer: Position) -> Playing:
    deal = Deal(DECK[:10], DECK[10:20], DECK[20:30], DECK[30:])
    state = Declaring.start(Declared(declarer, 18), deal)
    state = put_back(take_skat(state).state, deal.skat).state
    outcome = declare(state, GameKind.KARO, hand=False, ouvert=False, announcement=Announcement.NONE)
    assert outcome.refusal is None
    return start_play(outcome.state, deal)


def next_card(state: Playing) -> Playing:
    position = state.turn
    return next(
        outcome.state for card in state.hands[position] if (outcome := play_card(state, position, card)).refusal is None
    )


def advanced(state: Playing, event: str) -> Playing:
    if event == CARD:
        return next_card(state)
    if event == TENTH_TRICK:
        while state.result is None:
            state = next_card(state)
        return state
    outcome = give_up(state) if event == GIVE_UP else throw_down(state, FOREHAND)
    assert outcome.refusal is None
    return outcome.state


def said_in(
    options: KontraOptions, steps: tuple[AuctionStep, ...], declarer: Position, events: tuple[object, ...]
) -> tuple[Doubling, KontraRefusal | None]:
    """The doubling and the refusal after the events; every say but the last must be accepted."""
    state, doubling, refusal = playing_with(declarer), Doubling.start(), None
    for event in events:
        assert refusal is None
        if isinstance(event, str):
            state = advanced(state, event)
            continue
        position, word = event
        outcome = say(doubling, options, state, bidders_of(steps), position, word)
        doubling, refusal = outcome.doubling, outcome.refusal
    return doubling, refusal


def options_of(sayer: KontraSayer, reach: KontraReach) -> KontraOptions:
    return KontraOptions(sayer=sayer, reach=reach)


@pytest.mark.parametrize(
    ("sayer", "reach", "steps", "declarer", "events", "expected"),
    [
        pytest.param(ANY, KONTRA_RE, MIDDLEHAND_DECLARES, MIDDLEHAND, ((REARHAND, KONTRA),), 2, id="1-any-opponent"),
        pytest.param(
            BIDDERS, KONTRA_RE, MIDDLEHAND_DECLARES, MIDDLEHAND, ((REARHAND, KONTRA),), DID_NOT_BID, id="2-no-bid"
        ),
        pytest.param(BIDDERS, KONTRA_RE, MIDDLEHAND_DECLARES, MIDDLEHAND, ((FOREHAND, KONTRA),), 2, id="3-held-once"),
        pytest.param(
            BIDDERS,
            KONTRA_RE,
            REARHAND_BID_IN_THE_SECOND_PAIR,
            MIDDLEHAND,
            ((REARHAND, KONTRA),),
            2,
            id="4-bid-in-the-second-pair",
        ),
        pytest.param(
            BIDDERS, KONTRA_RE, FOREHAND_PLAYS, FOREHAND, ((MIDDLEHAND, KONTRA),), DID_NOT_BID, id="5-middlehand"
        ),
        pytest.param(BIDDERS, KONTRA_RE, FOREHAND_PLAYS, FOREHAND, ((REARHAND, KONTRA),), DID_NOT_BID, id="5-rearhand"),
        pytest.param(ANY, KONTRA_RE, FOREHAND_PLAYS, FOREHAND, ((MIDDLEHAND, KONTRA),), 2, id="5-any-middlehand"),
        pytest.param(ANY, KONTRA_RE, FOREHAND_PLAYS, FOREHAND, ((REARHAND, KONTRA),), 2, id="5-any-rearhand"),
        pytest.param(
            ANY, KONTRA_RE, MIDDLEHAND_DECLARES, MIDDLEHAND, ((MIDDLEHAND, KONTRA),), NOT_YOUR_WORD, id="6-declarer"
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            (CARD, (FOREHAND, KONTRA)),
            TOO_LATE,
            id="7-after-his-lead",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            (CARD, CARD, (REARHAND, KONTRA)),
            2,
            id="8-before-his-own-card",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (MIDDLEHAND, RE)),
            4,
            id="9-re-before-his-next-card",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), CARD, (MIDDLEHAND, RE)),
            4,
            id="9-re-before-his-card-while-an-opponent-led",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), CARD, CARD, (MIDDLEHAND, RE)),
            TOO_LATE,
            id="10-after-his-card",
        ),
        pytest.param(
            ANY, KONTRA_RE, MIDDLEHAND_DECLARES, MIDDLEHAND, ((MIDDLEHAND, RE),), NOT_YOUR_WORD, id="11-re-first"
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (FOREHAND, RE)),
            NOT_YOUR_WORD,
            id="11-re-by-an-opponent",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (REARHAND, KONTRA)),
            NOT_YOUR_WORD,
            id="11-second-kontra",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (MIDDLEHAND, RE), (FOREHAND, SUPRA)),
            BEYOND_REACH,
            id="12-kontra-re",
        ),
        pytest.param(
            ANY,
            WITH_STANDINGS,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (MIDDLEHAND, RE), (FOREHAND, SUPRA)),
            BEYOND_REACH,
            id="12-with-standings",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (MIDDLEHAND, RE), (FOREHAND, SUPRA)),
            8,
            id="13-supra",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (MIDDLEHAND, RE), (FOREHAND, SUPRA), (MIDDLEHAND, HIRSCH)),
            16,
            id="13-hirsch",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (MIDDLEHAND, RE), (REARHAND, SUPRA)),
            NOT_YOUR_WORD,
            id="14-other-opponent",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (MIDDLEHAND, RE), (FOREHAND, SUPRA), CARD, CARD, (MIDDLEHAND, HIRSCH)),
            TOO_LATE,
            id="supra-and-hirsch-follow-the-same-deadline",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (MIDDLEHAND, RE), CARD, (FOREHAND, SUPRA)),
            TOO_LATE,
            id="supra-after-the-kontra-opponent-played-a-card",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, KONTRA), (MIDDLEHAND, RE), (FOREHAND, SUPRA), (MIDDLEHAND, HIRSCH), (FOREHAND, KONTRA)),
            NOT_YOUR_WORD,
            id="no-word-after-hirsch",
        ),
        pytest.param(
            ANY, UP_TO_HIRSCH, MIDDLEHAND_DECLARES, MIDDLEHAND, ((FOREHAND, HIRSCH),), NOT_YOUR_WORD, id="hirsch-first"
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            ((FOREHAND, SUPRA),),
            BEYOND_REACH,
            id="supra-first-beyond-reach",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            (TENTH_TRICK, (FOREHAND, KONTRA)),
            OVER,
            id="15-tenth-trick",
        ),
        pytest.param(
            ANY, UP_TO_HIRSCH, MIDDLEHAND_DECLARES, MIDDLEHAND, (GIVE_UP, (FOREHAND, KONTRA)), OVER, id="15-given-up"
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            MIDDLEHAND_DECLARES,
            MIDDLEHAND,
            (THROW_DOWN, (FOREHAND, KONTRA)),
            OVER,
            id="15-thrown-down",
        ),
        pytest.param(ANY, UP_TO_HIRSCH, MIDDLEHAND_DECLARES, MIDDLEHAND, (), 1, id="25-no-word"),
    ],
)
def test_a_word_is_accepted_or_refused_as_the_table_rules_say(
    sayer: KontraSayer,
    reach: KontraReach,
    steps: tuple[AuctionStep, ...],
    declarer: Position,
    events: tuple[object, ...],
    expected: KontraRefusal | int,
) -> None:
    doubling, refusal = said_in(options_of(sayer, reach), steps, declarer, events)
    if isinstance(expected, KontraRefusal):
        assert refusal is expected
    else:
        assert refusal is None
        assert doubling.factor == expected


def test_a_refused_word_leaves_the_doubling_as_it_was() -> None:
    options = options_of(ANY, KONTRA_RE)
    outcome = say(Doubling.start(), options, playing_with(MIDDLEHAND), frozenset(), MIDDLEHAND, KONTRA)
    assert outcome.refusal is NOT_YOUR_WORD
    assert outcome.doubling == Doubling.start()


def test_the_bidders_are_the_positions_that_bid_or_held() -> None:
    assert bidders_of(MIDDLEHAND_DECLARES) == {MIDDLEHAND, FOREHAND}
    assert bidders_of(FOREHAND_PLAYS) == frozenset()


WON, LOST = Settlement(won=True, value=24, score=24), Settlement(won=False, value=24, score=-48)
OVERBID_AND_LOST = Settlement(won=False, value=36, score=-72)  # Kreuz mit 1 settled at 36 under a bid of 30
NULL_WON = Settlement(won=True, value=23, score=23)
ALL_WORDS = (KONTRA, RE, SUPRA, HIRSCH)


def doubling_of(words: tuple[Word, ...]) -> Doubling:
    state, doubling = playing_with(MIDDLEHAND), Doubling.start()
    sayers = cycle((FOREHAND, MIDDLEHAND))
    for word in words:
        outcome = say(doubling, options_of(ANY, UP_TO_HIRSCH), state, frozenset(), next(sayers), word)
        assert outcome.refusal is None
        doubling = outcome.doubling
    return doubling


@pytest.mark.parametrize(
    ("reach", "settlement", "words", "expected"),
    [
        pytest.param(KONTRA_RE, WON, (KONTRA,), Reckoning(98, 0), id="16"),
        pytest.param(KONTRA_RE, LOST, (KONTRA,), Reckoning(-146, 40), id="17"),
        pytest.param(KONTRA_RE, WON, (KONTRA, RE), Reckoning(146, 0), id="18"),
        pytest.param(KONTRA_RE, OVERBID_AND_LOST, (KONTRA,), Reckoning(-194, 40), id="19"),
        pytest.param(WITH_STANDINGS, WON, (KONTRA,), Reckoning(148, 0), id="20-won"),
        pytest.param(WITH_STANDINGS, LOST, (KONTRA,), Reckoning(-196, 80), id="20-lost"),
        pytest.param(WITH_STANDINGS, LOST, (KONTRA, RE), Reckoning(-392, 160), id="21"),
        pytest.param(UP_TO_HIRSCH, WON, ALL_WORDS, Reckoning(434, 0), id="22"),
        pytest.param(UP_TO_HIRSCH, LOST, (KONTRA, RE, SUPRA), Reckoning(-434, 40), id="23"),
        pytest.param(KONTRA_RE, NULL_WON, (KONTRA,), Reckoning(96, 0), id="24"),
        pytest.param(KONTRA_RE, WON, (), reckon(WON), id="25-list-score-only"),
        pytest.param(WITH_STANDINGS, LOST, (), reckon(LOST), id="25-with-standings"),
        pytest.param(UP_TO_HIRSCH, LOST, (), reckon(LOST), id="25-up-to-hirsch"),
    ],
)
def test_the_doubling_multiplies_what_the_table_option_says(
    reach: KontraReach, settlement: Settlement, words: tuple[Word, ...], expected: Reckoning
) -> None:
    assert doubled_reckoning(settlement, doubling_of(words), reach) == expected
