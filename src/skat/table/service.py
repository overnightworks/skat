import copy
import secrets
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from skat.engine.deal import deal, draw_dealer, next_dealer
from skat.table.auction import AUCTION_STEP_COMMAND, AuctionCommand, auction_payload, decide_step
from skat.table.declaring import DECLARING_STEP_COMMAND, DeclaringCommand, decide_declaring_step, declaring_payload
from skat.table.game_list import series_list_view_of
from skat.table.kontra import KONTRA_COMMAND, KontraCommand, decide_kontra, kontra_payload
from skat.table.member_place import (
    Acceptance,
    AcceptResult,
    InvitationId,
    InvitationOffer,
    InvitationRequest,
    InviteRefusal,
    MemberRefusal,
    TableStanding,
    agents_seated_at,
    decide_accept,
    decide_invite,
    forgotten_if_expired,
    standings_among,
)
from skat.table.member_view import MemberView, ViewSignal, member_view_of, view_recipients
from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    GiveUpCommand,
    PlayCardCommand,
    ThrowDownCommand,
    agree_to_give_up_payload,
    card_payload,
    decide_agree_to_give_up,
    decide_card,
    decide_decline_give_up,
    decide_give_up,
    decide_throw_down,
    decline_give_up_payload,
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
    SitDown,
    StandUp,
    TableId,
    TableRecord,
)
from skat.table.rules import (
    AGREE_TO_GIVE_UP_COMMAND,
    DECLINE_GIVE_UP_COMMAND,
    GIVE_UP_COMMAND,
    PLAY_CARD_COMMAND,
    SIT_DOWN_COMMAND,
    STAND_UP_COMMAND,
    THROW_DOWN_COMMAND,
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
    hold_frees_chair,
    is_deal_or_step_of_play,
    next_deal_due,
    presence_step,
    present_at,
    replayed_decision,
    replayed_table,
    result_pending,
    resume_step,
    seat_of,
    seated_if_hand_ended,
    sit_deals,
    sit_payload,
    stand_payload,
)
from skat.table.series_end import (
    AGREE_TO_END_SERIES_COMMAND,
    REFUSE_TO_END_SERIES_COMMAND,
    SeriesEndCommand,
    decide_agree_to_end,
    decide_refuse_to_end,
    series_end_payload,
)
from skat.table.transactions import DuplicateReceiptError
from skat.table.views import PausedEntryView, TableView, paused_entry_of, view_of

if TYPE_CHECKING:
    import random
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from skat.table.game_list import RamschSeriesEntryView, SeriesEntryView
    from skat.table.transactions import OccupiedChair, TableTransaction, TableTransactions

__all__ = ["CommandIdReusedError", "CommandResult", "TableService"]


@dataclass(frozen=True)
class CommandResult:
    """What a table command did: the table as the actor sees it, and why it changed nothing if it did not.

    `seated_when_hand_ended` names who sat at the table if this command ended its hand; a replay names nobody, so a
    retry restarts no pause.
    """

    view: TableView
    refusal: CommandRefusal | None = None
    holder: str | None = None
    seated_when_hand_ended: frozenset[str] = frozenset()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _tell_nobody(accounts: frozenset[str]) -> None:
    """The signal of a service no one listens to."""


def _show_nobody(table_id: TableId, accounts: frozenset[str]) -> None:
    """The view signal of a service no one listens to."""


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
        self._standings_changed: Callable[[frozenset[str]], None] = _tell_nobody
        self._view_changed: ViewSignal = _show_nobody
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

    def with_standing_signal(self, signal: Callable[[frozenset[str]], None]) -> TableService:
        """The same service where each commit that changes whether an agent is a member of a table tells `signal` the
        agents it concerns, after the commit and on the thread the command ran on; no change tells it nothing.
        """
        clone = copy.copy(self)
        clone._standings_changed = signal  # noqa: SLF001 - the clone is this class's own instance
        return clone

    def with_view_signal(self, signal: ViewSignal) -> TableService:
        """The same service where each commit that raised a table's version tells `signal` the table and the agents
        seated at it after the commit, on the thread the command ran on; a change that raised nothing tells it nothing.
        """
        clone = copy.copy(self)
        clone._view_changed = signal  # noqa: SLF001 - the clone is this class's own instance
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
            transaction.add_table(table, actor.display_name)
            transaction.set_empty_since(table.id, self._now())
            transaction.add_receipt(create_receipt(actor, command, table))
        self._tell(agents_seated_at(table))
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
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            AUCTION_STEP_COMMAND,
            auction_payload(command),
            lambda table: decide_step(table, actor, command),
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
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            PLAY_CARD_COMMAND,
            card_payload(command),
            lambda table: decide_card(table, actor, command),
        )

    def say_kontra(
        self, actor: Actor, command: KontraCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            KONTRA_COMMAND,
            kontra_payload(command),
            lambda table: decide_kontra(table, actor, command),
        )

    def give_up(
        self,
        actor: Actor,
        command: GiveUpCommand,
        connected_accounts: frozenset[str],
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            GIVE_UP_COMMAND,
            give_up_payload(command),
            lambda table: decide_give_up(table, actor, command),
        )

    def agree_to_give_up(
        self,
        actor: Actor,
        command: AgreeToGiveUpCommand,
        connected_accounts: frozenset[str],
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            AGREE_TO_GIVE_UP_COMMAND,
            agree_to_give_up_payload(command),
            lambda table: decide_agree_to_give_up(table, actor, command),
        )

    def decline_give_up(
        self, actor: Actor, command: DeclineGiveUpCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            DECLINE_GIVE_UP_COMMAND,
            decline_give_up_payload(command),
            lambda table: decide_decline_give_up(table, actor, command),
        )

    def throw_down(
        self,
        actor: Actor,
        command: ThrowDownCommand,
        connected_accounts: frozenset[str],
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            THROW_DOWN_COMMAND,
            throw_down_payload(command),
            lambda table: decide_throw_down(table, actor, command),
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

    def agree_to_end_series(
        self, actor: Actor, command: SeriesEndCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            AGREE_TO_END_SERIES_COMMAND,
            series_end_payload(command),
            lambda table: decide_agree_to_end(table, actor),
        )

    def refuse_to_end_series(
        self, actor: Actor, command: SeriesEndCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            REFUSE_TO_END_SERIES_COMMAND,
            series_end_payload(command),
            lambda table: decide_refuse_to_end(table, actor),
        )

    def free_chair(self, table_id: TableId, account_id: str, due: AbstractContextManager[bool]) -> bool:
        """Free the account's chair on the server's own account, with no actor, command id or receipt.

        `due` is entered once the row is locked, so a command that committed meanwhile has had its say, and left
        after the commit; it yields whether the caller still wants the chair freed, and False changes nothing.
        A table on which a hand was dealt frees no chair this way, and the refusal writes nothing. The decision
        re-reads the chair under the row lock, so a repeat, or a chair the account left in the meantime, changes
        nothing either. True when it freed the chair.
        """
        with ExitStack() as after_commit, self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            if table is None or not after_commit.enter_context(due) or not hold_frees_chair(table):
                return False
            decision = decide_free_chair(table, account_id)
            if decision.refusal is not None:
                return False
            transaction.save_table(decision.table, played_at=None)
        self._tell(agents_seated_at(table) - agents_seated_at(decision.table))
        self._tell_view(table_id, view_recipients(table, decision.table))
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
            dealt = dealt_next(table, self._new_hand(table))
            transaction.save_table(dealt, played_at=self._now())
        self._tell_view(table_id, view_recipients(table, dealt))
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
            members = self._members_of(transaction, table)
            transaction.end_table(table_id, self._now(), empty_seconds)
        self._tell(members)
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
            members: frozenset[str] = self._members_of(transaction, table) if step is PresenceStep.END else frozenset()
            if step is PresenceStep.END:
                transaction.end_table(table_id, now, empty_seconds)
            elif step is not PresenceStep.KEEP:
                transaction.set_empty_since(table_id, now if step is PresenceStep.STAMP else None)
        self._tell(members)
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

    def tables_held_by(self, account_id: str) -> tuple[TableId, ...]:
        """The tables the account holds a chair at, each once, in id order; an unlocked scan, so a candidate list."""
        held = {chair.table_id for chair in self.occupied_chairs() if chair.account_id == account_id}
        return tuple(sorted(held, key=lambda table_id: table_id.value))

    def paused_tables(self, actor: Actor, days: int) -> tuple[PausedEntryView, ...]:
        """The live tables on which a hand was dealt and whose chair the actor holds, the soonest end first, ties in
        id order; a table ends `days` days after the time of its last deal or step of play.

        The chair scan is unlocked, so each candidate is read again in one transaction under its shared row lock: an
        ended table, a table without a dealt hand and one whose chair the actor left meanwhile are skipped.
        """
        candidates = self.tables_held_by(actor.account_id)
        with self._transactions.begin() as transaction:
            tables = (transaction.table(table_id) for table_id in candidates)
            entries: list[PausedEntryView] = []
            for table in tables:
                if (
                    isinstance(table, TableRecord)
                    and hand_was_dealt(table)
                    and seat_of(table, actor.account_id) is not None
                ):
                    facts = transaction.paused_facts(table.id)
                    ends_at = facts.last_played_at.astimezone(UTC) + timedelta(days=days)
                    entries.append(paused_entry_of(table, actor.account_id, ends_at, facts.opener_name))
        return tuple(sorted(entries, key=lambda entry: (entry.ends_at, entry.id)))

    def invite_agent(self, table_id: TableId, request: InvitationRequest) -> InvitationOffer | InviteRefusal:
        """Write an invitation to the agent for the table, with the expiry instant the caller names.

        Refused, and nothing written, when the table is not live, an invitation to the agent is open or the agent
        holds a chair there. Room at the table and the owner's presence are the caller's to check.
        """
        with self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            entry = transaction.locked_book_entry(table_id, request.agent_account)
            written = decide_invite(table, entry, request, InvitationId.random(), self._now())
            if isinstance(written, InviteRefusal):
                return written
            transaction.save_book_entry(written[0])
        self._tell(frozenset({request.agent_account}))
        return written[1]

    def accept_invitation(
        self, agent: Actor, owner_account: str | None, acceptance: Acceptance, connected_accounts: frozenset[str]
    ) -> AcceptResult:
        """Seat the agent at the table's lowest free chair for the invitation it names, in one transaction under the
        table's row lock, dealing as a sit does; or refuse and say why.

        `owner_account` is the owner its token names, None for a token that names none, and `connected_accounts` who
        holds an open stream at the table. The command carries no command id and writes no receipt: a retry finds no
        open invitation and is stale.
        """
        table_id = TableId.parse(acceptance.table_id)
        stale = AcceptResult(MemberRefusal.STALE_INVITATION)
        if table_id is None:
            return stale
        with self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            entry = transaction.locked_book_entry(table_id, agent.account_id)
            if table is None or entry is None:
                return stale
            decision = decide_accept(
                table,
                entry,
                agent,
                owner_account,
                acceptance,
                owner_present=owner_account in connected_accounts,
                now=self._now(),
                new_hand=self._new_hand(table) if sit_deals(table) else None,
            )
            if decision.entry != entry:
                transaction.save_book_entry(decision.entry)
            if decision.table is not table:
                self._save_decided(transaction, SIT_DOWN_COMMAND, table, decision.table)
        if decision.entry != entry:
            self._tell(frozenset({agent.account_id}))
        self._tell_view(table_id, view_recipients(table, decision.table))
        return AcceptResult(decision.refusal, result_pending(decision.table))

    def standings_of(self, agent_account: str) -> tuple[TableStanding, ...]:
        """Every table the agent holds a chair at or has an open invitation to, from one read; the read forgets an
        invitation of the agent that ran out on the service's clock.
        """
        now = self._now()
        with self._transactions.begin() as transaction:
            entries = transaction.locked_book_entries_of(agent_account)
            kept = tuple(forgotten_if_expired(entry, now) for entry in entries)
            for before, after in zip(entries, kept, strict=True):
                if after != before:
                    transaction.save_book_entry(after)
            held = [chair.table_id for chair in transaction.occupied_chairs() if chair.account_id == agent_account]
        return standings_among(kept, held, now)

    def _tell(self, accounts: frozenset[str]) -> None:
        if accounts:
            self._standings_changed(accounts)

    def _tell_view(self, table_id: TableId, accounts: frozenset[str]) -> None:
        if accounts:
            self._view_changed(table_id, accounts)

    @staticmethod
    def _members_of(transaction: TableTransaction, table: TableRecord) -> frozenset[str]:
        """The agents whose standing the table's end changes: those that hold a chair and those invited."""
        return agents_seated_at(table) | transaction.book_accounts_at(table.id)

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
    ) -> CommandResult | None:
        try:
            return self._run_command_once(actor, connected_accounts, table_id, command_id, command, payload, decide)
        except DuplicateReceiptError:
            # The same command id committed on another table between this one's lookup and its receipt;
            # the retry finds that receipt and replays it or refuses the reuse.
            return self._run_command_once(actor, connected_accounts, table_id, command_id, command, payload, decide)

    def _run_command_once(
        self,
        actor: Actor,
        connected_accounts: frozenset[str],
        table_id: str,
        command_id: str,
        command: str,
        payload: str,
        decide: Callable[[TableRecord], Decision],
    ) -> CommandResult | None:
        """Lock the table row, replay by actor and command id, decide, write, store the receipt; None for no table."""
        identifier = TableId.parse(table_id)
        if identifier is None:
            return None
        with self._transactions.begin() as transaction:
            table = transaction.locked_table(identifier)
            if table is None:
                return None
            replay = transaction.replay(actor.account_id, command_id)
            seated_when_hand_ended: frozenset[str] = frozenset()
            told: frozenset[str] = frozenset()
            viewers: frozenset[str] = frozenset()
            if replay is None:
                decision = decide(table)
                if decision.refusal is None:
                    self._save_decided(transaction, command, table, decision.table)
                    told = agents_seated_at(table) ^ agents_seated_at(decision.table)
                    viewers = view_recipients(table, decision.table)
                transaction.add_receipt(command_receipt(actor, command_id, command, payload, decision))
            else:
                decision = replayed_decision(replay, command, payload)
            present = present_at(decision.table, connected_accounts, self._live_leases())
            if replay is None:
                seated_when_hand_ended = seated_if_hand_ended(table, decision.table)
            result = CommandResult(
                view_of(decision.table, actor.account_id, present),
                decision.refusal,
                decision.holder,
                seated_when_hand_ended,
            )
        self._tell(told)
        self._tell_view(identifier, viewers)
        return result

    def _save_decided(
        self, transaction: TableTransaction, command: str, before: TableRecord, after: TableRecord
    ) -> None:
        played = is_deal_or_step_of_play(command, before, after)
        transaction.save_table(after, played_at=self._now() if played else None)
        if hand_was_dealt(after) and not hand_was_dealt(before):
            transaction.set_empty_since(after.id, None)

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

    def member_view(self, account_id: str, table_id: str, connected_accounts: frozenset[str]) -> MemberView | None:
        """The live table's view for the account that holds a chair there, with whether the table waits for it; None
        for any other account, an ended table and a table that is not there.
        """
        table = self._table_read(table_id)
        if not isinstance(table, TableRecord):
            return None
        return member_view_of(table, account_id, present_at(table, connected_accounts, self._live_leases()))

    def series_list(self, table_id: str) -> tuple[SeriesEntryView | RamschSeriesEntryView, ...] | None:
        """The table's list of finished games, the same for every viewer; None for no table, empty once it ended."""
        table = self._table_read(table_id)
        if table is None:
            return None
        return () if isinstance(table, EndedTable) else series_list_view_of(table)
