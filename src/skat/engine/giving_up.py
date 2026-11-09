from dataclasses import replace

from skat.engine.tricks import Ending, PlayedOut, Playing, PlayOutcome, PlayRefusal

_CARDS_HELD_AT_THE_SECOND_TRICK_START = 9


def give_up(state: Playing) -> PlayOutcome:
    """The declarer gives up his game while he still holds nine or ten cards; nobody else is asked."""
    if state.result is not None:
        return PlayOutcome(state, PlayRefusal.OVER)
    if len(state.hands[state.declared.declarer]) < _CARDS_HELD_AT_THE_SECOND_TRICK_START:
        return PlayOutcome(state, PlayRefusal.TOO_LATE_TO_GIVE_UP)
    return PlayOutcome(replace(state, result=PlayedOut(state.declared, state.tricks, Ending.GIVEN_UP)))
