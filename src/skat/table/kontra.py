from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.engine.deal import seats_from
from skat.engine.kontra import WordSaid, bidders_of, say
from skat.table.hand_state import doubling_of, playing_of
from skat.table.records import Decision, Refusal
from skat.table.rules import acting_position

if TYPE_CHECKING:
    from skat.engine.deal import Position
    from skat.engine.kontra import Word
    from skat.engine.tricks import Playing
    from skat.table.records import Actor, TableRecord

KONTRA_COMMAND: Final = "kontra"


@dataclass(frozen=True)
class KontraCommand:
    """A word said; the actor's position comes from the session, never from the client."""

    command_id: str
    table_id: str
    version: int
    word: Word


@dataclass(frozen=True)
class SeatedWord:
    """A word said and the seat that said it."""

    seat: int
    word: Word


@dataclass(frozen=True)
class KontraView:
    """The words of the running hand as one viewer sees them: every word said in order, the factor they make, and
    the word the viewer's own chair may say now.
    """

    said: tuple[SeatedWord, ...]
    factor: int
    my_word: Word | None


def kontra_payload(command: KontraCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    return f"{command.table_id}:{command.version}:{command.word.value}"


def decide_kontra(table: TableRecord, actor: Actor, command: KontraCommand) -> Decision:
    """One word: no hand, no chair, a stale version, a table without Kontra, the wrong phase, then the engine."""
    position = acting_position(table, actor, command.version)
    if isinstance(position, Refusal):
        return Decision(table, position)
    options = table.options.kontra
    if options is None:
        return Decision(table, Refusal.RULE_OFF)
    state, doubling = playing_of(table), doubling_of(table)
    if state is None or doubling is None:
        return Decision(table, Refusal.WRONG_PHASE)
    outcome = say(doubling, options, state, bidders_of(table.progress.auction), position, command.word)
    if outcome.refusal is not None:
        return Decision(table, outcome.refusal)
    said = WordSaid(position, command.word, len(table.progress.plays))
    words = (*table.progress.words, said)
    return Decision(replace(table, version=table.version + 1, progress=replace(table.progress, words=words)))


def kontra_view_of(table: TableRecord, state: Playing, viewer_positions: frozenset[Position]) -> KontraView | None:
    """The words for one viewer; None at a table without Kontra.

    The viewer's own chair gets the word it may say now: the next word, if the engine accepts it from that position.
    A watcher has no chair, so no word.
    """
    options, doubling = table.options.kontra, doubling_of(table)
    if options is None or doubling is None:
        return None
    bidders = bidders_of(table.progress.auction)
    next_word = doubling.next_word
    may_say = next_word is not None and any(
        say(doubling, options, state, bidders, position, next_word).refusal is None for position in viewer_positions
    )
    seats = seats_from(table.dealer)
    return KontraView(
        said=tuple(SeatedWord(seats[each.position], each.word) for each in table.progress.words),
        factor=doubling.factor,
        my_word=next_word if may_say else None,
    )
