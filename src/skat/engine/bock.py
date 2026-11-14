from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.engine.bidding import PassedIn
from skat.engine.games import GameKind
from skat.engine.kontra import Doubling, Word
from skat.engine.ramsch import RamschPlayedOut
from skat.engine.score import Settlement, settle
from skat.engine.value import value_of

if TYPE_CHECKING:
    from skat.engine.declaration import Declaration
    from skat.engine.tricks import PlayedOut

GAMES_IN_A_ROUND: Final = 3
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
    ended: PlayedOut | PassedIn | RamschPlayedOut,
    doubling: Doubling,
    totals: tuple[TotalChange, ...],
) -> bool:
    """Whether the hand meets a trigger the table has on; meeting several still starts one round.

    A Ramsch is the hand all three passed, played out: it meets `passed-in`, and no other trigger of a game.
    """
    met = (
        frozenset({BockTrigger.PASSED_IN})
        if isinstance(ended, PassedIn | RamschPlayedOut)
        else _triggers_met_by_play(ended, doubling)
    )
    if any(change.now_ends_in_00 for change in totals):
        met |= {BockTrigger.TOTAL_ENDING_IN_00}
    return not triggers.isdisjoint(met)


@dataclass(frozen=True)
class BockRounds:
    """The games each pending Bock round still has, the round that began first at the front, and the Ramsch-round games
    still to come after the Bock games, three for each Bock round that ended.
    """

    remaining: tuple[int, ...]
    ramsch_games: int = 0

    @classmethod
    def start(cls) -> BockRounds:
        return cls(remaining=())


def in_ramsch_round(rounds: BockRounds, overlap: BockOverlap) -> bool:
    """Whether the next game, or the running one, is a Ramsch-round game: no Bock game is pending and a Ramsch-round
    game is.
    """
    return games_left(rounds, overlap) == 0 and rounds.ramsch_games > 0


def advance(rounds: BockRounds, overlap: BockOverlap, *, triggered: bool, ramsch_follows: bool) -> BockRounds:
    """After a hand, played or passed in: it uses up a game of the pending rounds, then a trigger acts by the option.

    A Ramsch-round game uses up a Ramsch-round game and no Bock game. With `ramsch_follows` each Bock round the hand
    ends adds a Ramsch round of three games.
    """
    if overlap is BockOverlap.MULTIPLY:
        used = tuple(left - 1 for left in rounds.remaining)
    else:
        used = tuple(left - 1 if index == 0 else left for index, left in enumerate(rounds.remaining))
    left_over = tuple(left for left in used if left > 0)
    ended_rounds = len(used) - len(left_over)
    ramsch_games = rounds.ramsch_games
    if in_ramsch_round(rounds, overlap):
        ramsch_games -= 1
    if ramsch_follows:
        ramsch_games += ended_rounds * GAMES_IN_A_ROUND
    ignored = overlap is BockOverlap.IGNORE and bool(rounds.remaining)
    if triggered and not ignored:
        left_over = (*left_over, GAMES_IN_A_ROUND)
    return BockRounds(remaining=left_over, ramsch_games=ramsch_games)


def bock_factor(rounds: BockRounds, overlap: BockOverlap) -> int:
    """2 while a Bock game runs; with the multiply option 2 to the number of pending rounds."""
    counted = len(rounds.remaining) if overlap is BockOverlap.MULTIPLY else min(len(rounds.remaining), 1)
    return 2**counted


def games_left(rounds: BockRounds, overlap: BockOverlap) -> int:
    """The Bock games still to come: the pending rounds one after another, or with multiply side by side."""
    if overlap is BockOverlap.MULTIPLY:
        return max(rounds.remaining, default=0)
    return sum(rounds.remaining)


def bock_settlement(settlement: Settlement, rounds: BockRounds, overlap: BockOverlap) -> Settlement:
    """Only the list score is multiplied; the game value stays, and so do the 50 and the 40 of the reckoning."""
    return Settlement(settlement.won, settlement.value, settlement.score * bock_factor(rounds, overlap))
