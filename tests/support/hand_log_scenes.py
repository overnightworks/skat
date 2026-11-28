"""The scenes of a hand that both stores of a hand must hold alike, each built on a dealt table, and the next steps a
command can take from each.

A scene's record raises its base's version and carries traces: the version's, and one on every other act, so every
scene holds traced acts and an untraced one.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum, auto

from skat.engine.bidding import Bid, Hold, Pass
from skat.engine.cards import Rank
from skat.engine.deal import Position
from skat.engine.declaration import Announcement, Declare, PutBack, TakeSkat
from skat.engine.games import GameKind
from skat.engine.kontra import Word, WordSaid
from skat.engine.schieberamsch import DeclareGrandHand, GrandHandRule, Push, Put, Take
from skat.table.acts import acts_of
from skat.table.hand_state import pushing_of
from skat.table.member_view import traces_after, traces_of_acts
from skat.table.records import GiveUpAsked, HandProgress, Series, TableOptions, TableRecord
from skat.table.views import view_of
from tests.support.open_chairs import ALL_PASS, PUSHING
from tests.support.played_game import a_whole_game, after_a_game, an_entry, declared_herz_hand, table_in

MIDDLEHAND, REARHAND, FOREHAND = Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND
VERSION_TRACE = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
STEP_TRACE = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
NEXT_TRACE = "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"
GRAND_HAND = replace(PUSHING, ramsch=replace(PUSHING.ramsch, grand_hand=GrandHandRule.ALLOWED))
WON_AT_18 = (Bid(MIDDLEHAND, 18), Pass(FOREHAND), Pass(REARHAND))

type Build = Callable[[TableRecord], TableRecord]


class LogAfter(Enum):
    """What a next step does to the hand's log: extend it, empty it as a hand's end forgets its steps, or start it
    anew with a deal.
    """

    EXTENDS = auto()
    EMPTIES = auto()
    STARTS_OVER = auto()


@dataclass(frozen=True)
class NextStep:
    name: str
    build: Build
    log_after: LogAfter = LogAfter.EXTENDS


@dataclass(frozen=True)
class HandScene:
    name: str
    build: Build
    next_steps: tuple[NextStep, ...]
    options: TableOptions = TableOptions()  # noqa: RUF009 - TableOptions is frozen
    dealt: bool = True


def _in(table: TableRecord, **changed: object) -> TableRecord:
    return replace(table, progress=replace(table.progress, **changed))


def _steps(table: TableRecord, phase: str, *steps: object) -> TableRecord:
    return _in(table, **{phase: (*getattr(table.progress, phase), *steps)})


def _declared(table: TableRecord, **changed: object) -> TableRecord:
    return replace(table, progress=replace(declared_herz_hand(), **changed))


def _cards(table: TableRecord, count: int) -> TableRecord:
    """The table holding the first `count` cards of a whole game played from its declaration."""
    return _in(table, plays=a_whole_game(_in(table, plays=()))[:count])


def _next_card(table: TableRecord) -> TableRecord:
    return _cards(table, len(table.progress.plays) + 1)


def _played_out(table: TableRecord) -> TableRecord:
    return after_a_game(table, an_entry())


def _aborted(table: TableRecord) -> TableRecord:
    return replace(table, hand=None, progress=HandProgress(aborted=True))


def _non_jacks_of_forehand(table: TableRecord) -> tuple:
    stage = pushing_of(table)
    assert stage is not None
    return tuple(card for card in stage.deal.hands[FOREHAND] if card.rank is not Rank.JACK)[:2]


def _skat_put_back(table: TableRecord) -> PutBack:
    """The declarer puts the skat he took back as it lay."""
    assert table.hand is not None
    return PutBack(table.hand.skat)


def _put(table: TableRecord) -> TableRecord:
    return _steps(table, "pushing", Put(FOREHAND, _non_jacks_of_forehand(table)))


def _with_cards_and_words(table: TableRecord) -> TableRecord:
    return _in(
        _cards(_declared(table), 2), words=(WordSaid(FOREHAND, Word.KONTRA, 0), WordSaid(MIDDLEHAND, Word.RE, 2))
    )


def _the_deal(table: TableRecord) -> TableRecord:
    """The table dealt the in-memory table's deal by its dealer, with no step."""
    dealt = a_dealt_table()
    return replace(table, dealer=dealt.dealer, hand=dealt.hand, progress=HandProgress())


_A_CARD = NextStep("a card", _next_card)
_PLAYED_OUT = NextStep("the end of the game", _played_out, LogAfter.EMPTIES)
_NEXT_DEAL = NextStep("the next deal", _the_deal, LogAfter.STARTS_OVER)


def _auction_scenes() -> tuple[HandScene, ...]:
    return (
        HandScene(
            "a table with no deal",
            lambda table: replace(table, dealer=None, hand=None),
            (NextStep("the deal", _the_deal),),
            dealt=False,
        ),
        HandScene(
            "dealt with no step",
            lambda table: table,
            (
                NextStep("a bid", lambda table: _steps(table, "auction", Bid(MIDDLEHAND, 18))),
                NextStep("a pass", lambda table: _steps(table, "auction", Pass(MIDDLEHAND))),
            ),
        ),
        HandScene(
            "mid-auction",
            lambda table: _in(table, auction=(Bid(MIDDLEHAND, 18),)),
            (
                NextStep("a hold", lambda table: _steps(table, "auction", Hold(FOREHAND))),
                NextStep("a pass", lambda table: _steps(table, "auction", Pass(FOREHAND))),
            ),
        ),
        HandScene(
            "passed in, between hands",
            lambda table: replace(table, hand=None, progress=HandProgress(auction=ALL_PASS)),
            (_NEXT_DEAL,),
        ),
    )


def _stage_and_declaring_scenes() -> tuple[HandScene, ...]:
    grand = Declare(GameKind.GRAND, hand=False, ouvert=False, announcement=Announcement.NONE)
    return (
        HandScene(
            "the Ramsch stage after a take",
            lambda table: _in(table, auction=ALL_PASS, pushing=(Take(FOREHAND),)),
            (NextStep("a put", _put),),
            options=PUSHING,
        ),
        HandScene(
            "the Ramsch stage after a put",
            lambda table: _put(_in(table, auction=ALL_PASS, pushing=(Take(FOREHAND),))),
            (
                NextStep("a push", lambda table: _steps(table, "pushing", Push(MIDDLEHAND))),
                NextStep("a Grand Hand", lambda table: _steps(table, "pushing", DeclareGrandHand(MIDDLEHAND))),
            ),
            options=GRAND_HAND,
        ),
        HandScene(
            "the Ramsch stage after a push",
            lambda table: _steps(
                _put(_in(table, auction=ALL_PASS, pushing=(Take(FOREHAND),))), "pushing", Push(MIDDLEHAND)
            ),
            (NextStep("a push", lambda table: _steps(table, "pushing", Push(REARHAND))),),
            options=PUSHING,
        ),
        HandScene(
            "the Ramsch stage after a Grand Hand",
            lambda table: _in(table, auction=ALL_PASS, pushing=(DeclareGrandHand(FOREHAND),)),
            (),
            options=GRAND_HAND,
        ),
        HandScene(
            "declaring after the take",
            lambda table: _in(table, auction=WON_AT_18, declaring=(TakeSkat(),)),
            (NextStep("a put-back", lambda table: _steps(table, "declaring", _skat_put_back(table))),),
        ),
        HandScene(
            "declaring after the put-back",
            lambda table: _in(table, auction=WON_AT_18, declaring=(TakeSkat(), _skat_put_back(table))),
            (NextStep("a declaration", lambda table: _steps(table, "declaring", grand)),),
        ),
        HandScene(
            "a Hand declaration",
            _declared,
            (_A_CARD, NextStep("a word", lambda table: _steps(table, "words", WordSaid(FOREHAND, Word.KONTRA, 0)))),
        ),
    )


def _playing_scenes() -> tuple[HandScene, ...]:
    return (
        HandScene(
            "cards with words, a word after the last card",
            _with_cards_and_words,
            (_A_CARD, NextStep("a word", lambda table: _steps(table, "words", WordSaid(FOREHAND, Word.SUPRA, 2)))),
        ),
        HandScene("before the last card", lambda table: _cards(_declared(table), 29), (_PLAYED_OUT,)),
        HandScene(
            "a standing give-up",
            lambda table: _declared(table, give_up=GiveUpAsked(MIDDLEHAND)),
            (
                NextStep("a no", lambda table: _in(table, give_up=GiveUpAsked(MIDDLEHAND, declined_by=FOREHAND))),
                _PLAYED_OUT,
            ),
        ),
        HandScene(
            "a half-agreed shortening",
            lambda table: _declared(
                table, give_up=GiveUpAsked(MIDDLEHAND, claim=Announcement.NONE, agreed_by=FOREHAND)
            ),
            (
                NextStep("a refusal", lambda table: _in(table, give_up=None, shortening_refused_by=REARHAND)),
                _PLAYED_OUT,
            ),
        ),
    )


def _standing_scenes() -> tuple[HandScene, ...]:
    return (
        HandScene("a refused shortening", lambda table: _declared(table, shortening_refused_by=FOREHAND), (_A_CARD,)),
        HandScene("open play", lambda table: _declared(table, played_open=frozenset({MIDDLEHAND})), (_A_CARD,)),
        HandScene(
            "abort votes",
            lambda table: _declared(table, abort_yes=frozenset({1})),
            (_A_CARD, NextStep("the abort", _aborted, LogAfter.EMPTIES)),
        ),
        HandScene("aborted, between hands", _aborted, (_NEXT_DEAL,)),
        HandScene("played out, between hands", _played_out, (_NEXT_DEAL,)),
    )


def scenes() -> tuple[HandScene, ...]:
    """The scenes of the matrix but the ended table, which no hand log holds."""
    return (*_auction_scenes(), *_stage_and_declaring_scenes(), *_playing_scenes(), *_standing_scenes())


def traced(table: TableRecord) -> TableRecord:
    """The table with the version's trace and every other act's, the first act's among them."""
    acts = acts_of(table, view_of(table, "", frozenset()))
    by_number = {act.seq: STEP_TRACE for index, act in enumerate(acts) if index % 2 == 0}
    return replace(table, traces=traces_of_acts(table, VERSION_TRACE, by_number))


def scene_on(scene: HandScene, base: TableRecord) -> TableRecord:
    """The scene built on `base`, one version above it, with its traces."""
    return traced(replace(scene.build(base), version=base.version + 1))


def stepped(before: TableRecord, step: NextStep) -> TableRecord:
    """The table after the next step, one version above, its traces carried over as a command's commit does."""
    after = replace(step.build(before), version=before.version + 1)
    return replace(after, traces=traces_after(before, after, NEXT_TRACE))


def a_dealt_table(options: TableOptions = TableOptions()) -> TableRecord:  # noqa: B008 - TableOptions is frozen
    """A dealt table in memory, at the first game of a series of 12."""
    return replace(table_in(HandProgress(), options), series=Series(12, 1))
