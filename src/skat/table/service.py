import copy
import secrets
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from skat.engine.deal import deal, draw_dealer, next_dealer
from skat.table.auction import AUCTION_STEP_COMMAND, AuctionCommand, auction_payload, decide_step
from skat.table.declaring import DECLARING_STEP_COMMAND, DeclaringCommand, decide_declaring_step, declaring_payload
from skat.table.game_list import series_list_view_of
from skat.table.playing import (
    GIVE_UP_COMMAND,
    PLAY_CARD_COMMAND,
    THROW_DOWN_COMMAND,
    GiveUpCommand,
    PlayCardCommand,
    ThrowDownCommand,
    card_payload,
    decide_card,
    decide_give_up,
    decide_throw_down,
    give_up_payload,
    throw_down_payload,
)
from skat.table.ready import (
    NEW_SERIES_COMMAND,
    READY_COMMAND,
    NewSeriesCommand,
    ReadyCommand,
    decide_new_series,
    decide_ready,
    new_series_payload,
    ready_payload,
)
from skat.table.records import (
    Actor,
    CommandRefusal,
    CreateTable,
    Decision,
    EndedTable,
    NewHand,
    Receipt,
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
    PresenceStep,
    ResumeStep,
    command_receipt,
    create_receipt,
    dealt_next,
    decide_create,
    decide_free_chair,
    decide_sit,
    decide_stand,
    ends_empty,
    hand_was_dealt,
    next_deal_due,
    presence_step,
    present_at,
    replayed_decision,
    replayed_table,
    resume_step,
    seated_if_hand_ended,
    sit_deals,
    sit_payload,
    stand_payload,
)
from skat.table.views import TableView, view_of

if TYPE_CHECKING:
    import random
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from skat.table.game_list import SeriesEntryView

__all__ = [
    "CommandIdReusedError",
    "CommandResult",
    "DuplicateReceiptError",
    "LiveWait",
    "OccupiedChair",
    "TableService",
    "TableTransaction",
    "TableTransactions",
]


class DuplicateReceiptError(Exception):
    """Another transaction stored a receipt under the same (account, command id) first."""


class TableTransaction(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def replay(self, account_id: str, command_id: str) -> Replay | None: ...

    def table(self, table_id: TableId) -> TableRecord | EndedTable | None: ...

    def locked_table(self, table_id: TableId) -> TableRecord | None:
        """A live table, its row locked exclusively for the transaction; only the commands that change it read this
        way. An ended table reads as none.
        """
        ...

    def save_table(self, table: TableRecord) -> None:
        """Write the table's version, chairs and dealer, a new hand's cards and steps, and new list entries.

        A passed-in hand's cards go and its steps stay until the next deal; a played-out hand, a record without a
        hand whose list grew, loses its cards and every step before its entry is appended. A stored hand stays as
        dealt: a record whose hand differs from it while the hand has progress raises, unless the third pass ended
        the hand. A list that does not continue the stored one raises, unless the record is a series' first deal, which
        empties the stored list first; a free chair that is ready raises too.
        """
        ...

    def add_table(self, table: TableRecord) -> None: ...

    def end_table(self, table_id: TableId, at: datetime, empty_seconds: int) -> None:
        """End the table whose row this transaction locked, once: its version rises by one, its dealer clears, and
        it keeps only its row and its create receipt, so its id is never issued again and a create retry finds it.
        """
        ...

    def empty_since(self, table_id: TableId) -> datetime | None:
        """Since when nobody has been at the table, or None while it is unset."""
        ...

    def set_empty_since(self, table_id: TableId, since: datetime | None) -> None:
        """Write the time since when nobody has been at the table, on the row this transaction locked; it changes
        nothing else, not even the version.
        """
        ...

    def live_empty_since(self) -> tuple[LiveWait, ...]:
        """Every live table with whether a hand was dealt on it and its time since when nobody has been there, each
        row locked by this transaction.
        """
        ...

    def add_receipt(self, receipt: Receipt) -> None: ...

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]: ...


class TableTransactions(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def begin(self) -> AbstractContextManager[TableTransaction]:
        """One transaction: it commits when the block ends and rolls back when the block raises."""
        ...


@dataclass(frozen=True)
class LiveWait:
    table_id: TableId
    dealer: int | None
    empty_since: datetime | None


@dataclass(frozen=True)
class OccupiedChair:
    table_id: TableId
    account_id: str


@dataclass(frozen=True)
class CommandResult:
    """What a table command did: the table as the actor sees it, and why it changed nothing if it did not.

    `seated_when_hand_ended` names who sat at the table if this command ended its hand; a replay names nobody, so a
    retry restarts no timer. `away_when_hand_ended` names those of them who were not present then.
    """

    view: TableView
    refusal: CommandRefusal | None = None
    holder: str | None = None
    seated_when_hand_ended: frozenset[str] = frozenset()
    away_when_hand_ended: frozenset[str] = frozenset()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TableService:
    """The table commands and views; every command is one transaction."""

    def __init__(
        self,
        transactions: TableTransactions,
        new_table_id: Callable[[], TableId] = TableId.random,
        random_source: random.Random | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._transactions = transactions
        self._live_leases: Callable[[], frozenset[str]] = frozenset
        self._now = now
        self._new_table_id = new_table_id
        self._random_source = secrets.SystemRandom() if random_source is None else random_source

    def with_leases(self, live_leases: Callable[[], frozenset[str]]) -> TableService:
        """The same service where every account with a live lease counts as present at the table it sits at.

        `live_leases` is read under the table's row lock and has no side effect.
        """
        clone = copy.copy(self)
        clone._live_leases = live_leases  # noqa: SLF001 - the clone is this class's own instance
        return clone

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
                return view_of(replayed_table(replay, command), actor.account_id, frozenset())
            table = decide_create(actor, self._new_table_id(), command.series_length, command.options)
            transaction.add_table(table)
            transaction.set_empty_since(table.id, self._now())
            transaction.add_receipt(create_receipt(actor, command, table))
            return view_of(table, actor.account_id, frozenset())

    def sit(self, actor: Actor, command: SitDown, connected_accounts: frozenset[str]) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            SIT_DOWN_COMMAND,
            sit_payload(command),
            lambda table: decide_sit(table, actor, command.seat, self._new_hand(table) if sit_deals(table) else None),
        )

    def stand(self, actor: Actor, command: StandUp, connected_accounts: frozenset[str]) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            STAND_UP_COMMAND,
            stand_payload(command),
            lambda table: decide_stand(table, actor),
        )

    def take_auction_step(
        self,
        actor: Actor,
        command: AuctionCommand,
        connected_accounts: frozenset[str],
        on_hand_ended: Callable[[frozenset[str]], None] | None = None,
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            AUCTION_STEP_COMMAND,
            auction_payload(command),
            lambda table: decide_step(table, actor, command),
            on_hand_ended,
        )

    def take_declaring_step(
        self, actor: Actor, command: DeclaringCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            DECLARING_STEP_COMMAND,
            declaring_payload(command),
            lambda table: decide_declaring_step(table, actor, command),
        )

    def play_card(
        self,
        actor: Actor,
        command: PlayCardCommand,
        connected_accounts: frozenset[str],
        on_hand_ended: Callable[[frozenset[str]], None] | None = None,
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            PLAY_CARD_COMMAND,
            card_payload(command),
            lambda table: decide_card(table, actor, command),
            on_hand_ended,
        )

    def give_up(
        self,
        actor: Actor,
        command: GiveUpCommand,
        connected_accounts: frozenset[str],
        on_hand_ended: Callable[[frozenset[str]], None],
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            GIVE_UP_COMMAND,
            give_up_payload(command),
            lambda table: decide_give_up(table, actor, command),
            on_hand_ended,
        )

    def throw_down(
        self,
        actor: Actor,
        command: ThrowDownCommand,
        connected_accounts: frozenset[str],
        on_hand_ended: Callable[[frozenset[str]], None],
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            THROW_DOWN_COMMAND,
            throw_down_payload(command),
            lambda table: decide_throw_down(table, actor, command),
            on_hand_ended,
        )

    def mark_ready(
        self, actor: Actor, command: ReadyCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            READY_COMMAND,
            ready_payload(command),
            lambda table: decide_ready(table, actor, command),
        )

    def start_new_series(
        self, actor: Actor, command: NewSeriesCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            NEW_SERIES_COMMAND,
            new_series_payload(command),
            lambda table: decide_new_series(table, actor),
        )

    def free_chair(self, table_id: TableId, account_id: str, due: AbstractContextManager[bool]) -> bool:
        """Free the account's chair on the server's own account, with no actor, command id or receipt.

        `due` is entered once the row is locked, so a command that committed meanwhile has had its say, and left
        after the commit; it yields whether the caller still wants the chair freed, and False changes nothing.
        The decision re-reads the chair under the row lock, so a repeat, or a chair the account left in the
        meantime, changes nothing either. True when it freed the chair.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None or not after_commit.enter_context(due):
                return False
            decision = decide_free_chair(table, account_id)
            if decision.refusal is not None:
                return False
            transaction.save_table(decision.table)
            return True

    def deal_next(self, table_id: TableId, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        """Deal the next hand on the server's own account, with no actor, command id or receipt.

        `connected_accounts` is entered once the row is locked and left after the commit; it yields who holds an open
        stream then, or None once the presence cannot tell, which deals nothing; a live lease counts for its occupant.
        The decision re-reads the table under the row lock, so a repeat, or a table that changed meanwhile, changes
        nothing. True when it dealt.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return False
            connected = present_at(table, after_commit.enter_context(connected_accounts), self._live_leases())
            if connected is None or not next_deal_due(table, connected):
                return False
            transaction.save_table(dealt_next(table, self._new_hand(table)))
            return True

    def end_empty_table(
        self,
        table_id: TableId,
        connected_accounts: AbstractContextManager[frozenset[str] | None],
        empty_seconds: int,
    ) -> bool:
        """End a table nobody is connected to and on which no hand was dealt, on the server's own account, with no
        actor, command id or receipt.

        `connected_accounts` is entered once the row is locked and left after the commit; it yields who holds an open
        stream then, or None once the presence cannot tell. The decision reads who is present under the row lock, so a
        repeat, a table that ended meanwhile, or a stream that opened since changes nothing. `empty_seconds` is the
        wait the answer will name. True when it ended the table.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return False
            present = present_at(table, after_commit.enter_context(connected_accounts), self._live_leases())
            if not ends_empty(table, present):
                return False
            transaction.end_table(table_id, self._now(), empty_seconds)
            return True

    def note_presence(
        self,
        table_id: TableId,
        connected_accounts: AbstractContextManager[frozenset[str] | None],
        empty_seconds: int,
    ) -> bool:
        """Bring the time since when nobody has been at the table in line with who is present, on the server's own
        account, with no actor, command id, receipt or version change.

        `connected_accounts` is entered once the row is locked and left after the commit, as for `end_empty_table`,
        so the last write after any change reflects the latest truth. A table someone arrives at after its time was
        up ends instead of reviving. True when it ended the table.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None:
                return False
            present = present_at(table, after_commit.enter_context(connected_accounts), self._live_leases())
            now = self._now()
            step = presence_step(table, present, transaction.empty_since(table_id), now, empty_seconds)
            if step is PresenceStep.END:
                transaction.end_table(table_id, now, empty_seconds)
            elif step is not PresenceStep.KEEP:
                transaction.set_empty_since(table_id, now if step is PresenceStep.STAMP else None)
            return step is PresenceStep.END

    def resume_empty_waits(self, empty_seconds: int) -> dict[str, float]:
        """At the server's start: give every live table on which no hand was dealt and that has no time one, end
        every such table whose wait is already up, and answer each remaining table's id with the seconds left of its
        wait; a table with a dealt hand pauses and is left out.
        """
        now = self._now()
        with self._transactions.begin() as transaction:
            resumed = tuple(
                (wait.table_id, resume_step(wait.dealer, wait.empty_since, now, empty_seconds))
                for wait in transaction.live_empty_since()
            )
            for table_id, resume in resumed:
                if resume.step is ResumeStep.STAMP:
                    transaction.set_empty_since(table_id, now)
        left: dict[str, float] = {}
        for table_id, resume in resumed:
            if resume.step is ResumeStep.SKIP:
                continue
            if resume.step is ResumeStep.END and self.end_empty_table(
                table_id, nullcontext(frozenset()), empty_seconds
            ):
                continue
            left[table_id.value] = resume.seconds_left
        return left

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]:
        with self._transactions.begin() as transaction:
            return transaction.occupied_chairs()

    def _new_hand(self, table: TableRecord) -> NewHand:
        """The only place a hand is drawn: a table's first dealer by lot, every later one in turn, then the shuffle.

        Randomness enters only here, both from the one source.
        """
        dealer = draw_dealer(self._random_source) if table.dealer is None else next_dealer(table.dealer)
        return NewHand(dealer, deal(self._random_source))

    def _run_command(
        self,
        actor: Actor,
        connected_accounts: frozenset[str],
        table_id: str,
        command_id: str,
        command: str,
        payload: str,
        decide: Callable[[TableRecord], Decision],
        on_hand_ended: Callable[[frozenset[str]], None] | None = None,
    ) -> CommandResult | None:
        try:
            return self._run_command_once(
                actor, connected_accounts, table_id, command_id, command, payload, decide, on_hand_ended
            )
        except DuplicateReceiptError:
            # The same command id committed on another table between this one's lookup and its receipt;
            # the retry finds that receipt and replays it or refuses the reuse.
            return self._run_command_once(
                actor, connected_accounts, table_id, command_id, command, payload, decide, on_hand_ended
            )

    def _run_command_once(
        self,
        actor: Actor,
        connected_accounts: frozenset[str],
        table_id: str,
        command_id: str,
        command: str,
        payload: str,
        decide: Callable[[TableRecord], Decision],
        on_hand_ended: Callable[[frozenset[str]], None] | None,
    ) -> CommandResult | None:
        """Lock the table row, replay by actor and command id, decide, write, store the receipt; None for no table.

        When the command ended the hand, `on_hand_ended` hears who sat at the table and is not connected, before
        the commit, so no one else locks the row between the end of the hand and what the caller does about it.
        """
        identifier = TableId.parse(table_id)
        if identifier is None:
            return None
        with self._transactions.begin() as transaction:
            table = transaction.locked_table(identifier)
            if table is None:
                return None
            replay = transaction.replay(actor.account_id, command_id)
            seated_when_hand_ended: frozenset[str] = frozenset()
            away_when_hand_ended: frozenset[str] = frozenset()
            if replay is None:
                decision = decide(table)
                if decision.refusal is None:
                    transaction.save_table(decision.table)
                    if hand_was_dealt(decision.table) and not hand_was_dealt(table):
                        transaction.set_empty_since(identifier, None)
                transaction.add_receipt(command_receipt(actor, command_id, command, payload, decision))
            else:
                decision = replayed_decision(replay, command, payload)
            present = present_at(decision.table, connected_accounts, self._live_leases())
            if replay is None:
                seated_when_hand_ended = seated_if_hand_ended(table, decision.table)
                away_when_hand_ended = seated_when_hand_ended - present
                if on_hand_ended is not None:
                    on_hand_ended(away_when_hand_ended)
            return CommandResult(
                view_of(decision.table, actor.account_id, present),
                decision.refusal,
                decision.holder,
                seated_when_hand_ended,
                away_when_hand_ended,
            )

    def _table_read(self, table_id: str) -> TableRecord | EndedTable | None:
        identifier = TableId.parse(table_id)
        if identifier is None:
            return None
        with self._transactions.begin() as transaction:
            return transaction.table(identifier)

    def view(self, actor: Actor, table_id: str, connected_accounts: frozenset[str]) -> TableView | None:
        table = self._table_read(table_id)
        if table is None:
            return None
        present = (
            connected_accounts
            if isinstance(table, EndedTable)
            else present_at(table, connected_accounts, self._live_leases())
        )
        return view_of(table, actor.account_id, present)

    def series_list(self, table_id: str) -> tuple[SeriesEntryView, ...] | None:
        """The table's list of finished games, the same for every viewer; None for no table, empty once it ended."""
        table = self._table_read(table_id)
        if table is None:
            return None
        return () if isinstance(table, EndedTable) else series_list_view_of(table)
