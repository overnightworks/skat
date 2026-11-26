from enum import StrEnum
from typing import Final

from skat.engine.bidding import Awaiting
from skat.engine.cards import Rank, Suit
from skat.engine.deal import Position
from skat.engine.declaration import Stage


class SuitToken(StrEnum):
    KREUZ = "kreuz"
    PIK = "pik"
    HERZ = "herz"
    KARO = "karo"


class RankToken(StrEnum):
    SEVEN = "seven"
    EIGHT = "eight"
    NINE = "nine"
    TEN = "ten"
    JACK = "jack"
    QUEEN = "queen"
    KING = "king"
    ACE = "ace"


class PositionToken(StrEnum):
    FOREHAND = "forehand"
    MIDDLEHAND = "middlehand"
    REARHAND = "rearhand"


class AwaitingToken(StrEnum):
    BID = "bid"
    ANSWER = "answer"
    PLAY = "play"


class StageToken(StrEnum):
    CHOOSING = "choosing"
    DISCARDING = "discarding"
    PICKED = "picked"
    DECLARED = "declared"


# The engine orders cards by number; the wire names them by word, so that order is no public contract.
SUIT_TOKENS: Final = {
    Suit.KREUZ: SuitToken.KREUZ,
    Suit.PIK: SuitToken.PIK,
    Suit.HERZ: SuitToken.HERZ,
    Suit.KARO: SuitToken.KARO,
}
RANK_TOKENS: Final = {
    Rank.SEVEN: RankToken.SEVEN,
    Rank.EIGHT: RankToken.EIGHT,
    Rank.NINE: RankToken.NINE,
    Rank.TEN: RankToken.TEN,
    Rank.JACK: RankToken.JACK,
    Rank.QUEEN: RankToken.QUEEN,
    Rank.KING: RankToken.KING,
    Rank.ACE: RankToken.ACE,
}
POSITION_TOKENS: Final = {
    Position.FOREHAND: PositionToken.FOREHAND,
    Position.MIDDLEHAND: PositionToken.MIDDLEHAND,
    Position.REARHAND: PositionToken.REARHAND,
}
AWAITING_TOKENS: Final = {
    Awaiting.BID: AwaitingToken.BID,
    Awaiting.ANSWER: AwaitingToken.ANSWER,
    Awaiting.PLAY: AwaitingToken.PLAY,
}
STAGE_TOKENS: Final = {
    Stage.CHOOSING: StageToken.CHOOSING,
    Stage.DISCARDING: StageToken.DISCARDING,
    Stage.PICKED: StageToken.PICKED,
    Stage.DECLARED: StageToken.DECLARED,
}
