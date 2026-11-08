from contextlib import contextmanager
from typing import TYPE_CHECKING, Final, Literal

from sqlalchemy import delete, exists, insert, select, update
from sqlalchemy.exc import IntegrityError

from skat.engine.cards import DECK, Card
from skat.engine.deal import Deal, Position
from skat.store.auction import append_steps, delete_steps, read_steps
from skat.store.schema import (
    POSITION_TEXT,
    RANK_TEXT,
    SKAT_HOLDER,
    SUIT_TEXT,
    chairs,
    hand_cards,
    metadata,
    receipts,
    tables,
)
from skat.table.records import Chair, HandProgress, Occupant, Receipt, Replay, TableId, TableRecord, parsed_refusal
from skat.table.service import DuplicateReceiptError, OccupiedChair, TableTransaction

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.engine import Connection, Engine

__all__ = ["PostgresTableTransactions", "metadata"]

UNIQUE_VIOLATION: Final = "23505"


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


def _table_record(
    connection: Connection, table_id: str, *, row_lock: Literal["update", "share"] | None = "share"
) -> TableRecord | None:
    query = select(tables.c.version, tables.c.dealer).where(tables.c.id == table_id)
    if row_lock is not None:
        query = query.with_for_update(read=row_lock == "share")
    table = connection.execute(query).one_or_none()
    if table is None:
        return None
    seats = connection.execute(
        select(chairs.c.seat, chairs.c.account_id, chairs.c.display_name)
        .where(chairs.c.table_id == table_id)
        .order_by(chairs.c.seat)
    ).all()
    return TableRecord(
        id=TableId(table_id),
        version=table.version,
        chairs=tuple(
            Chair(seat.seat, None if seat.account_id is None else Occupant(seat.account_id, seat.display_name))
            for seat in seats
        ),
        dealer=table.dealer,
        hand=_read_hand(connection, table_id),
        progress=HandProgress(auction=read_steps(connection, table_id)),
    )


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
        # The receipt's foreign key guarantees the table.
        assert table is not None  # noqa: S101 - narrows the type for a row the schema guarantees
        return Replay(
            command=receipt.command,
            payload=receipt.payload,
            table=table,
            refusal=None if receipt.refusal is None else parsed_refusal(receipt.refusal),
            holder=receipt.holder,
        )

    def table(self, table_id: TableId) -> TableRecord | None:
        return _table_record(self._connection, table_id.value)

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        self._holds_row = True
        return _table_record(self._connection, table_id.value, row_lock="update")

    def save_table(self, table: TableRecord) -> None:
        hand_stored = self._connection.execute(
            select(exists().where(hand_cards.c.table_id == table.id.value))
        ).scalar_one()
        self._connection.execute(
            update(tables).where(tables.c.id == table.id.value).values(version=table.version, dealer=table.dealer)
        )
        if table.hand is None and hand_stored:
            self._connection.execute(delete(hand_cards).where(hand_cards.c.table_id == table.id.value))
        if table.hand is not None and not hand_stored:
            delete_steps(self._connection, table.id.value)
            self._connection.execute(insert(hand_cards), _hand_rows(table.id.value, table.hand))
        append_steps(self._connection, table.id.value, table.progress.auction)
        for chair in table.chairs:
            self._connection.execute(
                update(chairs)
                .where(chairs.c.table_id == table.id.value, chairs.c.seat == chair.seat)
                .values(
                    account_id=None if chair.occupant is None else chair.occupant.account_id,
                    display_name=None if chair.occupant is None else chair.occupant.display_name,
                )
            )

    def add_table(self, table: TableRecord) -> None:
        self._connection.execute(insert(tables).values(id=table.id.value, version=table.version))
        self._connection.execute(
            insert(chairs),
            [
                {
                    "table_id": table.id.value,
                    "seat": chair.seat,
                    "account_id": None if chair.occupant is None else chair.occupant.account_id,
                    "display_name": None if chair.occupant is None else chair.occupant.display_name,
                }
                for chair in table.chairs
            ],
        )

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]:
        return tuple(
            OccupiedChair(TableId(row.table_id), row.account_id)
            for row in self._connection.execute(
                select(chairs.c.table_id, chairs.c.account_id).where(chairs.c.account_id.is_not(None))
            )
        )

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
