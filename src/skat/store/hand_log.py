"""A hand's state as one typed log: `hand_steps` holds the steps of the table's latest hand and `hands` its standing
state.

A step's ordinal is the slot of its act, so the steps follow the acts' order: the deal first, then the auction, the
pushing stage and the declaring, then the cards with each word in the order it was said. A word therefore carries no
count of the cards before it: the card rows before it are that count. A table that has dealt has one `hands` row,
written for the version in its `stamp_version`; a release that moves the table without writing the row leaves that
stamp behind the table's version.
"""

from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Table,
    Text,
    delete,
    false,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as upsert

from skat.engine.bidding import Bid, Hold, Pass, Play
from skat.engine.cards import Card
from skat.engine.declaration import Declare, PutBack, TakeSkat
from skat.engine.kontra import Word, WordSaid
from skat.engine.schieberamsch import DeclareGrandHand, Push, Put, Take
from skat.engine.tricks import CardPlayed
from skat.store.schema import (
    ANNOUNCEMENT_OF_TEXT,
    ANNOUNCEMENT_TEXT,
    GAME_OF_TEXT,
    GAME_TEXT,
    POSITION_OF_TEXT,
    POSITION_TEXT,
    RANK_OF_TEXT,
    RANK_TEXT,
    SUIT_OF_TEXT,
    SUIT_TEXT,
    metadata,
    one_of,
    standing_checks,
    tables,
    unstored_steps,
)
from skat.table.acts import said_in_order
from skat.table.auction import AuctionAction, action_of, step_of
from skat.table.records import EntryTraces, GiveUpAsked, HandProgress

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy import Row
    from sqlalchemy.engine import Connection

    from skat.engine.bidding import AuctionStep
    from skat.engine.deal import Position
    from skat.engine.declaration import DeclaringStep
    from skat.table.records import PushingStep, TableRecord


class StepKind(StrEnum):
    """The store's word for a sort of step; the stage's steps are told apart from the declarer's take and put-back."""

    DEAL = "deal"
    BID = "bid"
    HOLD = "hold"
    PASS = "pass"  # noqa: S105 - the word for dropping out of the auction and no password
    PLAY = "play"
    TAKE_SKAT = "take-skat"
    PUT_BACK = "put-back"
    DECLARE = "declare"
    STAGE_TAKE = "stage-take"
    STAGE_PUT = "stage-put"
    STAGE_PUSH = "stage-push"
    STAGE_GRAND_HAND = "stage-grand-hand"
    CARD = "card"
    WORD = "word"


_KIND_OF_ACTION: Final = {
    AuctionAction.BID: StepKind.BID,
    AuctionAction.HOLD: StepKind.HOLD,
    AuctionAction.PASS: StepKind.PASS,
    AuctionAction.PLAY: StepKind.PLAY,
}
_ACTION_OF_KIND: Final = {kind: action for action, kind in _KIND_OF_ACTION.items()}
_STAGE_KINDS: Final = {
    Take: StepKind.STAGE_TAKE,
    Push: StepKind.STAGE_PUSH,
    DeclareGrandHand: StepKind.STAGE_GRAND_HAND,
}
_STAGE_STEPS: Final = {kind: step for step, kind in _STAGE_KINDS.items()}

hand_steps = Table(
    "hand_steps",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id, ondelete="CASCADE"), primary_key=True),
    Column("ordinal", SmallInteger, primary_key=True),
    Column("kind", Text, nullable=False),
    Column("position", Text),
    Column("value", SmallInteger),
    Column("suit", Text),
    Column("rank", Text),
    Column("second_suit", Text),
    Column("second_rank", Text),
    Column("game", Text),
    Column("hand", Boolean),
    Column("ouvert", Boolean),
    Column("announcement", Text),
    Column("word", Text),
    Column("traceparent", Text),
    one_of("kind", (kind.value for kind in StepKind), "hand_steps_kind_is_a_kind"),
    one_of("position", POSITION_TEXT.values(), "hand_steps_position_is_a_position"),
    one_of("suit", SUIT_TEXT.values(), "hand_steps_suit_is_a_suit"),
    one_of("rank", RANK_TEXT.values(), "hand_steps_rank_is_a_rank"),
    one_of("second_suit", SUIT_TEXT.values(), "hand_steps_second_suit_is_a_suit"),
    one_of("second_rank", RANK_TEXT.values(), "hand_steps_second_rank_is_a_rank"),
    one_of("game", GAME_TEXT.values(), "hand_steps_game_is_a_game"),
    one_of("announcement", ANNOUNCEMENT_TEXT.values(), "hand_steps_announcement_is_an_announcement"),
    one_of("word", (word.value for word in Word), "hand_steps_word_is_a_word"),
    Index(
        "hand_steps_each_card_once",
        "table_id",
        "suit",
        "rank",
        unique=True,
        postgresql_where=text(f"kind = '{StepKind.CARD.value}'"),
    ),
)

# The standing state of the table's current or last hand: replaced at each deal, it lives until the next deal or the
# table's end. `end_traceparent` is the trace of the request that ended the hand.
hands = Table(
    "hands",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id, ondelete="CASCADE"), primary_key=True),
    Column("give_up_asked_by", Text),
    Column("give_up_declined_by", Text),
    Column("give_up_claim", Text),
    Column("give_up_agreed_by", Text),
    Column("give_up_open", Boolean, nullable=False, server_default=false()),
    Column("shortening_refused_by", Text),
    Column("played_open", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("abort_yes_seats", ARRAY(SmallInteger), nullable=False, server_default=text("'{}'")),
    Column("aborted", Boolean, nullable=False, server_default=false()),
    Column("end_traceparent", Text),
    Column("stamp_version", Integer, nullable=False),
    *standing_checks("hands", "aborted"),
)


@dataclass(frozen=True)
class StepRow:
    """One step as `hand_steps` stores it, without its table and ordinal."""

    kind: StepKind
    position: str | None = None
    value: int | None = None
    suit: str | None = None
    rank: str | None = None
    second_suit: str | None = None
    second_rank: str | None = None
    game: str | None = None
    hand: bool | None = None
    ouvert: bool | None = None
    announcement: str | None = None
    word: str | None = None
    traceparent: str | None = None


type _Step = AuctionStep | PushingStep | DeclaringStep | CardPlayed | WordSaid


def _position(position: Position) -> str:
    return POSITION_TEXT[position]


def _with_two_cards(row: StepRow, cards: tuple[Card, ...]) -> StepRow:
    first, second = cards
    return replace(
        row,
        suit=SUIT_TEXT[first.suit],
        rank=RANK_TEXT[first.rank],
        second_suit=SUIT_TEXT[second.suit],
        second_rank=RANK_TEXT[second.rank],
    )


def _row_of(step: _Step) -> StepRow:
    match step:
        case Bid() | Hold() | Pass() | Play():
            value = step.value if isinstance(step, Bid) else None
            return StepRow(_KIND_OF_ACTION[action_of(step)], _position(step.position), value)
        case TakeSkat():
            return StepRow(StepKind.TAKE_SKAT)
        case PutBack():
            return _with_two_cards(StepRow(StepKind.PUT_BACK), step.cards)
        case Declare():
            game, announcement = GAME_TEXT[step.kind], ANNOUNCEMENT_TEXT[step.announcement]
            return StepRow(StepKind.DECLARE, game=game, hand=step.hand, ouvert=step.ouvert, announcement=announcement)
        case Put():
            return _with_two_cards(StepRow(StepKind.STAGE_PUT, _position(step.position)), step.cards)
        case Take() | Push() | DeclareGrandHand():
            return StepRow(_STAGE_KINDS[type(step)], _position(step.position))
        case CardPlayed():
            return StepRow(
                StepKind.CARD, _position(step.position), suit=SUIT_TEXT[step.card.suit], rank=RANK_TEXT[step.card.rank]
            )
        case _:  # a spoken word, the last of the steps
            return StepRow(StepKind.WORD, _position(step.position), word=step.word.value)


def encoded(table: TableRecord) -> tuple[StepRow, ...]:
    """The log of the table's latest hand, each step with its trace: empty once the hand ended and forgot its steps,
    and from the deal on while the hand runs or its auction passed it in.
    """
    progress = table.progress
    steps = (
        *progress.auction,
        *progress.pushing,
        *progress.declaring,
        *said_in_order(progress.plays, progress.words),
    )
    if table.hand is None and not steps:
        return ()
    traced = dict(table.traces.steps)
    rows = (StepRow(StepKind.DEAL), *(_row_of(step) for step in steps))
    return tuple(replace(row, traceparent=traced.get(slot)) for slot, row in enumerate(rows, start=1))


def _card(suit: str | None, rank: str | None) -> Card:
    if suit is None or rank is None:
        message = "a stored step names a card without its suit or rank"
        raise ValueError(message)
    return Card(SUIT_OF_TEXT[suit], RANK_OF_TEXT[rank])


def _cards(row: StepRow) -> tuple[Card, Card]:
    return _card(row.suit, row.rank), _card(row.second_suit, row.second_rank)


def _position_of(row: StepRow) -> Position:
    if row.position is None:
        message = f"a stored {row.kind.value} step names no position"
        raise ValueError(message)
    return POSITION_OF_TEXT[row.position]


def _declare_of(row: StepRow) -> Declare:
    if row.game is None or row.hand is None or row.ouvert is None or row.announcement is None:
        message = "a stored declare step names no whole game"
        raise ValueError(message)
    return Declare(
        GAME_OF_TEXT[row.game], hand=row.hand, ouvert=row.ouvert, announcement=ANNOUNCEMENT_OF_TEXT[row.announcement]
    )


def _auction_step_of(row: StepRow) -> AuctionStep:
    """The auction step a stored row names; a value only a bid carries, so a row whose value misfits its kind raises
    instead of decoding as another step.
    """
    action = _ACTION_OF_KIND[row.kind]
    if action is AuctionAction.BID and row.value is None:
        message = "a stored bid step names no value"
        raise ValueError(message)
    if action is not AuctionAction.BID and row.value is not None:
        message = f"a stored {row.kind.value} step carries a value"
        raise ValueError(message)
    return step_of(action, row.value, _position_of(row))


def _word_of(row: StepRow) -> Word:
    if row.word is None:
        message = "a stored word step names no word"
        raise ValueError(message)
    return Word(row.word)


@dataclass
class _Phases:
    auction: list[AuctionStep]
    pushing: list[PushingStep]
    declaring: list[DeclaringStep]
    plays: list[CardPlayed]
    words: list[WordSaid]


def _sort_into(phases: _Phases, row: StepRow) -> None:
    kind = row.kind
    if kind in _ACTION_OF_KIND:
        phases.auction.append(_auction_step_of(row))
    elif kind in _STAGE_STEPS:
        phases.pushing.append(_STAGE_STEPS[kind](_position_of(row)))
    elif kind is StepKind.STAGE_PUT:
        phases.pushing.append(Put(_position_of(row), _cards(row)))
    elif kind is StepKind.TAKE_SKAT:
        phases.declaring.append(TakeSkat())
    elif kind is StepKind.PUT_BACK:
        phases.declaring.append(PutBack(_cards(row)))
    elif kind is StepKind.DECLARE:
        phases.declaring.append(_declare_of(row))
    elif kind is StepKind.CARD:
        phases.plays.append(CardPlayed(_position_of(row), _card(row.suit, row.rank)))
    elif kind is StepKind.WORD:
        phases.words.append(WordSaid(_position_of(row), _word_of(row), len(phases.plays)))


def decoded(rows: Iterable[StepRow], standing: HandProgress, ending: str | None) -> tuple[HandProgress, EntryTraces]:
    """The hand's progress from its log and its standing state, and the traces of its steps and of `ending`, the
    trace of its end; the version's trace is the table row's.
    """
    phases = _Phases([], [], [], [], [])
    traced: list[tuple[int, str]] = []
    for slot, row in enumerate(rows, start=1):
        _sort_into(phases, row)
        if row.traceparent is not None:
            traced.append((slot, row.traceparent))
    progress = replace(
        standing,
        auction=tuple(phases.auction),
        pushing=tuple(phases.pushing),
        declaring=tuple(phases.declaring),
        plays=tuple(phases.plays),
        words=tuple(phases.words),
    )
    return progress, EntryTraces(None, tuple(traced), ending)


def _text_of(position: Position | None) -> str | None:
    return None if position is None else POSITION_TEXT[position]


def _position_or_none(text: str | None) -> Position | None:
    return None if text is None else POSITION_OF_TEXT[text]


def standing_values(progress: HandProgress) -> dict[str, object]:
    """The columns of the hand's standing state, named as `hands` names them."""
    asked = progress.give_up
    return {
        "give_up_asked_by": None if asked is None else POSITION_TEXT[asked.asker],
        "give_up_declined_by": None if asked is None else _text_of(asked.declined_by),
        "give_up_claim": None if asked is None or asked.claim is None else ANNOUNCEMENT_TEXT[asked.claim],
        "give_up_agreed_by": None if asked is None else _text_of(asked.agreed_by),
        "give_up_open": asked is not None and asked.open_play,
        "shortening_refused_by": _text_of(progress.shortening_refused_by),
        "played_open": sorted(POSITION_TEXT[each] for each in progress.played_open),
        "abort_yes_seats": sorted(progress.abort_yes),
        "aborted": progress.aborted,
    }


def _give_up_of(row: Row[Any]) -> GiveUpAsked | None:
    if row.give_up_asked_by is None:
        return None
    claim = row.give_up_claim
    return GiveUpAsked(
        POSITION_OF_TEXT[row.give_up_asked_by],
        _position_or_none(row.give_up_declined_by),
        None if claim is None else ANNOUNCEMENT_OF_TEXT[claim],
        _position_or_none(row.give_up_agreed_by),
        row.give_up_open,
    )


def standing_of(row: Row[Any], *, aborted: bool) -> HandProgress:
    """The hand's standing state, on a hand with no step, from a row with the columns `hands` and the table row both
    name alike; `aborted` is the one they name apart.
    """
    return HandProgress(
        give_up=_give_up_of(row),
        shortening_refused_by=_position_or_none(row.shortening_refused_by),
        played_open=frozenset(POSITION_OF_TEXT[each] for each in row.played_open),
        abort_yes=frozenset(row.abort_yes_seats),
        aborted=aborted,
    )


def read_log(connection: Connection, table_id: str) -> tuple[StepRow, ...]:
    rows = connection.execute(
        select(hand_steps).where(hand_steps.c.table_id == table_id).order_by(hand_steps.c.ordinal)
    )
    return tuple(
        StepRow(
            StepKind(row.kind),
            row.position,
            row.value,
            row.suit,
            row.rank,
            row.second_suit,
            row.second_rank,
            row.game,
            row.hand,
            row.ouvert,
            row.announcement,
            row.word,
            row.traceparent,
        )
        for row in rows
    )


def stamped_hand(connection: Connection, table_id: str) -> Row[Any] | None:
    """The table's `hands` row while it was written for the table's version; None when another release moved the
    table since, or the table never dealt.
    """
    return connection.execute(
        select(hands)
        .join(tables, tables.c.id == hands.c.table_id)
        .where(hands.c.table_id == table_id, hands.c.stamp_version == tables.c.version)
    ).one_or_none()


def save_hand_log(connection: Connection, table: TableRecord, *, rewrite: bool) -> None:
    """Store the table's hand in the log and stamp its `hands` row with the table's version. The log appends the steps
    not yet stored, and stored steps that are no prefix of the hand's raise; `rewrite` deletes the stored ones first,
    for a new hand, a hand whose end forgets its steps, and a log another release left behind. A table with no hand
    and no step leaves a stored deal that took no step alone, as it leaves the dealt cards.
    """
    table_id = table.id.value
    log = encoded(table)
    if rewrite:
        connection.execute(delete(hand_steps).where(hand_steps.c.table_id == table_id))
    stored = () if rewrite else read_log(connection, table_id)
    deal_alone = not log and len(stored) == 1
    fresh = () if deal_alone else unstored_steps(table_id, stored, log)
    if fresh:
        rows = [
            {"table_id": table_id, "ordinal": ordinal, **asdict(row), "kind": row.kind.value}
            for ordinal, row in enumerate(fresh, start=len(stored) + 1)
        ]
        connection.execute(insert(hand_steps), rows)
    if table.dealer is None:
        return
    values = {**standing_values(table.progress), "end_traceparent": table.traces.ending, "stamp_version": table.version}
    written = upsert(hands).values(table_id=table_id, **values)
    connection.execute(written.on_conflict_do_update(index_elements=[hands.c.table_id], set_=values))


def forget_hand_log(connection: Connection, table_id: str) -> None:
    """Forget the table's log and its `hands` row, as the table's end does."""
    connection.execute(delete(hand_steps).where(hand_steps.c.table_id == table_id))
    connection.execute(delete(hands).where(hands.c.table_id == table_id))
