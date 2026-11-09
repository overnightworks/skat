from dataclasses import replace
from typing import TYPE_CHECKING

from skat.engine.declaration import Announcement
from skat.engine.score import settle
from skat.engine.tricks import Ending, PlayedOut, Playing, PlayOutcome, PlayRefusal
from skat.engine.value import announcement_reached

if TYPE_CHECKING:
    from skat.engine.deal import Position

_CARDS_HELD_AT_THE_SECOND_TRICK_START = 9


def _ended(state: Playing, ending: Ending) -> PlayedOut:
    return PlayedOut(state.declared, state.tricks, ending)


def _already_won(state: Playing) -> bool:
    return settle(_ended(state, Ending.DECLARER_THREW_DOWN), state.declared.bid).won


def _already_lost(state: Playing) -> bool:
    return not settle(_ended(state, Ending.OPPONENTS_THREW_DOWN), state.declared.bid).won


def give_up(state: Playing, *, consented: bool = False) -> PlayOutcome:
    """The declarer gives up his game: freely while he holds nine or ten cards, later only when an opponent agreed.

    A game his tricks and the skat already win cannot be given up, with or without consent.
    """
    if state.result is not None:
        return PlayOutcome(state, PlayRefusal.OVER)
    if _already_won(state):
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
    if _already_won(state):
        return PlayOutcome(replace(state, result=_ended(state, Ending.DECIDED_WON)))
    if _already_lost(state):
        return PlayOutcome(replace(state, result=_ended(state, Ending.DECIDED)))
    return PlayOutcome(replace(state, result=_ended(state, Ending.CONCEDED)))


def shorten(state: Playing, *, all_agreed: bool = False, claim: Announcement = Announcement.NONE) -> PlayOutcome:
    """The declarer shortens the game by showing his cards; it ends only when every opponent agreed.

    A level he demands that the opponents already put out of reach is refused before anyone is asked. A game already
    lost for him stays lost, one already won keeps its real result unless he demands a level, and an undecided one is
    won by its declaration and the demanded level.
    """
    if state.result is not None:
        return PlayOutcome(state, PlayRefusal.OVER)
    if not announcement_reached(claim, _ended(state, Ending.OPPONENTS_THREW_DOWN)):
        return PlayOutcome(state, PlayRefusal.CLAIM_OUT_OF_REACH)
    if not all_agreed:
        return PlayOutcome(state, PlayRefusal.NEEDS_CONSENT)
    if _already_lost(state):
        return PlayOutcome(replace(state, result=_ended(state, Ending.DECIDED)))
    if claim is Announcement.NONE and _already_won(state):
        return PlayOutcome(replace(state, result=_ended(state, Ending.DECIDED_WON)))
    return PlayOutcome(replace(state, result=PlayedOut(state.declared, state.tricks, Ending.SHORTENED, claim)))
