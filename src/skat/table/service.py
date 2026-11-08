import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from skat.engine.deal import deal, draw_dealer
from skat.table.records import (
    Actor,
    CreateTable,
    Decision,
    FirstDeal,
    Receipt,
    Refusal,
    Replay,
    SitDown,
    StandUp,
    TableId,
    TableRecord,
)
from skat.table.rules import (
    SIT_DOWN_COMMAND,
    STAND_UP_COMMAND,
    CommandIdReusedError,
    create_receipt,
    decide_create,
    decide_free_chair,
    decide_sit,
    decide_stand,
    replayed_decision,
    replayed_table,
    seating_receipt,
    sit_deals,
    sit_payload,
    stand_payload,
)
from skat.table.views import TableView, view_of

if TYPE_CHECKING:
    import random
    from collections.abc import Callable
    from contextlib import AbstractContextManager

__all__ = [
    "CommandIdReusedError",
    "DuplicateReceiptError",
    "OccupiedChair",
    "SeatingResult",
    "TableService",
    "TableTransaction",
    "TableTransactions",
]


class DuplicateReceiptError(Exception):
    """Another transaction stored a receipt under the same (account, command id) first."""


class TableTransaction(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def replay(self, account_id: str, command_id: str) -> Replay | None: ...

    def table(self, table_id: TableId) -> TableRecord | None: ...

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        """The table, its row locked until the transaction ends; only the commands that change it read this way."""
        ...

    def save_table(self, table: TableRecord) -> None:
        """Write the table's version, chairs and dealer, and its hand when one first appears."""
        ...

    def add_table(self, table: TableRecord) -> None: ...

    def add_receipt(self, receipt: Receipt) -> None: ...

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]: ...


class TableTransactions(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def begin(self) -> AbstractContextManager[TableTransaction]:
        """One transaction: it commits when the block ends and rolls back when the block raises."""
        ...


@dataclass(frozen=True)
class OccupiedChair:
    table_id: TableId
    account_id: str


@dataclass(frozen=True)
class SeatingResult:
    """What a sit or stand command did: the table as the actor sees it, and why it changed nothing if it did not."""

    view: TableView
    refusal: Refusal | None = None
    holder: str | None = None


class TableService:
    """The table commands and views; every command is one transaction."""

    def __init__(
        self,
        transactions: TableTransactions,
        new_table_id: Callable[[], TableId] = TableId.random,
        random_source: random.Random | None = None,
    ) -> None:
        self._transactions = transactions
        self._new_table_id = new_table_id
        self._random_source = secrets.SystemRandom() if random_source is None else random_source

    def create(self, actor: Actor, command: CreateTable) -> TableView:
        try:
            return self._create_once(actor, command)
        except DuplicateReceiptError:
            # An identical request committed between this one's lookup and its receipt; the retry finds that receipt.
            return self._create_once(actor, command)

    def _create_once(self, actor: Actor, command: CreateTable) -> TableView:
        with self._transactions.begin() as transaction:
            replay = transaction.replay(actor.account_id, command.command_id)
            if replay is not None:
                return view_of(replayed_table(replay), actor.account_id, frozenset())
            table = decide_create(actor, self._new_table_id())
            transaction.add_table(table)
            transaction.add_receipt(create_receipt(actor, command, table))
            return view_of(table, actor.account_id, frozenset())

    def sit(self, actor: Actor, command: SitDown, connected_accounts: frozenset[str]) -> SeatingResult | None:
        return self._seat(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            SIT_DOWN_COMMAND,
            sit_payload(command),
            lambda table: decide_sit(table, actor, command.seat, self._first_deal(table)),
        )

    def stand(self, actor: Actor, command: StandUp, connected_accounts: frozenset[str]) -> SeatingResult | None:
        return self._seat(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            STAND_UP_COMMAND,
            stand_payload(command),
            lambda table: decide_stand(table, actor),
        )

    def free_chair(self, table_id: TableId, account_id: str) -> bool:
        """Free the account's chair on the server's own account, with no actor, command id or receipt.

        The decision re-reads the chair under the row lock, so a repeat, or a chair the account left in the
        meantime, changes nothing. True when it freed the chair.
        """
        with self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return False
            decision = decide_free_chair(table, account_id)
            if decision.refusal is not None:
                return False
            transaction.save_table(decision.table)
            return True

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]:
        with self._transactions.begin() as transaction:
            return transaction.occupied_chairs()

    def _first_deal(self, table: TableRecord) -> FirstDeal | None:
        """Randomness enters only here: the dealer, then the shuffle, both from the one source."""
        if not sit_deals(table):
            return None
        dealer = draw_dealer(self._random_source)
        hand = deal(self._random_source)
        return FirstDeal(dealer, hand)

    def _seat(
        self,
        actor: Actor,
        connected_accounts: frozenset[str],
        table_id: str,
        command_id: str,
        command: str,
        payload: str,
        decide: Callable[[TableRecord], Decision],
    ) -> SeatingResult | None:
        try:
            return self._seat_once(actor, connected_accounts, table_id, command_id, command, payload, decide)
        except DuplicateReceiptError:
            # The same command id committed on another table between this one's lookup and its receipt;
            # the retry finds that receipt and replays it or refuses the reuse.
            return self._seat_once(actor, connected_accounts, table_id, command_id, command, payload, decide)

    def _seat_once(
        self,
        actor: Actor,
        connected_accounts: frozenset[str],
        table_id: str,
        command_id: str,
        command: str,
        payload: str,
        decide: Callable[[TableRecord], Decision],
    ) -> SeatingResult | None:
        """Lock the table row, replay by actor and command id, decide, write, store the receipt; None for no table."""
        identifier = TableId.parse(table_id)
        if identifier is None:
            return None
        with self._transactions.begin() as transaction:
            table = transaction.locked_table(identifier)
            if table is None:
                return None
            replay = transaction.replay(actor.account_id, command_id)
            if replay is None:
                decision = decide(table)
                if decision.refusal is None:
                    transaction.save_table(decision.table)
                transaction.add_receipt(seating_receipt(actor, command_id, command, payload, decision))
            else:
                decision = replayed_decision(replay, command, payload)
            return SeatingResult(
                view_of(decision.table, actor.account_id, connected_accounts), decision.refusal, decision.holder
            )

    def view(self, actor: Actor, table_id: str, connected_accounts: frozenset[str]) -> TableView | None:
        identifier = TableId.parse(table_id)
        if identifier is None:
            return None
        with self._transactions.begin() as transaction:
            table = transaction.table(identifier)
        return None if table is None else view_of(table, actor.account_id, connected_accounts)
