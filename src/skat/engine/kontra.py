from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.engine.bidding import AuctionStep, Bid, Hold
from skat.engine.deal import Position
from skat.engine.replay import replay_log
from skat.engine.score import Reckoning, Settlement, list_bonus, reckon
from skat.engine.tricks import playing_after

if TYPE_CHECKING:
    from skat.engine.tricks import CardPlayed, Playing


class KontraSayer(StrEnum):
    """Who may say Kontra."""

    ANY_OPPONENT = "any-opponent"
    BIDDERS_ONLY = "bidders-only"


class KontraReach(StrEnum):
    """How far the words go and what they double."""

    KONTRA_RE = "kontra-re"
    KONTRA_RE_STANDINGS = "kontra-re-standings"
    UP_TO_HIRSCH = "up-to-hirsch"

    @property
    def words_allowed(self) -> int:
        return 4 if self is KontraReach.UP_TO_HIRSCH else 2


class KontraDeadline(StrEnum):
    """Until when the words may be said."""

    OWN_CARD = "own-card"
    FIRST_CARD = "first-card"


@dataclass(frozen=True)
class KontraOptions:
    sayer: KontraSayer
    reach: KontraReach
    deadline: KontraDeadline


class Word(StrEnum):
    """The words in the order they are said; each doubles the score once more."""

    KONTRA = "kontra"
    RE = "re"
    SUPRA = "supra"
    HIRSCH = "hirsch"

    @property
    def factor(self) -> int:
        return 2 ** (_SAYING_ORDER.index(self) + 1)


_SAYING_ORDER: Final = tuple(Word)


class KontraRefusal(StrEnum):
    """Why a word changed nothing, in the order the reasons are checked."""

    OVER = "over"
    BEYOND_REACH = "beyond-reach"
    NOT_YOUR_WORD = "not-your-word"
    DID_NOT_BID = "did-not-bid"
    TOO_LATE = "too-late"
    WORDS_DUE = "words-due"


@dataclass(frozen=True)
class Doubling:
    """The words said so far, who said Kontra and who declined, and the cards the next speaker had played then."""

    words: tuple[Word, ...]
    kontra_by: Position | None
    next_speaker_cards: int
    declined: frozenset[Position] = frozenset()

    @classmethod
    def start(cls) -> Doubling:
        return cls(words=(), kontra_by=None, next_speaker_cards=0)

    @property
    def last_word(self) -> Word | None:
        return self.words[-1] if self.words else None

    @property
    def factor(self) -> int:
        return 1 if self.last_word is None else self.last_word.factor

    @property
    def next_word(self) -> Word | None:
        return _SAYING_ORDER[len(self.words)] if len(self.words) < len(_SAYING_ORDER) else None


@dataclass(frozen=True)
class DoublingOutcome:
    """The doubling after a word; a refusal leaves it as it was."""

    doubling: Doubling
    refusal: KontraRefusal | None = None

    @property
    def state(self) -> Doubling:
        """The doubling under the name a replay of steps reads."""
        return self.doubling


def bidders_of(steps: tuple[AuctionStep, ...]) -> frozenset[Position]:
    """The positions that bid or held at least once."""
    return frozenset(step.position for step in steps if isinstance(step, Bid | Hold))


def _cards_played(playing: Playing, position: Position) -> int:
    in_current_trick = any(played.position is position for played in playing.current_plays)
    return len(playing.tricks) + in_current_trick


def _any_card_played(playing: Playing) -> bool:
    return bool(playing.tricks or playing.current_plays)


def _too_late(doubling: Doubling, options: KontraOptions, playing: Playing, position: Position) -> bool:
    if options.deadline is KontraDeadline.FIRST_CARD:
        return _any_card_played(playing)
    return _cards_played(playing, position) > doubling.next_speaker_cards


def _is_his_word(doubling: Doubling, declarer: Position, position: Position, word: Word) -> bool:
    if word is not doubling.next_word or position in doubling.declined:
        return False
    if word is Word.KONTRA:
        return position is not declarer
    if word is Word.SUPRA:
        return position is doubling.kontra_by
    return position is declarer


def _refusal(
    doubling: Doubling,
    options: KontraOptions,
    playing: Playing,
    bidders: frozenset[Position],
    position: Position,
    word: Word,
) -> KontraRefusal | None:
    if playing.result is not None:
        return KontraRefusal.OVER
    if _SAYING_ORDER.index(word) >= options.reach.words_allowed:
        return KontraRefusal.BEYOND_REACH
    if not _is_his_word(doubling, playing.declared.declarer, position, word):
        return KontraRefusal.NOT_YOUR_WORD
    if word is Word.KONTRA and options.sayer is KontraSayer.BIDDERS_ONLY and position not in bidders:
        return KontraRefusal.DID_NOT_BID
    if _too_late(doubling, options, playing, position):
        return KontraRefusal.TOO_LATE
    return None


def _answerer(doubling: Doubling, options: KontraOptions, declarer: Position) -> Position | None:
    """Who may still answer the word standing, within the reach; none before a Kontra."""
    standing = doubling.next_word
    if not doubling.words or standing is None or _SAYING_ORDER.index(standing) >= options.reach.words_allowed:
        return None
    return doubling.kontra_by if standing is Word.SUPRA else declarer


def _undecided_opponents(doubling: Doubling, declarer: Position) -> frozenset[Position]:
    """The opponents who have neither said Kontra nor declined."""
    return frozenset(
        position
        for position in Position
        if position not in {declarer, doubling.kontra_by} and position not in doubling.declined
    )


def _decline_refusal(
    doubling: Doubling,
    options: KontraOptions,
    playing: Playing,
    bidders: frozenset[Position],
    position: Position,
) -> KontraRefusal | None:
    declarer = playing.declared.declarer
    if playing.result is not None:
        return KontraRefusal.OVER
    answers = position is _answerer(doubling, options, declarer) and position not in doubling.declined
    is_undecided_opponent = position in _undecided_opponents(doubling, declarer)
    if options.deadline is not KontraDeadline.FIRST_CARD or not (answers or is_undecided_opponent):
        return KontraRefusal.NOT_YOUR_WORD
    if is_undecided_opponent and options.sayer is KontraSayer.BIDDERS_ONLY and position not in bidders:
        return KontraRefusal.DID_NOT_BID
    if _any_card_played(playing):
        return KontraRefusal.TOO_LATE
    return None


def decline(
    doubling: Doubling,
    options: KontraOptions,
    playing: Playing,
    bidders: frozenset[Position],
    position: Position,
) -> DoublingOutcome:
    """A word given up before the first card; only a table that plays the words until then accepts it."""
    refusal = _decline_refusal(doubling, options, playing, bidders, position)
    if refusal is not None:
        return DoublingOutcome(doubling, refusal)
    return DoublingOutcome(replace(doubling, declined=doubling.declined | {position}))


def awaits_words(doubling: Doubling, options: KontraOptions, bidders: frozenset[Position], declarer: Position) -> bool:
    """Whether the first lead must still wait for a word or a decline."""
    if options.deadline is not KontraDeadline.FIRST_CARD:
        return False
    answerer = _answerer(doubling, options, declarer)
    if answerer is not None and answerer not in doubling.declined:
        return True
    return any(
        options.sayer is KontraSayer.ANY_OPPONENT or position in bidders
        for position in _undecided_opponents(doubling, declarer)
    )


def say(
    doubling: Doubling,
    options: KontraOptions,
    playing: Playing,
    bidders: frozenset[Position],
    position: Position,
    word: Word,
) -> DoublingOutcome:
    """A word is said until its speaker plays his next card; play never waits for it."""
    refusal = _refusal(doubling, options, playing, bidders, position, word)
    if refusal is not None:
        return DoublingOutcome(doubling, refusal)
    kontra_by = position if word is Word.KONTRA else doubling.kontra_by
    next_speaker = kontra_by if word is Word.RE else playing.declared.declarer
    assert next_speaker is not None  # noqa: S101 - narrows the type; Re follows a Kontra
    return DoublingOutcome(
        replace(
            doubling,
            words=(*doubling.words, word),
            kontra_by=kontra_by,
            next_speaker_cards=_cards_played(playing, next_speaker),
        )
    )


@dataclass(frozen=True)
class WordSaid:
    """A word as stored: who said it and how many cards of the hand were played before it."""

    position: Position
    word: Word
    cards_before: int


def doubling_after(
    start: Playing,
    plays: tuple[CardPlayed, ...],
    words: tuple[WordSaid, ...],
    options: KontraOptions,
    bidders: frozenset[Position],
) -> Doubling:
    """The doubling a stored hand's words lead to, each said against the plays it followed; a word the rules refuse
    is a corrupt log and raises.
    """

    def apply(doubling: Doubling, said: WordSaid) -> DoublingOutcome:
        playing = playing_after(start, plays[: said.cards_before])
        return say(doubling, options, playing, bidders, said.position, said.word)

    return replay_log(Doubling.start(), words, apply, "words")


def doubled_settlement(settlement: Settlement, doubling: Doubling) -> Settlement:
    """The settlement with its list score times the factor; the value stays, as the overbid check reads it."""
    return Settlement(settlement.won, settlement.value, settlement.score * doubling.factor)


def doubled_reckoning(settlement: Settlement, last_word: Word | None, reach: KontraReach) -> Reckoning:
    """What a game with a doubled list score adds up to; only with the standings option do the 50 and the 40 double
    too, by the factor of the last word.
    """
    plain = reckon(settlement)
    if reach is not KontraReach.KONTRA_RE_STANDINGS or last_word is None:
        return plain
    return Reckoning(
        settlement.score + list_bonus(settlement.won) * last_word.factor, plain.each_opponent * last_word.factor
    )
