from dataclasses import dataclass, replace
from enum import Enum, StrEnum
from typing import Final

from skat.engine.deal import Position
from skat.engine.games import NULL_VALUES, GameKind

LOWEST_BID: Final = 18
_FIRST_FAELLE: Final = 2


def _game_values() -> set[int]:
    values = set(NULL_VALUES.values())
    for kind in GameKind:
        if kind.base_value is not None and kind.highest_faelle is not None:
            values.update(kind.base_value * faelle for faelle in range(_FIRST_FAELLE, kind.highest_faelle + 1))
    return values


VALID_BIDS: Final = tuple(sorted(value for value in _game_values() if value >= LOWEST_BID))


class BidRefusal(StrEnum):
    """Why a bidding action changed nothing, in the order the reasons are checked."""

    OVER = "over"
    ALREADY_PASSED = "already-passed"
    NOT_YOUR_TURN = "not-your-turn"
    WRONG_ACTION = "wrong-action"
    INVALID_VALUE = "invalid-value"
    NOT_ABOVE_STANDING = "not-above-standing"


class _Awaiting(Enum):
    BID = "bid"
    ANSWER = "answer"
    PLAY = "play"


@dataclass(frozen=True)
class Declared:
    declarer: Position
    value: int


@dataclass(frozen=True)
class PassedIn:
    """The hand is passed in and has no declarer."""


@dataclass(frozen=True)
class Auction:
    """The auction as two pairs: the bidder bids, the responder holds or passes."""

    bidder: Position
    responder: Position
    awaiting: _Awaiting
    standing: int | None
    passed: frozenset[Position]
    second_pair: bool
    result: Declared | PassedIn | None

    @classmethod
    def start(cls) -> Auction:
        return cls(
            bidder=Position.MIDDLEHAND,
            responder=Position.FOREHAND,
            awaiting=_Awaiting.BID,
            standing=None,
            passed=frozenset(),
            second_pair=False,
            result=None,
        )

    @property
    def actor(self) -> Position:
        if self.awaiting is _Awaiting.PLAY:
            return Position.FOREHAND
        return self.bidder if self.awaiting is _Awaiting.BID else self.responder


@dataclass(frozen=True)
class BidOutcome:
    """The auction after an action; a refusal leaves it as it was."""

    auction: Auction
    refusal: BidRefusal | None = None


def _refuse(auction: Auction, reason: BidRefusal) -> BidOutcome:
    return BidOutcome(auction, reason)


def _check_turn(auction: Auction, position: Position, awaiting: set[_Awaiting]) -> BidRefusal | None:
    if auction.result is not None:
        return BidRefusal.OVER
    if position in auction.passed:
        return BidRefusal.ALREADY_PASSED
    if position is not auction.actor:
        return BidRefusal.NOT_YOUR_TURN
    if auction.awaiting not in awaiting:
        return BidRefusal.WRONG_ACTION
    return None


def bid(auction: Auction, position: Position, value: int) -> BidOutcome:
    refusal = _check_turn(auction, position, {_Awaiting.BID})
    if refusal is None and value not in VALID_BIDS:
        refusal = BidRefusal.INVALID_VALUE
    if refusal is None and auction.standing is not None and value <= auction.standing:
        refusal = BidRefusal.NOT_ABOVE_STANDING
    if refusal is not None:
        return _refuse(auction, refusal)
    return BidOutcome(replace(auction, awaiting=_Awaiting.ANSWER, standing=value))


def hold(auction: Auction, position: Position) -> BidOutcome:
    refusal = _check_turn(auction, position, {_Awaiting.ANSWER})
    if refusal is not None:
        return _refuse(auction, refusal)
    return BidOutcome(replace(auction, awaiting=_Awaiting.BID))


def pass_(auction: Auction, position: Position) -> BidOutcome:
    refusal = _check_turn(auction, position, set(_Awaiting))
    if refusal is not None:
        return _refuse(auction, refusal)
    passed = auction.passed | {position}
    auction = replace(auction, passed=passed)
    if auction.awaiting is _Awaiting.PLAY:
        return BidOutcome(replace(auction, result=PassedIn()))
    survivor = auction.responder if position is auction.bidder else auction.bidder
    if not auction.second_pair:
        return BidOutcome(
            replace(auction, bidder=Position.REARHAND, responder=survivor, awaiting=_Awaiting.BID, second_pair=True)
        )
    if auction.standing is None:
        return BidOutcome(replace(auction, awaiting=_Awaiting.PLAY))
    return BidOutcome(replace(auction, result=Declared(survivor, auction.standing)))


def play(auction: Auction, position: Position) -> BidOutcome:
    refusal = _check_turn(auction, position, {_Awaiting.PLAY})
    if refusal is not None:
        return _refuse(auction, refusal)
    return BidOutcome(replace(auction, result=Declared(position, LOWEST_BID)))
