"""What happened in a table's hand, as numbered acts: the lines an agent seated there reads beside its view.

Every act is replayed from the hand's stored steps, so a restart changes none of them. The number of an act is its
hand's number times `HAND_SPAN` plus its slot in the hand, so a later hand numbers every act above every act of an
earlier one, in the same series and across series. The hand's number counts the deals of the table's series and
continues across series; a table that keeps no series has no hand number and no act.

The running hand's acts take the slots 1, 2, ... in the order they happened. The acts that end a hand take the last
slots, because the end clears the hand's steps: an act that ended a hand is numbered above every act of the hand
whatever the hand had before it. The acts are only what the table's view shows every seat: a card is named only when it
is played, and a put-back names none. A give-up asked and the answers to it, and the votes to abort a hand, are no
acts: the table keeps them as a standing request, not as steps, and the view shows them.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.engine.bidding import LOWEST_BID, Bid, Hold, Pass, Play
from skat.engine.deal import seats_from
from skat.engine.declaration import Declaration, Declare, PutBack, TakeSkat
from skat.engine.schieberamsch import DeclareGrandHand, Push, Put, Take
from skat.table.game_list import GameEnding, ResultView
from skat.table.hand_state import declaring_of
from skat.table.records import SERIES_LENGTH_MAX
from skat.table.rules import hand_runs

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skat.engine.bidding import AuctionStep
    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.engine.declaration import DeclaringStep
    from skat.engine.kontra import Word, WordSaid
    from skat.engine.tricks import CardPlayed
    from skat.table.game_list import RamschResultView
    from skat.table.records import Series, TableRecord
    from skat.table.views import TableView

HAND_SPAN: Final = 1000
LAST_SLOT: Final = HAND_SPAN - 1


class ActKind(StrEnum):
    """The table's word for a sort of act."""

    DEAL = "deal"
    BID = "bid"
    HOLD = "hold"
    PASS = "pass"  # noqa: S105 - the word for dropping out of the auction and no password
    TAKE_SKAT = "take-skat"
    PUT_BACK = "put-back"
    PUSH = "push"
    DECLARE = "declare"
    PLAY = "play"
    WORD = "word"
    GIVE_UP = "give-up"
    SHORTEN = "shorten"
    PLAY_OPEN = "play-open"
    THROW_DOWN = "throw-down"
    RESULT = "result"
    PASSED_IN = "passed-in"
    ABORTED = "aborted"


type Detail = int | Card | Declaration | Word | ResultView | RamschResultView | None
"""What an act adds to its kind: the dealer's seat of a deal, the value of a bid or a hold, the declaration, the card
played, the word said, the result of a game; nothing for the rest.
"""


@dataclass(frozen=True)
class Act:
    """One numbered act: the seat that took it, None when nobody did, and what it adds to its kind."""

    seq: int
    seat: int | None
    kind: ActKind
    detail: Detail = None


type _Event = tuple[int | None, ActKind, Detail]


def _hand_number(series: Series) -> int:
    return (series.number - 1) * (SERIES_LENGTH_MAX + 1) + series.deals


def next_seq_of(table: TableRecord) -> int:
    """The number the first act of the table's next hand gets while that hand is a deal of the series now running; 1
    for a table that keeps no series.
    """
    return 1 if table.series is None else (_hand_number(table.series) + 1) * HAND_SPAN + 1


def _auction_events(steps: tuple[AuctionStep, ...], seats: dict[Position, int]) -> Iterator[_Event]:
    standing = None
    for step in steps:
        seat = seats[step.position]
        if isinstance(step, Bid):
            standing = step.value
            yield seat, ActKind.BID, step.value
        elif isinstance(step, Hold):
            yield seat, ActKind.HOLD, standing
        elif isinstance(step, Pass):
            yield seat, ActKind.PASS, None
        else:
            assert isinstance(step, Play)  # noqa: S101 - the engine's four auction steps
            yield seat, ActKind.BID, LOWEST_BID


def _declaration_of(table: TableRecord) -> Declaration:
    """The game the table's declarer declared, as the view shows it."""
    declaring = declaring_of(table)
    assert declaring is not None  # noqa: S101 - a stored declaration follows a seat that declares
    assert declaring.declaration is not None  # noqa: S101 - and a declared game has its declaration
    return declaring.declaration


def _pushing_events(table: TableRecord, seats: dict[Position, int]) -> Iterator[_Event]:
    for step in table.progress.pushing:
        seat = seats[step.position]
        if isinstance(step, Take):
            yield seat, ActKind.TAKE_SKAT, None
        elif isinstance(step, Put):
            yield seat, ActKind.PUT_BACK, None
        elif isinstance(step, Push):
            yield seat, ActKind.PUSH, None
        else:
            assert isinstance(step, DeclareGrandHand)  # noqa: S101 - the engine's four pushing steps
            yield seat, ActKind.DECLARE, _declaration_of(table)


def _declaring_events(table: TableRecord, seats: dict[Position, int]) -> Iterator[_Event]:
    steps: tuple[DeclaringStep, ...] = table.progress.declaring
    if not steps:
        return
    declaring = declaring_of(table)
    assert declaring is not None  # noqa: S101 - a stored declaring step follows a seat that declares
    seat = seats[declaring.declarer]
    for step in steps:
        if isinstance(step, TakeSkat):
            yield seat, ActKind.TAKE_SKAT, None
        elif isinstance(step, PutBack):
            yield seat, ActKind.PUT_BACK, None
        else:
            assert isinstance(step, Declare)  # noqa: S101 - the engine's three declaring steps
            yield seat, ActKind.DECLARE, _declaration_of(table)


def _play_events(
    plays: tuple[CardPlayed, ...], words: tuple[WordSaid, ...], seats: dict[Position, int]
) -> Iterator[_Event]:
    """The cards in order with each word before the card it was said ahead of, and the words said after the last."""
    unsaid = list(words)
    for played_before, play in enumerate(plays):
        while unsaid and unsaid[0].cards_before <= played_before:
            said = unsaid.pop(0)
            yield seats[said.position], ActKind.WORD, said.word
        yield seats[play.position], ActKind.PLAY, play.card
    for said in unsaid:
        yield seats[said.position], ActKind.WORD, said.word


def _running_events(table: TableRecord, seats: dict[Position, int], dealer: int) -> Iterator[_Event]:
    progress = table.progress
    yield None, ActKind.DEAL, dealer
    yield from _auction_events(progress.auction, seats)
    yield from _pushing_events(table, seats)
    yield from _declaring_events(table, seats)
    yield from _play_events(progress.plays, progress.words, seats)


_ENDING_KINDS: Final = {
    GameEnding.GIVEN_UP: ActKind.GIVE_UP,
    GameEnding.SHORTENED: ActKind.SHORTEN,
    GameEnding.PLAYED_OPEN: ActKind.PLAY_OPEN,
    GameEnding.THROWN_DOWN: ActKind.THROW_DOWN,
}


def _result_events(result: ResultView | RamschResultView) -> Iterator[_Event]:
    if isinstance(result, ResultView) and result.ending is not GameEnding.PLAYED_OUT:
        yield result.ended_by_seat, _ENDING_KINDS[result.ending], None
    yield None, ActKind.RESULT, result


def _ending_events(view: TableView) -> Iterator[_Event]:
    """The acts that end the hand the view stands after: its pass-in, its abort or its result."""
    if view.passed_in is not None:
        yield None, ActKind.PASSED_IN, None
    elif view.aborted is not None:
        yield None, ActKind.ABORTED, None
    elif view.result is not None:
        yield from _result_events(view.result)


def acts_of(table: TableRecord, view: TableView) -> tuple[Act, ...]:
    """The acts of the table's latest hand, numbered, told by the view of one seat: the running hand's from its deal;
    after its end the acts that end it, with a passed-in hand's steps. The next hand's deal clears them.
    """
    if table.series is None or table.dealer is None:
        return ()
    base = _hand_number(table.series) * HAND_SPAN
    seats = seats_from(table.dealer)
    if hand_runs(table):
        slotted = enumerate(_running_events(table, seats, table.dealer), start=1)
        return tuple(Act(base + slot, *event) for slot, event in slotted)
    steps = _running_events(table, seats, table.dealer) if view.passed_in is not None else iter(())
    passed_in = tuple(Act(base + slot, *event) for slot, event in enumerate(steps, start=1))
    ending = tuple(_ending_events(view))
    last_slots = range(LAST_SLOT - len(ending) + 1, LAST_SLOT + 1)
    return passed_in + tuple(Act(base + slot, *event) for slot, event in zip(last_slots, ending, strict=True))
