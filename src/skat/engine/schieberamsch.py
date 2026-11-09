from dataclasses import dataclass, replace
from enum import StrEnum
from functools import partial
from typing import Final

from skat.engine.bidding import LOWEST_BID, Declared
from skat.engine.cards import Card, Rank
from skat.engine.deal import Deal, Position
from skat.engine.declaration import SKAT_SIZE
from skat.engine.replay import replay_log


class PushingRule(StrEnum):
    """What a take, a push and the cards put back do in a Ramsch."""

    JACKS_STAY = "jacks-stay"
    JACKS_MAY_GO = "jacks-may-go"
    NO_DOUBLING = "no-doubling"

    @property
    def doubles(self) -> bool:
        return self is not PushingRule.NO_DOUBLING

    @property
    def jacks_may_go(self) -> bool:
        return self is PushingRule.JACKS_MAY_GO


class GrandHandRule(StrEnum):
    """Whether a player may leave a Ramsch to play a Grand Hand."""

    ALLOWED = "allowed"
    OFF = "off"


@dataclass(frozen=True)
class PushOptions:
    pushing: PushingRule
    grand_hand: GrandHandRule


class PushRefusal(StrEnum):
    """Why a step changed nothing, in the order the reasons are checked."""

    OVER = "over"
    NOT_YOUR_TURN = "not-your-turn"
    OUT_OF_ORDER = "out-of-order"
    GRAND_HAND_OFF = "grand-hand-off"
    NOT_TWO_OF_THE_TWELVE = "not-two-of-the-twelve"
    JACK_PUT_BACK = "jack-put-back"


@dataclass(frozen=True)
class RamschOn:
    """The stage ended: the Ramsch is played on the cards as they lie."""


@dataclass(frozen=True)
class Pushing:
    """The stage before a Ramsch: whose turn it is, the cards as they lie and the unseen pushes so far."""

    turn: Position
    deal: Deal
    holds_twelve: bool
    pushes: int
    result: RamschOn | Declared | None

    @classmethod
    def start(cls, deal: Deal) -> Pushing:
        return cls(turn=Position.FOREHAND, deal=deal, holds_twelve=False, pushes=0, result=None)


@dataclass(frozen=True)
class PushOutcome:
    """The stage after a step; a refusal leaves it as it was."""

    state: Pushing
    refusal: PushRefusal | None = None


@dataclass(frozen=True)
class Take:
    """The player on turn takes the skat."""

    position: Position


@dataclass(frozen=True)
class Put:
    """The player who took the skat puts two cards back."""

    position: Position
    cards: tuple[Card, ...]


@dataclass(frozen=True)
class Push:
    """The player on turn pushes the skat on unseen."""

    position: Position


@dataclass(frozen=True)
class DeclareGrandHand:
    """The player on turn declares Grand Hand before looking at the skat."""

    position: Position


type PushStep = Take | Put | Push | DeclareGrandHand

_SEATING: Final = tuple(Position)


def push_factor(pushes: int, rule: PushingRule) -> int:
    """What the Ramsch's list score is multiplied by for the unseen pushes."""
    return 2**pushes if rule.doubles else 1


def _order_refusal(state: Pushing, position: Position, *, looked: bool) -> PushRefusal | None:
    if state.result is not None:
        return PushRefusal.OVER
    if position is not state.turn:
        return PushRefusal.NOT_YOUR_TURN
    if state.holds_twelve is not looked:
        return PushRefusal.OUT_OF_ORDER
    return None


def _refuse(state: Pushing, refusal: PushRefusal) -> PushOutcome:
    return PushOutcome(state, refusal)


def _then_next(state: Pushing, *, deal: Deal, pushes: int) -> Pushing:
    if state.turn is _SEATING[-1]:
        return replace(state, deal=deal, holds_twelve=False, pushes=pushes, result=RamschOn())
    following = _SEATING[_SEATING.index(state.turn) + 1]
    return replace(state, turn=following, deal=deal, holds_twelve=False, pushes=pushes)


def take(state: Pushing, position: Position) -> PushOutcome:
    refusal = _order_refusal(state, position, looked=False)
    if refusal is not None:
        return _refuse(state, refusal)
    twelve = state.deal.hands[position] + state.deal.skat
    deal = replace(state.deal, skat=(), **{position.value: twelve})
    return PushOutcome(replace(state, deal=deal, holds_twelve=True))


def put(state: Pushing, position: Position, cards: tuple[Card, ...], rule: PushingRule) -> PushOutcome:
    refusal = _order_refusal(state, position, looked=True)
    if refusal is not None:
        return _refuse(state, refusal)
    hand = state.deal.hands[position]
    if len(cards) != SKAT_SIZE or len(set(cards)) != SKAT_SIZE or not set(cards) <= set(hand):
        return _refuse(state, PushRefusal.NOT_TWO_OF_THE_TWELVE)
    if not rule.jacks_may_go and any(card.rank is Rank.JACK for card in cards):
        return _refuse(state, PushRefusal.JACK_PUT_BACK)
    kept = tuple(card for card in hand if card not in cards)
    deal = replace(state.deal, skat=cards, **{position.value: kept})
    return PushOutcome(_then_next(state, deal=deal, pushes=state.pushes))


def push(state: Pushing, position: Position) -> PushOutcome:
    refusal = _order_refusal(state, position, looked=False)
    if refusal is not None:
        return _refuse(state, refusal)
    return PushOutcome(_then_next(state, deal=state.deal, pushes=state.pushes + 1))


def declare_grand_hand(state: Pushing, position: Position, rule: GrandHandRule) -> PushOutcome:
    refusal = _order_refusal(state, position, looked=False)
    if refusal is not None:
        return _refuse(state, refusal)
    if rule is GrandHandRule.OFF:
        return _refuse(state, PushRefusal.GRAND_HAND_OFF)
    return PushOutcome(replace(state, result=Declared(position, LOWEST_BID), pushes=0))


def pushing_step(state: Pushing, step: PushStep, options: PushOptions) -> PushOutcome:
    match step:
        case Take(position):
            return take(state, position)
        case Put(position, cards):
            return put(state, position, cards, options.pushing)
        case Push(position):
            return push(state, position)
        case _:
            return declare_grand_hand(state, step.position, options.grand_hand)


def pushing_after(start: Pushing, steps: tuple[PushStep, ...], options: PushOptions) -> Pushing:
    return replay_log(start, steps, partial(pushing_step, options=options), "pushing")
