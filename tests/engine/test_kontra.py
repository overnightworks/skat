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
    KontraDeadline,
    KontraOptions,
    KontraReach,
    KontraRefusal,
    KontraSayer,
    Word,
    WordSaid,
    awaits_words,
    bidders_of,
    decline,
    doubled_reckoning,
    doubled_settlement,
    doubling_after,
    say,
)
from skat.engine.score import Reckoning, Settlement, reckon
from skat.engine.tricks import CardPlayed, Playing, play_card, start_play

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
OWN_CARD, FIRST_CARD = KontraDeadline.OWN_CARD, KontraDeadline.FIRST_CARD
DECLINE = None
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


def options_of(sayer: KontraSayer, reach: KontraReach, deadline: KontraDeadline = OWN_CARD) -> KontraOptions:
    return KontraOptions(sayer=sayer, reach=reach, deadline=deadline)


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


def answered_in(
    options: KontraOptions, steps: tuple[AuctionStep, ...], events: tuple[object, ...]
) -> tuple[Doubling, KontraRefusal | None, bool]:
    """The doubling, the refusal of the last event and whether the lead waits; every event but the last is accepted."""
    state, doubling, refusal = playing_with(MIDDLEHAND), Doubling.start(), None
    bidders = bidders_of(steps)
    for event in events:
        assert refusal is None
        if isinstance(event, str):
            state = advanced(state, event)
            continue
        position, word = event
        if word is DECLINE:
            outcome = decline(doubling, options, state, bidders, position)
        else:
            outcome = say(doubling, options, state, bidders, position, word)
        doubling, refusal = outcome.doubling, outcome.refusal
    return doubling, refusal, awaits_words(doubling, options, bidders, MIDDLEHAND)


@pytest.mark.parametrize(
    ("sayer", "reach", "deadline", "steps", "events", "expected", "waits"),
    [
        pytest.param(ANY, KONTRA_RE, FIRST_CARD, MIDDLEHAND_DECLARES, (), 1, True, id="1-no-word-yet"),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, DECLINE), (REARHAND, DECLINE)),
            1,
            False,
            id="2-both-decline",
        ),
        pytest.param(
            BIDDERS,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, DECLINE),),
            1,
            False,
            id="3-the-one-who-did-not-bid-is-not-awaited",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((REARHAND, DECLINE), (FOREHAND, KONTRA)),
            2,
            True,
            id="4-kontra-after-a-decline-awaits-the-declarer",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, KONTRA), (REARHAND, DECLINE)),
            2,
            True,
            id="4-decline-after-a-kontra-awaits-the-declarer",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, KONTRA), (REARHAND, DECLINE), (MIDDLEHAND, RE)),
            4,
            False,
            id="5-re",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, KONTRA), (REARHAND, DECLINE), (MIDDLEHAND, DECLINE)),
            2,
            False,
            id="6-declarer-declines",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            (CARD, (FOREHAND, KONTRA)),
            TOO_LATE,
            None,
            id="7-kontra-after-a-card",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            (CARD, (FOREHAND, DECLINE)),
            TOO_LATE,
            None,
            id="7-decline-after-a-card",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, KONTRA), CARD, (MIDDLEHAND, RE)),
            TOO_LATE,
            None,
            id="7-re-after-a-card",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, DECLINE), (FOREHAND, DECLINE)),
            NOT_YOUR_WORD,
            None,
            id="8-second-decline",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, DECLINE), (FOREHAND, KONTRA)),
            NOT_YOUR_WORD,
            None,
            id="8-kontra-after-a-decline",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((MIDDLEHAND, DECLINE),),
            NOT_YOUR_WORD,
            None,
            id="8-declarer-without-a-kontra",
        ),
        pytest.param(
            BIDDERS,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((REARHAND, DECLINE),),
            DID_NOT_BID,
            None,
            id="8-decline-by-one-who-did-not-bid",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            (TENTH_TRICK, (FOREHAND, DECLINE)),
            OVER,
            None,
            id="15-decline-after-the-game-is-over",
        ),
        pytest.param(
            ANY,
            KONTRA_RE,
            OWN_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, DECLINE),),
            NOT_YOUR_WORD,
            None,
            id="9-no-decline-before-the-own-card",
        ),
        pytest.param(ANY, KONTRA_RE, OWN_CARD, MIDDLEHAND_DECLARES, (), 1, False, id="9-play-never-waits"),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, KONTRA), (REARHAND, DECLINE), (MIDDLEHAND, RE)),
            4,
            True,
            id="10-supra-is-awaited",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, KONTRA), (REARHAND, DECLINE), (MIDDLEHAND, RE), (FOREHAND, DECLINE)),
            4,
            False,
            id="10-supra-declined",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, KONTRA), (REARHAND, DECLINE), (MIDDLEHAND, RE), (FOREHAND, SUPRA)),
            8,
            True,
            id="10-hirsch-is-awaited",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, KONTRA), (REARHAND, DECLINE), (MIDDLEHAND, RE), (FOREHAND, SUPRA), (MIDDLEHAND, DECLINE)),
            8,
            False,
            id="10-hirsch-declined",
        ),
        pytest.param(
            ANY,
            UP_TO_HIRSCH,
            FIRST_CARD,
            MIDDLEHAND_DECLARES,
            ((FOREHAND, KONTRA), (REARHAND, DECLINE), (MIDDLEHAND, RE), (FOREHAND, SUPRA), (MIDDLEHAND, HIRSCH)),
            16,
            False,
            id="10-hirsch",
        ),
    ],
)
def test_play_waits_for_each_answer_when_the_words_end_with_the_first_card(
    sayer: KontraSayer,
    reach: KontraReach,
    deadline: KontraDeadline,
    steps: tuple[AuctionStep, ...],
    events: tuple[object, ...],
    expected: KontraRefusal | int,
    waits: bool | None,
) -> None:
    doubling, refusal, awaiting = answered_in(options_of(sayer, reach, deadline), steps, events)
    if isinstance(expected, KontraRefusal):
        assert refusal is expected
        return
    assert refusal is None
    assert doubling.factor == expected
    assert awaiting is waits


def test_a_refused_word_leaves_the_doubling_as_it_was() -> None:
    options = options_of(ANY, KONTRA_RE)
    outcome = say(Doubling.start(), options, playing_with(MIDDLEHAND), frozenset(), MIDDLEHAND, KONTRA)
    assert outcome.refusal is NOT_YOUR_WORD
    assert outcome.doubling == Doubling.start()


def test_the_bidders_are_the_positions_that_bid_or_held() -> None:
    assert bidders_of(MIDDLEHAND_DECLARES) == {MIDDLEHAND, FOREHAND}
    assert bidders_of(FOREHAND_PLAYS) == frozenset()


WON, LOST = Settlement(won=True, value=24, score=24), Settlement(won=False, value=24, score=-48)
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


@pytest.mark.parametrize(("word", "factor"), [(KONTRA, 2), (RE, 4), (SUPRA, 8), (HIRSCH, 16)])
def test_each_word_doubles_the_score_once_more_and_the_doubling_takes_the_last_ones_factor(
    word: Word, factor: int
) -> None:
    assert word.factor == factor
    assert doubling_of(ALL_WORDS[: ALL_WORDS.index(word) + 1]).factor == factor


def test_without_a_word_the_factor_is_one_and_there_is_no_last_word() -> None:
    assert Doubling.start().factor == 1
    assert Doubling.start().last_word is None
    assert doubling_of((KONTRA, RE)).last_word is RE


@pytest.mark.parametrize(
    ("settlement", "words", "expected"),
    [
        pytest.param(WON, (), WON, id="no-word"),
        pytest.param(WON, (KONTRA,), Settlement(won=True, value=24, score=48), id="kontra"),
        pytest.param(LOST, (KONTRA, RE), Settlement(won=False, value=24, score=-192), id="re"),
        pytest.param(NULL_WON, ALL_WORDS, Settlement(won=True, value=23, score=368), id="hirsch"),
    ],
)
def test_the_doubled_settlement_multiplies_the_list_score_alone(
    settlement: Settlement, words: tuple[Word, ...], expected: Settlement
) -> None:
    assert doubled_settlement(settlement, doubling_of(words)) == expected


@pytest.mark.parametrize(
    ("reach", "settlement", "last_word", "expected"),
    [
        pytest.param(KONTRA_RE, Settlement(won=True, value=24, score=48), KONTRA, Reckoning(98, 0), id="16"),
        pytest.param(KONTRA_RE, Settlement(won=False, value=24, score=-96), KONTRA, Reckoning(-146, 40), id="17"),
        pytest.param(KONTRA_RE, Settlement(won=True, value=24, score=96), RE, Reckoning(146, 0), id="18"),
        pytest.param(KONTRA_RE, Settlement(won=False, value=36, score=-144), KONTRA, Reckoning(-194, 40), id="19"),
        pytest.param(WITH_STANDINGS, Settlement(won=True, value=24, score=48), KONTRA, Reckoning(148, 0), id="20-won"),
        pytest.param(
            WITH_STANDINGS, Settlement(won=False, value=24, score=-96), KONTRA, Reckoning(-196, 80), id="20-lost"
        ),
        pytest.param(WITH_STANDINGS, Settlement(won=False, value=24, score=-192), RE, Reckoning(-392, 160), id="21"),
        pytest.param(UP_TO_HIRSCH, Settlement(won=True, value=24, score=384), HIRSCH, Reckoning(434, 0), id="22"),
        pytest.param(UP_TO_HIRSCH, Settlement(won=False, value=24, score=-384), SUPRA, Reckoning(-434, 40), id="23"),
        pytest.param(KONTRA_RE, Settlement(won=True, value=23, score=46), KONTRA, Reckoning(96, 0), id="24"),
        pytest.param(KONTRA_RE, WON, None, reckon(WON), id="25-list-score-only"),
        pytest.param(WITH_STANDINGS, LOST, None, reckon(LOST), id="25-with-standings"),
        pytest.param(UP_TO_HIRSCH, LOST, None, reckon(LOST), id="25-up-to-hirsch"),
    ],
)
def test_the_doubling_multiplies_what_the_table_option_says(
    reach: KontraReach, settlement: Settlement, last_word: Word | None, expected: Reckoning
) -> None:
    assert doubled_reckoning(settlement, last_word, reach) == expected


def plays_of(count: int) -> tuple[CardPlayed, ...]:
    """The first cards of the game, each the first legal card of whoever is on turn."""
    state, plays = playing_with(MIDDLEHAND), []
    for _ in range(count):
        position = state.turn
        card = next(card for card in state.hands[position] if play_card(state, position, card).refusal is None)
        plays.append(CardPlayed(position, card))
        state = play_card(state, position, card).state
    return tuple(plays)


@pytest.mark.parametrize(
    ("words", "expected_words", "expected_factor"),
    [
        pytest.param((), (), 1, id="none"),
        pytest.param((WordSaid(FOREHAND, KONTRA, 0),), (KONTRA,), 2, id="kontra"),
        pytest.param(
            (WordSaid(FOREHAND, KONTRA, 0), WordSaid(MIDDLEHAND, RE, 1)), (KONTRA, RE), 4, id="re-after-a-card"
        ),
        pytest.param(
            (
                WordSaid(FOREHAND, KONTRA, 0),
                WordSaid(MIDDLEHAND, RE, 1),
                WordSaid(FOREHAND, SUPRA, 3),
                WordSaid(MIDDLEHAND, HIRSCH, 3),
            ),
            ALL_WORDS,
            16,
            id="up-to-hirsch",
        ),
    ],
)
def test_the_stored_words_rebuild_the_doubling_each_against_the_plays_it_followed(
    words: tuple[WordSaid, ...], expected_words: tuple[Word, ...], expected_factor: int
) -> None:
    doubling = doubling_after(playing_with(MIDDLEHAND), plays_of(4), words, options_of(ANY, UP_TO_HIRSCH), frozenset())
    assert doubling.words == expected_words
    assert doubling.factor == expected_factor


@pytest.mark.parametrize(
    "word",
    [
        pytest.param(WordSaid(MIDDLEHAND, KONTRA, 0), id="the-declarer-says-kontra"),
        pytest.param(WordSaid(FOREHAND, KONTRA, 4), id="after-his-own-card"),
        pytest.param(WordSaid(FOREHAND, SUPRA, 0), id="out-of-order"),
    ],
)
def test_a_stored_word_the_rules_refuse_is_a_corrupt_log(word: WordSaid) -> None:
    state = playing_with(MIDDLEHAND)
    plays = plays_of(4)
    options = options_of(ANY, UP_TO_HIRSCH)
    with pytest.raises(ValueError, match="impossible words log"):
        doubling_after(state, plays, (word,), options, frozenset())
