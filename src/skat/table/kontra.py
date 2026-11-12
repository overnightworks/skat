from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.engine.deal import seats_from
from skat.engine.kontra import KontraRefusal, WordSaid, bidders_of, say
from skat.table.hand_state import doubling_of, playing_of
from skat.table.records import Decision, NoWordSaid, Refusal
from skat.table.rules import acting_position

if TYPE_CHECKING:
    from skat.engine.deal import Position
    from skat.engine.kontra import Doubling, KontraOptions, Word
    from skat.engine.tricks import Playing
    from skat.table.records import Actor, TableRecord

KONTRA_COMMAND: Final = "kontra"
NO_WORD_PAYLOAD: Final = "no-word"


@dataclass(frozen=True)
class KontraCommand:
    """A word said, or `None` for the answer that the actor says no word now; the actor's position comes from the
    session, never from the client.
    """

    command_id: str
    table_id: str
    version: int
    word: Word | None


@dataclass(frozen=True)
class SeatedWord:
    """A word said and the seat that said it."""

    seat: int
    word: Word


@dataclass(frozen=True)
class KontraView:
    """The words of the running hand as one viewer sees them: every word said in order, the factor they make, and
    the word the viewer's own chair may say now and whether it has answered that word with no word.
    """

    said: tuple[SeatedWord, ...]
    factor: int
    my_word: Word | None
    my_word_answered: bool


def kontra_payload(command: KontraCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    word = NO_WORD_PAYLOAD if command.word is None else command.word.value
    return f"{command.table_id}:{command.version}:{word}"


def _word_open_to(
    doubling: Doubling, options: KontraOptions, state: Playing, bidders: frozenset[Position], position: Position
) -> Word | KontraRefusal:
    """The word the position may say now, or why it may say none: the one question that an answer of no word and the
    viewer's own word both put to the engine. No word is next beyond the last.
    """
    next_word = doubling.next_word
    if next_word is None:
        return KontraRefusal.BEYOND_REACH
    refusal = say(doubling, options, state, bidders, position, next_word).refusal
    return next_word if refusal is None else refusal


def decide_kontra(table: TableRecord, actor: Actor, command: KontraCommand) -> Decision:
    """One word, or the answer of no word: no hand, no chair, a stale version, a table without Kontra, the wrong
    phase, then the engine.
    """
    position = acting_position(table, actor, command.version)
    if isinstance(position, Refusal):
        return Decision(table, position)
    options = table.options.kontra
    if options is None:
        return Decision(table, Refusal.RULE_OFF)
    state, doubling = playing_of(table), doubling_of(table)
    if state is None or doubling is None:
        return Decision(table, Refusal.WRONG_PHASE)
    bidders = bidders_of(table.progress.auction)
    if command.word is None:
        return _answered_no_word(table, position, _word_open_to(doubling, options, state, bidders, position))
    outcome = say(doubling, options, state, bidders, position, command.word)
    if outcome.refusal is not None:
        return Decision(table, outcome.refusal)
    said = WordSaid(position, command.word, len(table.progress.plays))
    words = (*table.progress.words, said)
    return Decision(replace(table, version=table.version + 1, progress=replace(table.progress, words=words)))


def _answered_no_word(table: TableRecord, position: Position, word: Word | KontraRefusal) -> Decision:
    """The seat's answer of no word to the word it may say now, refused as that word would be.

    The answer is kept beside the words and the word stays open, so the seat may still say it until its deadline and
    the engine never sees the answer. A second answer of the same seat for the same word changes nothing.
    """
    if isinstance(word, KontraRefusal):
        return Decision(table, word)
    answered = NoWordSaid(position, word)
    if answered in table.progress.no_words:
        return Decision(table)
    no_words = table.progress.no_words | {answered}
    return Decision(replace(table, version=table.version + 1, progress=replace(table.progress, no_words=no_words)))


def kontra_view_of(
    table: TableRecord, state: Playing, dealer: int, viewer_positions: frozenset[Position]
) -> KontraView | None:
    """The words for one viewer; None at a table without Kontra.

    The viewer's own chair gets the word it may say now: the next word, if the engine accepts it from that position.
    A watcher has no chair, so no word; the caller passes no viewer position while the hand waits for a sitter.
    """
    options, doubling = table.options.kontra, doubling_of(table)
    if options is None or doubling is None:
        return None
    bidders = bidders_of(table.progress.auction)
    open_words = {position: _word_open_to(doubling, options, state, bidders, position) for position in viewer_positions}
    mine = {position: word for position, word in open_words.items() if not isinstance(word, KontraRefusal)}
    seats = seats_from(dealer)
    return KontraView(
        said=tuple(SeatedWord(seats[each.position], each.word) for each in table.progress.words),
        factor=doubling.factor,
        my_word=doubling.next_word if mine else None,
        my_word_answered=bool(mine)
        and all(NoWordSaid(position, word) in table.progress.no_words for position, word in mine.items()),
    )
