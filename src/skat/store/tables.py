from contextlib import contextmanager
from typing import TYPE_CHECKING, Final

from sqlalchemy import Column, ForeignKey, ForeignKeyConstraint, Integer, MetaData, Table, Text, insert, select
from sqlalchemy.exc import IntegrityError

from skat.table.records import Chair, Occupant, Receipt, Replay, TableId, TableRecord
from skat.table.service import DuplicateReceiptError, TableTransaction

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.engine import Connection, Engine

UNIQUE_VIOLATION: Final = "23505"

metadata = MetaData()

tables = Table(
    "tables",
    metadata,
    Column("id", Text, primary_key=True),
    Column("version", Integer, nullable=False),
)

chairs = Table(
    "chairs",
    metadata,
    Column("table_id", Text, ForeignKey("tables.id"), primary_key=True),
    Column("seat", Integer, primary_key=True),
    Column("account_id", Text),
    Column("display_name", Text),
)

receipts = Table(
    "receipts",
    metadata,
    Column("account_id", Text, primary_key=True),
    Column("command_id", Text, primary_key=True),
    Column("command", Text, nullable=False),
    Column("payload", Text, nullable=False),
    Column("table_id", Text, nullable=False),
    ForeignKeyConstraint(["table_id"], ["tables.id"]),
)


def _table_record(connection: Connection, table_id: str) -> TableRecord | None:
    table = connection.execute(select(tables.c.version).where(tables.c.id == table_id)).one_or_none()
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
    )


class _PostgresTableTransaction:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def replay(self, account_id: str, command_id: str) -> Replay | None:
        receipt = self._connection.execute(
            select(receipts.c.command, receipts.c.payload, receipts.c.table_id).where(
                receipts.c.account_id == account_id, receipts.c.command_id == command_id
            )
        ).one_or_none()
        if receipt is None:
            return None
        table = _table_record(self._connection, receipt.table_id)
        # The receipt's foreign key guarantees the table.
        assert table is not None  # noqa: S101 - narrows the type for a row the schema guarantees
        return Replay(command=receipt.command, payload=receipt.payload, table=table)

    def table(self, table_id: TableId) -> TableRecord | None:
        return _table_record(self._connection, table_id.value)

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

    def add_receipt(self, receipt: Receipt) -> None:
        try:
            self._connection.execute(
                insert(receipts).values(
                    account_id=receipt.account_id,
                    command_id=receipt.command_id,
                    command=receipt.command,
                    payload=receipt.payload,
                    table_id=receipt.table_id.value,
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
