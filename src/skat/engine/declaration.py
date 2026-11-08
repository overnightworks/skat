from dataclasses import dataclass, replace
from enum import Enum, StrEnum
from typing import TYPE_CHECKING

from skat.engine.games import GameKind, NullLevels

if TYPE_CHECKING:
    from skat.engine.bidding import Declared
    from skat.engine.cards import Card
    from skat.engine.deal import Deal, Position

_SKAT_SIZE = 2


class Announcement(Enum):
    NONE = "none"
    SCHNEIDER = "schneider"
    SCHWARZ = "schwarz"


class DeclarationRefusal(StrEnum):
    """Why an action changed nothing, in the order the reasons are checked."""

    ALREADY_DECLARED = "already-declared"
    OUT_OF_ORDER = "out-of-order"
    NOT_TWO_OF_THE_TWELVE = "not-two-of-the-twelve"
    LEVEL_NOT_ALLOWED_AFTER_PICK_UP = "level-not-allowed-after-pick-up"
    ANNOUNCEMENT_IN_NULL = "announcement-in-null"


def _is_suit_or_grand(kind: GameKind) -> bool:
    return kind is not GameKind.NULL


@dataclass(frozen=True)
class Declaration:
    """The declared game; only `declare` builds it from a person's choice."""

    kind: GameKind
    hand: bool
    ouvert: bool
    announcement: Announcement

    def __post_init__(self) -> None:
        suit_or_grand = _is_suit_or_grand(self.kind)
        if self.announcement is not Announcement.NONE and not (suit_or_grand and self.hand):
            message = "impossible declaration: an announcement needs a suit or Grand Hand game"
            raise ValueError(message)
        if suit_or_grand and self.ouvert and not (self.hand and self.announcement is Announcement.SCHWARZ):
            message = "impossible declaration: an ouvert suit or Grand game is a Hand game announced Schwarz"
            raise ValueError(message)

    @property
    def null_levels(self) -> NullLevels | None:
        """E2's key for the Null value; none for any other game."""
        if self.kind is not GameKind.NULL:
            return None
        return NullLevels(hand=self.hand, ouvert=self.ouvert)


class _Stage(Enum):
    CHOOSING = "choosing"
    DISCARDING = "discarding"
    PICKED = "picked"
    DECLARED = "declared"


@dataclass(frozen=True)
class Declaring:
    """The step between the auction and the first lead; once declared it is the ended state."""

    declarer: Position
    bid: int
    hand: tuple[Card, ...]
    skat: tuple[Card, ...]
    stage: _Stage
    declaration: Declaration | None

    @classmethod
    def start(cls, auction_result: Declared, deal: Deal) -> Declaring:
        return cls(
            declarer=auction_result.declarer,
            bid=auction_result.value,
            hand=deal.hands[auction_result.declarer],
            skat=deal.skat,
            stage=_Stage.CHOOSING,
            declaration=None,
        )


@dataclass(frozen=True)
class DeclarationOutcome:
    """The state after an action; a refusal leaves it as it was."""

    state: Declaring
    refusal: DeclarationRefusal | None = None


def _refuse(state: Declaring, reason: DeclarationRefusal) -> DeclarationOutcome:
    return DeclarationOutcome(state, reason)


def take_skat(state: Declaring) -> DeclarationOutcome:
    if state.stage is _Stage.DECLARED:
        return _refuse(state, DeclarationRefusal.ALREADY_DECLARED)
    if state.stage is not _Stage.CHOOSING:
        return _refuse(state, DeclarationRefusal.OUT_OF_ORDER)
    return DeclarationOutcome(replace(state, stage=_Stage.DISCARDING, hand=state.hand + state.skat, skat=()))


def put_back(state: Declaring, cards: tuple[Card, ...]) -> DeclarationOutcome:
    if state.stage is _Stage.DECLARED:
        return _refuse(state, DeclarationRefusal.ALREADY_DECLARED)
    if state.stage is not _Stage.DISCARDING:
        return _refuse(state, DeclarationRefusal.OUT_OF_ORDER)
    if len(cards) != _SKAT_SIZE or len(set(cards)) != _SKAT_SIZE or not set(cards) <= set(state.hand):
        return _refuse(state, DeclarationRefusal.NOT_TWO_OF_THE_TWELVE)
    kept = tuple(card for card in state.hand if card not in cards)
    return DeclarationOutcome(replace(state, stage=_Stage.PICKED, hand=kept, skat=cards))


def _declare_refusal(
    state: Declaring, kind: GameKind, *, hand: bool, ouvert: bool, announcement: Announcement
) -> DeclarationRefusal | None:
    if state.stage is _Stage.DECLARED:
        return DeclarationRefusal.ALREADY_DECLARED
    if state.stage is _Stage.DISCARDING or (state.stage is _Stage.CHOOSING and not hand):
        return DeclarationRefusal.OUT_OF_ORDER
    higher_level = announcement is not Announcement.NONE or (ouvert and _is_suit_or_grand(kind))
    if state.stage is _Stage.PICKED and (hand or higher_level):
        return DeclarationRefusal.LEVEL_NOT_ALLOWED_AFTER_PICK_UP
    if kind is GameKind.NULL and announcement is not Announcement.NONE:
        return DeclarationRefusal.ANNOUNCEMENT_IN_NULL
    return None


def declare(
    state: Declaring, kind: GameKind, *, hand: bool, ouvert: bool, announcement: Announcement
) -> DeclarationOutcome:
    refusal = _declare_refusal(state, kind, hand=hand, ouvert=ouvert, announcement=announcement)
    if refusal is not None:
        return _refuse(state, refusal)
    if ouvert and _is_suit_or_grand(kind):
        announcement = Announcement.SCHWARZ
    declaration = Declaration(kind, hand=hand, ouvert=ouvert, announcement=announcement)
    return DeclarationOutcome(replace(state, stage=_Stage.DECLARED, declaration=declaration))
