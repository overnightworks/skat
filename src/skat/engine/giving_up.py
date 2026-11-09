from dataclasses import replace
from typing import TYPE_CHECKING

from skat.engine.score import settle
from skat.engine.tricks import Ending, PlayedOut, Playing, PlayOutcome, PlayRefusal

if TYPE_CHECKING:
    from skat.engine.deal import Position

_CARDS_HELD_AT_THE_SECOND_TRICK_START = 9


def _ended(state: Playing, ending: Ending) -> PlayedOut:
    return PlayedOut(state.declared, state.tricks, ending)


def give_up(state: Playing, *, consented: bool = False) -> PlayOutcome:
    """The declarer gives up his game: freely while he holds nine or ten cards, later only when an opponent agreed.

    A game his tricks and the skat already win cannot be given up, with or without consent.
    """
    if state.result is not None:
        return PlayOutcome(state, PlayRefusal.OVER)
    if settle(_ended(state, Ending.DECLARER_THREW_DOWN), state.declared.bid).won:
        return PlayOutcome(state, PlayRefusal.ALREADY_WON)
    if not consented and len(state.hands[state.declared.declarer]) < _CARDS_HELD_AT_THE_SECOND_TRICK_START:
        return PlayOutcome(state, PlayRefusal.NEEDS_CONSENT)
    return PlayOutcome(replace(state, result=_ended(state, Ending.GIVEN_UP)))


def throw_down(state: Playing, position: Position) -> PlayOutcome:
    """A side throws its cards down: the game ends, and what no completed trick holds counts for the other side."""
    if state.result is not None:
        return PlayOutcome(state, PlayRefusal.OVER)
    ending = Ending.DECLARER_THREW_DOWN if position is state.declared.declarer else Ending.OPPONENTS_THREW_DOWN
    return PlayOutcome(replace(state, result=_ended(state, ending)))


def opponent_gives_up(state: Playing) -> PlayOutcome:
    """An opponent gives up his side's defence: the game ends at once and no consent is asked.

    A game already won for the declarer ends with his real result, one already lost for him with the opponents' points
    so far, and an undecided one is won by its declaration and bid.
    """
    if state.result is not None:
        return PlayOutcome(state, PlayRefusal.OVER)
    bid = state.declared.bid
    if settle(_ended(state, Ending.DECLARER_THREW_DOWN), bid).won:
        return PlayOutcome(replace(state, result=_ended(state, Ending.OPPONENT_GAVE_UP)))
    if not settle(_ended(state, Ending.OPPONENTS_THREW_DOWN), bid).won:
        return PlayOutcome(replace(state, result=_ended(state, Ending.DECIDED)))
    return PlayOutcome(replace(state, result=_ended(state, Ending.CONCEDED)))
