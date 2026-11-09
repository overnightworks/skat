from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.engine.bidding import AuctionStep, Bid, Hold
from skat.engine.score import Reckoning, Settlement, reckon

if TYPE_CHECKING:
    from skat.engine.deal import Position
    from skat.engine.tricks import Playing


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


@dataclass(frozen=True)
class KontraOptions:
    sayer: KontraSayer
    reach: KontraReach


class Word(StrEnum):
    """The words in the order they are said; each doubles the score once more."""

    KONTRA = "kontra"
    RE = "re"
    SUPRA = "supra"
    HIRSCH = "hirsch"


_SAYING_ORDER: Final = tuple(Word)


class KontraRefusal(StrEnum):
    """Why a word changed nothing, in the order the reasons are checked."""

    OVER = "over"
    BEYOND_REACH = "beyond-reach"
    NOT_YOUR_WORD = "not-your-word"
    DID_NOT_BID = "did-not-bid"
    TOO_LATE = "too-late"


@dataclass(frozen=True)
class Doubling:
    """The words said so far, who said Kontra, and the cards the next speaker had played when the last one fell."""

    words: tuple[Word, ...]
    kontra_by: Position | None
    next_speaker_cards: int

    @classmethod
    def start(cls) -> Doubling:
        return cls(words=(), kontra_by=None, next_speaker_cards=0)

    @property
    def factor(self) -> int:
        return 2 ** len(self.words)

    @property
    def next_word(self) -> Word | None:
        return _SAYING_ORDER[len(self.words)] if len(self.words) < len(_SAYING_ORDER) else None


@dataclass(frozen=True)
class DoublingOutcome:
    """The doubling after a word; a refusal leaves it as it was."""

    doubling: Doubling
    refusal: KontraRefusal | None = None


def bidders_of(steps: tuple[AuctionStep, ...]) -> frozenset[Position]:
    """The positions that bid or held at least once."""
    return frozenset(step.position for step in steps if isinstance(step, Bid | Hold))


def _cards_played(playing: Playing, position: Position) -> int:
    in_current_trick = any(played.position is position for played in playing.current_plays)
    return len(playing.tricks) + in_current_trick


def _is_his_word(doubling: Doubling, declarer: Position, position: Position, word: Word) -> bool:
    if word is not doubling.next_word:
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
    if _cards_played(playing, position) > doubling.next_speaker_cards:
        return KontraRefusal.TOO_LATE
    return None


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


def doubled_reckoning(settlement: Settlement, doubling: Doubling, reach: KontraReach) -> Reckoning:
    """The list score times the factor; only with the standings option do the 50 and the 40 double too."""
    if reach is KontraReach.KONTRA_RE_STANDINGS:
        plain = reckon(settlement)
        return Reckoning(plain.declarer * doubling.factor, plain.each_opponent * doubling.factor)
    doubled = Settlement(settlement.won, settlement.value, settlement.score * doubling.factor)
    return reckon(doubled)
