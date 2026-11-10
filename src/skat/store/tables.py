from contextlib import contextmanager
from typing import TYPE_CHECKING, Final, Literal

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from skat.engine.bidding import PassedIn
from skat.engine.bock import BockOptions, BockOverlap, BockRounds, BockTrigger
from skat.engine.cards import DECK, Card
from skat.engine.deal import Deal, Position
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.store.auction import append_steps, auction_actions, delete_steps, read_steps
from skat.store.declaring import append_declaring_steps, declaring_steps, read_declaring_steps
from skat.store.game_list import append_game_list, game_list, read_game_list
from skat.store.kontra import append_words, kontra_words, read_words
from skat.store.playing import append_plays, played_cards, read_plays
from skat.store.schema import (
    POSITION_OF_TEXT,
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
from skat.table.hand_state import auction_of
from skat.table.records import (
    Chair,
    EndedTable,
    EndReason,
    GiveUpAsked,
    HandProgress,
    Occupant,
    Receipt,
    Replay,
    Series,
    TableId,
    TableOptions,
    TableRecord,
    parsed_refusal,
)
from skat.table.rules import CREATE_TABLE_COMMAND
from skat.table.service import DuplicateReceiptError, LiveWait, OccupiedChair, TableTransaction

if TYPE_CHECKING:
    from collections.abc import Generator
    from datetime import datetime

    from sqlalchemy.engine import Connection, Engine

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


def _kontra_options_of(sayer: str | None, reach: str | None, deadline: str | None) -> KontraOptions | None:
    """The table's Kontra options; its three columns are all set or all null."""
    if sayer is None or reach is None or deadline is None:
        return None
    return KontraOptions(KontraSayer(sayer), KontraReach(reach), KontraDeadline(deadline))


def _bock_options_of(triggers: list[str] | None, overlap: str | None) -> BockOptions | None:
    """The table's Bock options; its two columns are both set or both null."""
    if triggers is None or overlap is None:
        return None
    return BockOptions(frozenset(BockTrigger(trigger) for trigger in triggers), BockOverlap(overlap))


def _table_record(
    connection: Connection, table_id: str, *, row_lock: Literal["update", "share"] | None = "share"
) -> TableRecord | EndedTable | None:
    query = select(
        tables.c.version,
        tables.c.dealer,
        tables.c.end_reason,
        tables.c.empty_seconds,
        tables.c.series_length,
        tables.c.series_deals,
        tables.c.show_running_points,
        tables.c.give_up_asked_by,
        tables.c.give_up_declined_by,
        tables.c.kontra_sayer,
        tables.c.kontra_reach,
        tables.c.kontra_deadline,
        tables.c.bock_triggers,
        tables.c.bock_overlap,
        tables.c.bock_rounds,
    ).where(tables.c.id == table_id)
    if row_lock is not None:
        query = query.with_for_update(read=row_lock == "share")
    table = connection.execute(query).one_or_none()
    if table is None:
        return None
    if table.end_reason is not None:
        return EndedTable(TableId(table_id), table.version, EndReason(table.end_reason), table.empty_seconds)
    seats = connection.execute(
        select(chairs.c.seat, chairs.c.account_id, chairs.c.display_name, chairs.c.ready)
        .where(chairs.c.table_id == table_id)
        .order_by(chairs.c.seat)
    ).all()
    return TableRecord(
        id=TableId(table_id),
        version=table.version,
        chairs=tuple(
            Chair(
                seat.seat,
                None if seat.account_id is None else Occupant(seat.account_id, seat.display_name),
                ready=seat.ready,
            )
            for seat in seats
        ),
        dealer=table.dealer,
        hand=_read_hand(connection, table_id),
        progress=HandProgress(
            auction=read_steps(connection, table_id),
            declaring=read_declaring_steps(connection, table_id),
            plays=read_plays(connection, table_id),
            give_up=_read_give_up(table.give_up_asked_by, table.give_up_declined_by),
            words=read_words(connection, table_id),
        ),
        game_list=read_game_list(connection, table_id),
        series=None if table.series_length is None else Series(table.series_length, table.series_deals),
        options=TableOptions(
            show_running_points=table.show_running_points,
            kontra=_kontra_options_of(table.kontra_sayer, table.kontra_reach, table.kontra_deadline),
            bock=_bock_options_of(table.bock_triggers, table.bock_overlap),
        ),
        bock=BockRounds(tuple(table.bock_rounds)),
    )


def _bock_columns_of(bock: BockOptions | None) -> dict[str, object]:
    """The triggers sorted by their token, so the column reads the same however the request listed them."""
    return {
        "bock_triggers": None if bock is None else sorted(trigger.value for trigger in bock.triggers),
        "bock_overlap": None if bock is None else bock.overlap.value,
    }


def _read_give_up(asked_by: str | None, declined_by: str | None) -> GiveUpAsked | None:
    if asked_by is None:
        return None
    return GiveUpAsked(POSITION_OF_TEXT[asked_by], None if declined_by is None else POSITION_OF_TEXT[declined_by])


def _starts_series(table: TableRecord) -> bool:
    """The record holds a hand that is its series' first deal, which empties the list."""
    return table.series is not None and table.series.deals == 1 and table.hand is not None


def _forget_played_hand(connection: Connection, table_id: str) -> None:
    """A played-out hand keeps nothing but its list entry: its cards and every step it took go."""
    for rows in (hand_cards, auction_actions, declaring_steps, played_cards, kontra_words):
        connection.execute(delete(rows).where(rows.c.table_id == table_id))


def _kontra_columns_of(kontra: KontraOptions | None) -> dict[str, str | None]:
    return {
        "kontra_sayer": None if kontra is None else kontra.sayer.value,
        "kontra_reach": None if kontra is None else kontra.reach.value,
        "kontra_deadline": None if kontra is None else kontra.deadline.value,
    }


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
        # The receipt's foreign key guarantees the table, which stays as a tombstone after its end.
        assert table is not None  # noqa: S101 - narrows the type for a row the schema guarantees
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

    def _write_table_row(self, table: TableRecord) -> None:
        """The row's changing columns: the series length and the options are written by `add_table` and never here."""
        asked = table.progress.give_up
        self._connection.execute(
            update(tables)
            .where(tables.c.id == table.id.value)
            .values(
                version=table.version,
                dealer=table.dealer,
                series_deals=None if table.series is None else table.series.deals,
                bock_rounds=list(table.bock.remaining),
                give_up_asked_by=None if asked is None else POSITION_TEXT[asked.asker],
                give_up_declined_by=None
                if asked is None or asked.declined_by is None
                else POSITION_TEXT[asked.declined_by],
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
                    ready=chair.ready,
                )
            )

    def save_table(self, table: TableRecord) -> None:
        dealt = _read_hand(self._connection, table.id.value)
        ended = dealt is not None and table.hand is None
        passed_in = ended and isinstance(auction_of(table).result, PassedIn)
        played_out = ended and len(table.game_list) > len(read_game_list(self._connection, table.id.value))
        if dealt is not None and table.hand != dealt and table.progress != HandProgress() and not passed_in:
            message = f"the hand saved for table {table.id.value} differs from the one dealt"
            raise DealtHandRewrittenError(message)
        self._write_table_row(table)
        if dealt is None and _starts_series(table):
            self._connection.execute(delete(game_list).where(game_list.c.table_id == table.id.value))
        if passed_in:
            self._connection.execute(delete(hand_cards).where(hand_cards.c.table_id == table.id.value))
        if played_out:
            _forget_played_hand(self._connection, table.id.value)
        append_game_list(self._connection, table.id.value, table.game_list)
        if table.hand is not None and dealt is None:
            delete_steps(self._connection, table.id.value)
            self._connection.execute(insert(hand_cards), _hand_rows(table.id.value, table.hand))
        append_steps(self._connection, table.id.value, table.progress.auction)
        append_declaring_steps(self._connection, table.id.value, table.progress.declaring)
        append_plays(self._connection, table.id.value, table.progress.plays)
        append_words(self._connection, table.id.value, table.progress.words)
        self._write_chairs(table)

    def add_table(self, table: TableRecord) -> None:
        self._connection.execute(
            insert(tables).values(
                id=table.id.value,
                version=table.version,
                series_length=None if table.series is None else table.series.length,
                series_deals=None if table.series is None else table.series.deals,
                show_running_points=table.options.show_running_points,
                **_kontra_columns_of(table.options.kontra),
                **_bock_columns_of(table.options.bock),
            )
        )
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

    def end_table(self, table_id: TableId, at: datetime, empty_seconds: int) -> None:
        self._connection.execute(
            update(tables)
            .where(tables.c.id == table_id.value)
            .values(
                version=tables.c.version + 1,
                dealer=None,
                ended_at=at,
                end_reason=EndReason.EMPTY.value,
                empty_seconds=empty_seconds,
            )
        )
        _forget_played_hand(self._connection, table_id.value)
        for rows in (chairs, game_list):
            self._connection.execute(delete(rows).where(rows.c.table_id == table_id.value))
        self._connection.execute(
            delete(receipts).where(receipts.c.table_id == table_id.value, receipts.c.command != CREATE_TABLE_COMMAND)
        )

    def empty_since(self, table_id: TableId) -> datetime | None:
        return self._connection.execute(select(tables.c.empty_since).where(tables.c.id == table_id.value)).scalar_one()

    def set_empty_since(self, table_id: TableId, since: datetime | None) -> None:
        self._connection.execute(update(tables).where(tables.c.id == table_id.value).values(empty_since=since))

    def live_empty_since(self) -> tuple[LiveWait, ...]:
        return tuple(
            LiveWait(TableId(row.id), row.dealer, row.empty_since)
            for row in self._connection.execute(
                select(tables.c.id, tables.c.dealer, tables.c.empty_since)
                .where(tables.c.end_reason.is_(None))
                .with_for_update()
            )
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
