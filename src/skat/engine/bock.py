from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from skat.engine.bidding import PassedIn
from skat.engine.declaration import Declaration
from skat.engine.games import GameKind
from skat.engine.kontra import Doubling, Word
from skat.engine.score import Settlement, settle
from skat.engine.tricks import PlayedOut
from skat.engine.value import value_of

_GAMES_IN_A_ROUND: Final = 3
_SIXTY_SIXTY: Final = 60
_HUNDRED: Final = 100


class BockTrigger(StrEnum):
    """What can start a Bock round; a table switches each one on or off."""

    SIXTY_SIXTY = "sixty-sixty"
    WON_GRAND_HAND = "won-grand-hand"
    LOST_AFTER_KONTRA = "lost-after-kontra"
    RE = "re"
    PASSED_IN = "passed-in"
    SCHNEIDER = "schneider"
    SCHWARZ = "schwarz"
    TOTAL_ENDING_IN_00 = "total-ending-in-00"


class BockOverlap(StrEnum):
    """What a trigger does while Bock games are pending."""

    APPEND = "append"
    MULTIPLY = "multiply"
    IGNORE = "ignore"


@dataclass(frozen=True)
class BockOptions:
    triggers: frozenset[BockTrigger]
    overlap: BockOverlap


@dataclass(frozen=True)
class TotalChange:
    """One seat's total before and after a hand."""

    before: int
    after: int

    @property
    def now_ends_in_00(self) -> bool:
        return self.after != self.before and self.after != 0 and self.after % _HUNDRED == 0


def _triggers_met_by_play(played: PlayedOut, doubling: Doubling) -> frozenset[BockTrigger]:
    declaration = played.declared.declaration
    assert declaration is not None  # noqa: S101 - narrows the type; a played-out game is declared
    bid = played.declared.bid
    valuation = value_of(played, bid)
    won = settle(played, bid).won
    conditions = {
        BockTrigger.SIXTY_SIXTY: played.declarer_points == _SIXTY_SIXTY,
        BockTrigger.WON_GRAND_HAND: _is_grand_hand(declaration) and won,
        BockTrigger.LOST_AFTER_KONTRA: Word.KONTRA in doubling.words and not won,
        BockTrigger.RE: Word.RE in doubling.words,
        BockTrigger.SCHNEIDER: valuation.schneider,
        BockTrigger.SCHWARZ: valuation.schwarz,
    }
    return frozenset(trigger for trigger, met in conditions.items() if met)


def _is_grand_hand(declaration: Declaration) -> bool:
    return declaration.kind is GameKind.GRAND and declaration.hand


def bock_triggered(
    triggers: frozenset[BockTrigger],
    ended: PlayedOut | PassedIn,
    doubling: Doubling,
    totals: tuple[TotalChange, ...],
) -> bool:
    """Whether the hand meets a trigger the table has on; meeting several still starts one round."""
    met = frozenset({BockTrigger.PASSED_IN}) if isinstance(ended, PassedIn) else _triggers_met_by_play(ended, doubling)
    if any(change.now_ends_in_00 for change in totals):
        met |= {BockTrigger.TOTAL_ENDING_IN_00}
    return not triggers.isdisjoint(met)


@dataclass(frozen=True)
class BockRounds:
    """The games each pending Bock round still has, the round that began first at the front."""

    remaining: tuple[int, ...]

    @classmethod
    def start(cls) -> BockRounds:
        return cls(remaining=())


def advance(rounds: BockRounds, overlap: BockOverlap, *, triggered: bool) -> BockRounds:
    """After a hand, played or passed in: it uses up one game of the pending rounds, then a trigger acts by the option."""
    if overlap is BockOverlap.MULTIPLY:
        used = tuple(left - 1 for left in rounds.remaining)
    else:
        used = tuple(left - 1 if index == 0 else left for index, left in enumerate(rounds.remaining))
    left_over = tuple(left for left in used if left > 0)
    ignored = overlap is BockOverlap.IGNORE and bool(rounds.remaining)
    if triggered and not ignored:
        left_over = (*left_over, _GAMES_IN_A_ROUND)
    return BockRounds(remaining=left_over)


def bock_factor(rounds: BockRounds, overlap: BockOverlap) -> int:
    """2 while a Bock game runs; with the multiply option 2 to the number of pending rounds."""
    counted = len(rounds.remaining) if overlap is BockOverlap.MULTIPLY else min(len(rounds.remaining), 1)
    return 2**counted


def bock_settlement(settlement: Settlement, rounds: BockRounds, overlap: BockOverlap) -> Settlement:
    """Only the list score is multiplied; the game value stays, and so do the 50 and the 40 of the reckoning."""
    return Settlement(settlement.won, settlement.value, settlement.score * bock_factor(rounds, overlap))
