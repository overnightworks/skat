from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Final, Literal

from sqlalchemy import Integer, delete, exists, func, insert, literal, select, update
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from skat.engine.bidding import PassedIn
from skat.engine.cards import DECK, Card
from skat.engine.deal import Deal, Position
from skat.store.auction import append_steps, auction_actions, delete_steps, read_steps
from skat.store.declaring import append_declaring_steps, declaring_steps, read_declaring_steps
from skat.store.game_list import append_game_list, game_list, read_game_cards, read_game_list
from skat.store.kontra import append_words, kontra_no_words, kontra_words, read_no_words, read_words, write_no_words
from skat.store.member_book import accounts_at, forget_table, locked_entries_of, locked_entry, save_entry
from skat.store.playing import append_plays, played_cards, read_plays
from skat.store.pushing import append_pushing_steps, pushing_steps, read_pushing_steps
from skat.store.schema import (
    ANNOUNCEMENT_OF_TEXT,
    ANNOUNCEMENT_TEXT,
    POSITION_OF_TEXT,
    POSITION_TEXT,
    RANK_TEXT,
    SKAT_HOLDER,
    SUIT_TEXT,
    chair_holds,
    chairs,
    hand_cards,
    metadata,
    options_of,
    receipts,
    series,
    tables,
)
from skat.store.series import bock_of, insert_series, last_played_series, save_series, series_of, series_row
from skat.table.hand_state import auction_of
from skat.table.records import (
    Chair,
    EndedTable,
    Ending,
    EndReason,
    FormerHolder,
    GiveUpAsked,
    HandProgress,
    Occupant,
    OccupantKind,
    Receipt,
    Replay,
    SeatHeld,
    TableId,
    TableRecord,
    TableStyle,
    TurnStatement,
    Visibility,
    parsed_refusal,
)
from skat.table.rules import CREATE_TABLE_COMMAND, series_number_of
from skat.table.transactions import (
    DuplicateReceiptError,
    HeldChair,
    LiveWait,
    OccupiedChair,
    PausedFacts,
    TableTransaction,
    TableVersion,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence
    from datetime import datetime

    from sqlalchemy import ColumnElement, Row, ScalarSelect
    from sqlalchemy.engine import Connection, Engine

    from skat.table.game_cards import GameCards
    from skat.table.member_place import BookEntry

__all__ = ["DealtHandRewrittenError", "PostgresTableTransactions", "metadata"]

UNIQUE_VIOLATION: Final = "23505"


class DealtHandRewrittenError(Exception):
    """The hand being saved differs from the one dealt, while the hand already has progress."""


def _hand_rows(table_id: str, hand: Deal) -> list[dict[str, str]]:
    held = [(POSITION_TEXT[position], cards) for position, cards in hand.hands.items()]
    held.append((SKAT_HOLDER, hand.skat))
    return [
        {"table_id": table_id, "suit": SUIT_TEXT[card.suit], "rank": RANK_TEXT[card.rank], "holder": holder}
        for holder, cards in held
        for card in cards
    ]


def _read_hand(connection: Connection, table_id: str) -> Deal | None:
    """Each holder's cards in the engine's deck order; the rows carry no order of their own."""
    held = {
        (row.suit, row.rank): row.holder
        for row in connection.execute(
            select(hand_cards.c.suit, hand_cards.c.rank, hand_cards.c.holder).where(hand_cards.c.table_id == table_id)
        )
    }
    if not held:
        return None
    by_holder: dict[str, list[Card]] = {holder: [] for holder in (*POSITION_TEXT.values(), SKAT_HOLDER)}
    for card in DECK:
        by_holder[held[SUIT_TEXT[card.suit], RANK_TEXT[card.rank]]].append(card)
    return Deal(
        forehand=tuple(by_holder[POSITION_TEXT[Position.FOREHAND]]),
        middlehand=tuple(by_holder[POSITION_TEXT[Position.MIDDLEHAND]]),
        rearhand=tuple(by_holder[POSITION_TEXT[Position.REARHAND]]),
        skat=tuple(by_holder[SKAT_HOLDER]),
    )


def _chair_of(seat: Row[*tuple[Any, ...]]) -> Chair:
    occupant = (
        None
        if seat.account_id is None
        else Occupant(seat.account_id, seat.display_name, OccupantKind(seat.occupant_kind), seat.owner_account)
    )
    return Chair(seat.seat, occupant, ready=seat.ready, turn_state=_turn_state_of(seat))


def _turn_state_of(seat: Row[*tuple[Any, ...]]) -> TurnStatement | None:
    """The statement of the chair, read only while the account that stated it still sits there."""
    if seat.turn_state_account is None or seat.turn_state_account != seat.account_id:
        return None
    return TurnStatement(seat.turn_state_stopped, bool(seat.turn_state_thinking), seat.turn_state_at)


def _turn_state_values(chair: Chair) -> dict[str, Any]:
    """The columns of the chair's statement; a chair without one, or without an occupant, clears them."""
    statement = chair.turn_state
    if statement is None or chair.occupant is None:
        return {
            "turn_state_account": None,
            "turn_state_stopped": None,
            "turn_state_thinking": None,
            "turn_state_at": None,
        }
    return {
        "turn_state_account": chair.occupant.account_id,
        "turn_state_stopped": statement.stopped,
        "turn_state_thinking": statement.thinking,
        "turn_state_at": statement.stated_at,
    }


def _read_seats(connection: Connection, table_id: str) -> Sequence[Row[*tuple[Any, ...]]]:
    return connection.execute(
        select(
            chairs.c.seat,
            chairs.c.account_id,
            chairs.c.display_name,
            chairs.c.occupant_kind,
            chairs.c.owner_account,
            chairs.c.ready,
            chairs.c.held_in_hand,
            chairs.c.former_holder_name,
            chairs.c.turn_state_account,
            chairs.c.turn_state_stopped,
            chairs.c.turn_state_thinking,
            chairs.c.turn_state_at,
        )
        .where(chairs.c.table_id == table_id)
        .order_by(chairs.c.seat)
    ).all()


def _table_record(
    connection: Connection, table_id: str, *, row_lock: Literal["update", "share"] | None = "share"
) -> TableRecord | EndedTable | None:
    query = select(tables).where(tables.c.id == table_id)
    if row_lock is not None:
        query = query.with_for_update(read=row_lock == "share")
    table = connection.execute(query).one_or_none()
    if table is None:
        return None
    if table.end_reason is not None:
        return EndedTable(
            TableId(table_id),
            table.version,
            Ending(EndReason(table.end_reason), table.empty_seconds, table.unplayed_days, table.closed_by_name),
            last_played_series(connection, table_id),
        )
    seats = _read_seats(connection, table_id)
    current = series_row(connection, table_id, table.series_number)
    return TableRecord(
        id=TableId(table_id),
        version=table.version,
        chairs=tuple(_chair_of(seat) for seat in seats),
        dealer=table.dealer,
        hand=_read_hand(connection, table_id),
        progress=HandProgress(
            auction=read_steps(connection, table_id),
            declaring=read_declaring_steps(connection, table_id),
            plays=read_plays(connection, table_id),
            give_up=_read_give_up(table),
            shortening_refused_by=_position_of(table.shortening_refused_by),
            played_open=frozenset(POSITION_OF_TEXT[each] for each in table.played_open),
            words=read_words(connection, table_id),
            no_words=read_no_words(connection, table_id),
            pushing=read_pushing_steps(connection, table_id),
            abort_yes=frozenset(table.abort_yes_seats),
            aborted=table.hand_aborted,
            seats_held=frozenset(SeatHeld(account_id, seat.seat) for seat in seats for account_id in seat.held_in_hand),
            former_holders=frozenset(
                FormerHolder(seat.seat, seat.former_holder_name)
                for seat in seats
                if seat.former_holder_name is not None
            ),
        ),
        game_list=read_game_list(connection, table_id, table.series_number),
        series=series_of(current),
        options=options_of(current),
        bock=bock_of(current),
        visibility=Visibility(table.visibility),
        style=TableStyle(table.style),
    )


def _position_of(text: str | None) -> Position | None:
    return None if text is None else POSITION_OF_TEXT[text]


def _text_of(position: Position | None) -> str | None:
    return None if position is None else POSITION_TEXT[position]


def _read_give_up(table: Row[Any]) -> GiveUpAsked | None:
    if table.give_up_asked_by is None:
        return None
    return GiveUpAsked(
        POSITION_OF_TEXT[table.give_up_asked_by],
        _position_of(table.give_up_declined_by),
        None if table.give_up_claim is None else ANNOUNCEMENT_OF_TEXT[table.give_up_claim],
        _position_of(table.give_up_agreed_by),
        table.give_up_open,
    )


def _forget_played_hand(connection: Connection, table_id: str) -> None:
    """A played-out or aborted hand keeps nothing but its list entry, if it has one: its cards and every step it took
    go.
    """
    for rows in (
        hand_cards,
        auction_actions,
        declaring_steps,
        pushing_steps,
        played_cards,
        kontra_words,
        kontra_no_words,
    ):
        connection.execute(delete(rows).where(rows.c.table_id == table_id))


def _turn_statement_times_of_table() -> ScalarSelect[list[datetime]]:
    """The time of each statement among the table's chairs that its sitters stated, in seat order, as a correlated
    subquery: every chair keeps its own time, so a statement stamped earlier than another chair's still shows.
    """
    chair = aliased(chairs)
    return (
        select(func.array_agg(aggregate_order_by(chair.c.turn_state_at, chair.c.seat)))
        .where(chair.c.table_id == tables.c.id, chair.c.turn_state_account == chair.c.account_id)
        .scalar_subquery()
    )


def _hold_of(table_id: TableId, account_id: str) -> tuple[ColumnElement[bool], ...]:
    return chair_holds.c.table_id == table_id.value, chair_holds.c.account_id == account_id


class _PostgresTableTransaction:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._holds_row = False

    def replay(self, account_id: str, command_id: str) -> Replay | None:
        receipt = self._connection.execute(
            select(
                receipts.c.command,
                receipts.c.payload,
                receipts.c.table_id,
                receipts.c.refusal,
                receipts.c.holder,
            ).where(receipts.c.account_id == account_id, receipts.c.command_id == command_id)
        ).one_or_none()
        if receipt is None:
            return None
        # A command that already holds its table's row reads the receipt's table unlocked: a lock here could cycle
        # with a command at that table. A command holding no row reads it under the shared lock.
        table = _table_record(self._connection, receipt.table_id, row_lock=None if self._holds_row else "share")
        # The forgetting sweep deletes an ended table with its receipts: a receipt read before the sweep commits can
        # find its table gone, and a receipt that expired answers as none.
        if table is None:
            return None
        return Replay(
            command=receipt.command,
            payload=receipt.payload,
            table=table,
            refusal=None if receipt.refusal is None else parsed_refusal(receipt.refusal),
            holder=receipt.holder,
        )

    def table(self, table_id: TableId) -> TableRecord | EndedTable | None:
        return _table_record(self._connection, table_id.value)

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        self._holds_row = True
        table = _table_record(self._connection, table_id.value, row_lock="update")
        return table if isinstance(table, TableRecord) else None

    def _write_table_row(self, table: TableRecord, played_at: datetime | None) -> None:
        """The row's changing columns: the visibility and the opener's name are written by `add_table` and never here,
        the series' columns by `save_series`; no time leaves the last played time as it is.
        """
        asked = table.progress.give_up
        played = {} if played_at is None else {"last_played_at": played_at}
        self._connection.execute(
            update(tables)
            .where(tables.c.id == table.id.value)
            .values(
                version=table.version,
                dealer=table.dealer,
                style=table.style.value,
                **played,
                series_number=series_number_of(table),
                abort_yes_seats=sorted(table.progress.abort_yes),
                hand_aborted=table.progress.aborted,
                give_up_asked_by=None if asked is None else POSITION_TEXT[asked.asker],
                give_up_declined_by=None if asked is None else _text_of(asked.declined_by),
                give_up_claim=None if asked is None or asked.claim is None else ANNOUNCEMENT_TEXT[asked.claim],
                give_up_agreed_by=None if asked is None else _text_of(asked.agreed_by),
                give_up_open=asked is not None and asked.open_play,
                shortening_refused_by=_text_of(table.progress.shortening_refused_by),
                played_open=sorted(POSITION_TEXT[each] for each in table.progress.played_open),
            )
        )

    def _write_chairs(self, table: TableRecord) -> None:
        for chair in table.chairs:
            occupant = chair.occupant
            self._connection.execute(
                update(chairs)
                .where(chairs.c.table_id == table.id.value, chairs.c.seat == chair.seat)
                .values(
                    account_id=None if occupant is None else occupant.account_id,
                    display_name=None if occupant is None else occupant.display_name,
                    occupant_kind=None if occupant is None else occupant.kind.value,
                    owner_account=None if occupant is None else occupant.owner_account,
                    ready=chair.ready,
                    held_in_hand=sorted(
                        mark.account_id for mark in table.progress.seats_held if mark.seat == chair.seat
                    ),
                    former_holder_name=table.progress.former_holder_name(chair.seat),
                    **_turn_state_values(chair),
                )
            )

    def save_turn_state(self, table_id: TableId, chair: Chair) -> None:
        self._connection.execute(
            update(chairs)
            .where(chairs.c.table_id == table_id.value, chairs.c.seat == chair.seat)
            .values(**_turn_state_values(chair))
        )

    def game_cards(self, table_id: TableId, series_number: int, number: int) -> GameCards | None:
        return read_game_cards(self._connection, table_id.value, series_number, number)

    def save_table(self, table: TableRecord, *, played_at: datetime | None) -> None:
        dealt = _read_hand(self._connection, table.id.value)
        ended = dealt is not None and table.hand is None
        aborted = ended and table.progress.aborted
        passed_in = ended and isinstance(auction_of(table).result, PassedIn)
        series_number = series_number_of(table)
        played_out = ended and len(table.game_list) > len(
            read_game_list(self._connection, table.id.value, series_number)
        )
        if (
            dealt is not None
            and table.hand != dealt
            and table.progress != HandProgress()
            and not (passed_in or aborted)
        ):
            message = f"the hand saved for table {table.id.value} differs from the one dealt"
            raise DealtHandRewrittenError(message)
        self._write_table_row(table, played_at)
        save_series(self._connection, table)
        if passed_in:
            self._connection.execute(delete(hand_cards).where(hand_cards.c.table_id == table.id.value))
        if played_out or aborted:
            _forget_played_hand(self._connection, table.id.value)
        append_game_list(self._connection, table.id.value, series_number, table.game_list, played_at)
        if table.hand is not None and dealt is None:
            delete_steps(self._connection, table.id.value)
            self._connection.execute(insert(hand_cards), _hand_rows(table.id.value, table.hand))
        append_steps(self._connection, table.id.value, table.progress.auction)
        append_declaring_steps(self._connection, table.id.value, table.progress.declaring)
        append_pushing_steps(self._connection, table.id.value, table.progress.pushing)
        append_plays(self._connection, table.id.value, table.progress.plays)
        append_words(self._connection, table.id.value, table.progress.words)
        write_no_words(self._connection, table.id.value, table.progress.no_words)
        self._write_chairs(table)

    def add_table(self, table: TableRecord, opener_name: str) -> None:
        self._connection.execute(
            insert(tables).values(
                id=table.id.value,
                version=table.version,
                opener_name=opener_name,
                series_number=series_number_of(table),
                visibility=table.visibility.value,
            )
        )
        insert_series(self._connection, table)
        self._connection.execute(
            insert(chairs),
            [
                {
                    "table_id": table.id.value,
                    "seat": chair.seat,
                    "account_id": None if chair.occupant is None else chair.occupant.account_id,
                    "display_name": None if chair.occupant is None else chair.occupant.display_name,
                    "occupant_kind": None if chair.occupant is None else chair.occupant.kind.value,
                    "owner_account": None if chair.occupant is None else chair.occupant.owner_account,
                }
                for chair in table.chairs
            ],
        )

    def end_table(self, table_id: TableId, at: datetime, ending: Ending) -> None:
        self._connection.execute(
            update(tables)
            .where(tables.c.id == table_id.value)
            .values(
                version=tables.c.version + 1,
                dealer=None,
                last_played_at=None,
                opener_name=None,
                give_up_asked_by=None,
                give_up_declined_by=None,
                give_up_claim=None,
                give_up_agreed_by=None,
                give_up_open=False,
                shortening_refused_by=None,
                played_open=[],
                ended_at=at,
                end_reason=ending.reason.value,
                empty_seconds=ending.empty_seconds,
                unplayed_days=ending.unplayed_days,
                closed_by_name=ending.closed_by_name,
            )
        )
        _forget_played_hand(self._connection, table_id.value)
        self._connection.execute(delete(chairs).where(chairs.c.table_id == table_id.value))
        self._connection.execute(delete(chair_holds).where(chair_holds.c.table_id == table_id.value))
        forget_table(self._connection, table_id.value)
        self._connection.execute(
            delete(receipts).where(receipts.c.table_id == table_id.value, receipts.c.command != CREATE_TABLE_COMMAND)
        )

    def opener_account(self, table_id: TableId) -> str | None:
        return self._connection.execute(
            select(receipts.c.account_id).where(
                receipts.c.table_id == table_id.value, receipts.c.command == CREATE_TABLE_COMMAND
            )
        ).scalar_one_or_none()

    def played_before(self, cutoff: datetime) -> tuple[TableId, ...]:
        return tuple(
            TableId(table_id)
            for table_id in self._connection.execute(
                select(tables.c.id)
                .where(tables.c.end_reason.is_(None), tables.c.last_played_at <= cutoff)
                .order_by(tables.c.id)
            ).scalars()
        )

    def forget_ended_before(self, cutoff: datetime) -> int:
        gameless = (
            select(tables.c.id)
            .where(tables.c.ended_at <= cutoff, ~exists().where(game_list.c.table_id == tables.c.id))
            .scalar_subquery()
        )
        self._connection.execute(delete(receipts).where(receipts.c.table_id.in_(gameless)))
        self._connection.execute(delete(series).where(series.c.table_id.in_(gameless)))
        deleted = self._connection.execute(delete(tables).where(tables.c.id.in_(gameless))).rowcount
        self._connection.execute(
            update(tables)
            .where(tables.c.ended_at <= cutoff, tables.c.closed_by_name.is_not(None))
            .values(closed_by_name=None)
        )
        return deleted

    def empty_since(self, table_id: TableId) -> datetime | None:
        return self._connection.execute(select(tables.c.empty_since).where(tables.c.id == table_id.value)).scalar_one()

    def paused_facts(self, table_id: TableId) -> PausedFacts:
        row = self._connection.execute(
            select(tables.c.last_played_at, tables.c.opener_name).where(tables.c.id == table_id.value)
        ).one()
        return PausedFacts(row.last_played_at, row.opener_name)

    def set_empty_since(self, table_id: TableId, since: datetime | None) -> None:
        self._connection.execute(update(tables).where(tables.c.id == table_id.value).values(empty_since=since))

    def live_empty_since(self) -> tuple[LiveWait, ...]:
        return tuple(
            LiveWait(TableId(row.id), row.dealer, row.empty_since)
            for row in self._connection.execute(
                select(tables.c.id, tables.c.dealer, tables.c.empty_since)
                .where(tables.c.end_reason.is_(None))
                .order_by(tables.c.id)
                .with_for_update()
            )
        )

    def store_leave(self, table_id: TableId, account_id: str, hold_seconds: float, *, newest_wins: bool) -> None:
        seated = (
            select(
                chairs.c.table_id,
                chairs.c.account_id,
                func.now() + func.make_interval(0, 0, 0, 0, 0, 0, literal(hold_seconds)),
            )
            .join(tables, tables.c.id == chairs.c.table_id)
            .where(
                chairs.c.table_id == table_id.value,
                chairs.c.account_id == account_id,
                tables.c.end_reason.is_(None),
            )
        )
        written = upsert(chair_holds).from_select(["table_id", "account_id", "due_at"], seated)
        held = [chair_holds.c.table_id, chair_holds.c.account_id]
        self._connection.execute(
            written.on_conflict_do_update(index_elements=held, set_={"due_at": written.excluded.due_at})
            if newest_wins
            else written.on_conflict_do_nothing(index_elements=held)
        )

    def delete_hold(self, table_id: TableId, account_id: str) -> None:
        self._connection.execute(delete(chair_holds).where(*_hold_of(table_id, account_id)))

    def locked_hold_due(self, table_id: TableId, account_id: str) -> bool:
        due = self._connection.execute(
            select(chair_holds.c.due_at <= func.now()).where(*_hold_of(table_id, account_id)).with_for_update()
        ).scalar_one_or_none()
        return bool(due)

    def due_holds(self, limit: int) -> tuple[HeldChair, ...]:
        return tuple(
            HeldChair(TableId(row.table_id), row.account_id)
            for row in self._connection.execute(
                select(chair_holds.c.table_id, chair_holds.c.account_id)
                .where(chair_holds.c.due_at <= func.now())
                .order_by(chair_holds.c.due_at)
                .limit(limit)
            )
        )

    def hold_seconds_left(self, table_id: TableId) -> dict[str, int]:
        left = func.greatest(0, func.ceil(func.extract("epoch", chair_holds.c.due_at - func.now()))).cast(Integer)
        return {
            row.account_id: row.left
            for row in self._connection.execute(
                select(chair_holds.c.account_id, left.label("left")).where(chair_holds.c.table_id == table_id.value)
            )
        }

    def tables_of(self, account_id: str) -> tuple[TableVersion, ...]:
        return tuple(
            TableVersion(TableId(row.id), row.version, tuple(row.turn_statement_times or ()))
            for row in self._connection.execute(
                select(tables.c.id, tables.c.version, _turn_statement_times_of_table().label("turn_statement_times"))
                .join(chairs, chairs.c.table_id == tables.c.id)
                .where(chairs.c.account_id == account_id, tables.c.end_reason.is_(None))
                .order_by(tables.c.id)
            )
        )

    def open_table_ids(self) -> tuple[TableId, ...]:
        return tuple(
            TableId(table_id)
            for table_id in self._connection.execute(
                select(tables.c.id)
                .where(tables.c.end_reason.is_(None), tables.c.visibility == Visibility.OPEN.value)
                .order_by(tables.c.id)
            ).scalars()
        )

    def versions_of(self, table_ids: Iterable[TableId]) -> tuple[TableVersion, ...]:
        return tuple(
            TableVersion(TableId(row.id), row.version, tuple(row.turn_statement_times or ()))
            for row in self._connection.execute(
                select(tables.c.id, tables.c.version, _turn_statement_times_of_table().label("turn_statement_times"))
                .where(tables.c.id.in_([table_id.value for table_id in table_ids]), tables.c.end_reason.is_(None))
                .order_by(tables.c.id)
            )
        )

    def chairs_taken_by(self, table_ids: Iterable[TableId], account_ids: frozenset[str]) -> frozenset[OccupiedChair]:
        return frozenset(
            OccupiedChair(TableId(row.table_id), row.account_id)
            for row in self._connection.execute(
                select(chairs.c.table_id, chairs.c.account_id).where(
                    chairs.c.table_id.in_([table_id.value for table_id in table_ids]),
                    chairs.c.account_id.in_(account_ids),
                )
            )
        )

    def locked_book_entry(self, table_id: TableId, agent_account: str) -> BookEntry | None:
        return locked_entry(self._connection, table_id.value, agent_account)

    def locked_book_entries_of(self, agent_account: str) -> tuple[BookEntry, ...]:
        return locked_entries_of(self._connection, agent_account)

    def save_book_entry(self, entry: BookEntry) -> None:
        save_entry(self._connection, entry)

    def book_accounts_at(self, table_id: TableId) -> frozenset[str]:
        return accounts_at(self._connection, table_id.value)

    def add_receipt(self, receipt: Receipt) -> None:
        try:
            self._connection.execute(
                insert(receipts).values(
                    account_id=receipt.account_id,
                    command_id=receipt.command_id,
                    command=receipt.command,
                    payload=receipt.payload,
                    table_id=receipt.table_id.value,
                    refusal=receipt.refusal,
                    holder=receipt.holder,
                )
            )
        except IntegrityError as failure:
            if getattr(failure.orig, "sqlstate", None) == UNIQUE_VIOLATION:
                raise DuplicateReceiptError from failure
            raise  # pragma: no cover


class PostgresTableTransactions:
    """One Postgres transaction per `begin`: it commits when the block ends and rolls back when it raises."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def begin(self) -> Generator[TableTransaction]:
        with self._engine.begin() as connection:
            yield _PostgresTableTransaction(connection)
