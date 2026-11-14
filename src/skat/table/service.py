import copy
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from skat.table.auction import AUCTION_STEP_COMMAND, AuctionCommand, auction_payload, decide_step
from skat.table.declaring import DECLARING_STEP_COMMAND, DeclaringCommand, decide_declaring_step, declaring_payload
from skat.table.ending import close_table, end_unplayed_table, forget_ended_tables, table_with_opener, unplayed_tables
from skat.table.game_list import series_list_view_of
from skat.table.hand_abort import (
    AGREE_TO_ABORT_COMMAND,
    REFUSE_TO_ABORT_COMMAND,
    AbortVoteCommand,
    abort_vote_payload,
    decide_agree_to_abort,
    decide_refuse_to_abort,
)
from skat.table.kontra import KONTRA_COMMAND, KontraCommand, decide_kontra, kontra_payload
from skat.table.lobby import LobbyReads
from skat.table.member_place import (
    Acceptance,
    AcceptResult,
    InvitationId,
    InvitationOffer,
    InviteRefusal,
    MemberRefusal,
    TableOffers,
    TableStanding,
    agent_in_chair,
    agents_seated_at,
    at_the_table,
    decide_accept,
    decide_invite,
    standings_of,
    table_offers_of,
)
from skat.table.member_view import (
    MemberActs,
    MemberView,
    ViewSignal,
    member_acts_of,
    member_view_of,
    moment_at,
    moment_recipients,
    view_recipients,
)
from skat.table.moment import TableMoment
from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    GiveUpCommand,
    PlayCardCommand,
    PlayOpenCommand,
    ShortenCommand,
    ThrowDownCommand,
    agree_to_give_up_payload,
    card_payload,
    decide_agree_to_give_up,
    decide_card,
    decide_decline_give_up,
    decide_give_up,
    decide_play_open,
    decide_shorten,
    decide_throw_down,
    decline_give_up_payload,
    give_up_payload,
    play_open_payload,
    shorten_payload,
    throw_down_payload,
)
from skat.table.pushing import PUSHING_STEP_COMMAND, PushingCommand, decide_pushing_step, pushing_payload
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
    CloseTable,
    CreateTable,
    Decision,
    EndedTable,
    Refusal,
    SendAway,
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
    PLAY_OPEN_COMMAND,
    SHORTEN_COMMAND,
    SIT_DOWN_COMMAND,
    STAND_UP_COMMAND,
    THROW_DOWN_COMMAND,
    CommandIdReusedError,
    command_receipt,
    create_receipt,
    decide_create,
    decide_sit,
    decide_stand,
    drawn_hand,
    hand_was_dealt,
    is_deal_or_step_of_play,
    present_at,
    replayed_decision,
    replayed_table,
    result_pending,
    seated_if_hand_ended,
    sit_deals,
    sit_payload,
    stand_payload,
)
from skat.table.send_away import SEND_AWAY_COMMAND, decide_send_away_by, save_book_after_send_away, send_away_payload
from skat.table.series_end import (
    AGREE_TO_END_SERIES_COMMAND,
    REFUSE_TO_END_SERIES_COMMAND,
    SeriesEndCommand,
    decide_agree_to_end,
    decide_refuse_to_end,
    series_end_payload,
)
from skat.table.server_steps import ServerSteps
from skat.table.transactions import DuplicateReceiptError
from skat.table.views import CommandResult, TableView, view_of

if TYPE_CHECKING:
    import random
    from collections.abc import Callable, Sequence
    from contextlib import AbstractContextManager

    from skat.table.game_list import RamschSeriesEntryView, SeriesEntryView
    from skat.table.member_place import CallFacts
    from skat.table.transactions import OccupiedChair, TableTransaction, TableTransactions

__all__ = ["CommandIdReusedError", "CommandResult", "TableService"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TableService(LobbyReads):
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
        self._standings_changed: Callable[[frozenset[str]], None] = lambda _accounts: None
        self._view_changed: ViewSignal = lambda _table_id, _accounts: None
        self._tools_changed: Callable[[frozenset[str]], None] = lambda _accounts: None
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

    def with_tools_signal(self, signal: Callable[[frozenset[str]], None]) -> TableService:
        """The same service where each commit that seats an agent, frees its chair or moves its seat on to another
        moment tells `signal` the agents it concerns, after the commit and on the thread the command ran on; no change
        tells it nothing.
        """
        clone = copy.copy(self)
        clone._tools_changed = signal  # noqa: SLF001 - the clone is this class's own instance
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
                return view_of(replayed_table(replay, command), actor.account_id, frozenset(), actor.account_id)
            table = decide_create(
                actor, self._new_table_id(), command.series_length, command.options, command.visibility
            )
            transaction.add_table(table, actor.display_name)
            transaction.set_empty_since(table.id, self._now())
            transaction.add_receipt(create_receipt(actor, command, table))
        self._tell_seats(agents_seated_at(table))
        return view_of(table, actor.account_id, frozenset(), actor.account_id)

    def sit(self, actor: Actor, command: SitDown, connected_accounts: frozenset[str]) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            SIT_DOWN_COMMAND,
            sit_payload(command),
            lambda table: decide_sit(
                table, actor, command.seat, drawn_hand(table, self._random_source) if sit_deals(table) else None
            ),
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

    def send_away(
        self, actor: Actor, command: SendAway, connected_accounts: frozenset[str], is_member: bool
    ) -> CommandResult | None:
        """Free an agent's chair at once, in every phase of a hand, and take the place from its standing in the same
        transaction: the agent's book row gets a higher epoch and no invitation. The hand waits for a sitter.

        `actor` must be at the table and a member of the calling group (`is_member`) or the agent's owner, else
        `not-allowed`, which writes no receipt. A replay and a refusal write no book row.
        """
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            SEND_AWAY_COMMAND,
            send_away_payload(command),
            lambda table: decide_send_away_by(table, command, actor, connected_accounts, is_member, self._now()),
            lambda transaction, table: save_book_after_send_away(transaction, table.id, command.agent_account),
        )

    def replayed_send_away(self, actor: Actor, command: SendAway) -> Decision | None:
        """The outcome of this person's earlier send-away under the command id, None if none; it writes nothing and
        raises `CommandIdReusedError` for another request under the id.
        """
        with self._transactions.begin() as transaction:
            replay = transaction.replay(actor.account_id, command.command_id)
        return None if replay is None else replayed_decision(replay, SEND_AWAY_COMMAND, send_away_payload(command))

    def take_auction_step(
        self, actor: Actor, command: AuctionCommand, connected_accounts: frozenset[str]
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

    def take_pushing_step(
        self, actor: Actor, command: PushingCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            PUSHING_STEP_COMMAND,
            pushing_payload(command),
            lambda table: decide_pushing_step(table, actor, command),
        )

    def play_card(
        self, actor: Actor, command: PlayCardCommand, connected_accounts: frozenset[str]
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

    def give_up(self, actor: Actor, command: GiveUpCommand, connected_accounts: frozenset[str]) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            GIVE_UP_COMMAND,
            give_up_payload(command),
            lambda table: decide_give_up(table, actor, command),
        )

    def shorten(
        self, actor: Actor, command: ShortenCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            SHORTEN_COMMAND,
            shorten_payload(command),
            lambda table: decide_shorten(table, actor, command),
        )

    def play_open(
        self, actor: Actor, command: PlayOpenCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            PLAY_OPEN_COMMAND,
            play_open_payload(command),
            lambda table: decide_play_open(table, actor, command),
        )

    def agree_to_give_up(
        self, actor: Actor, command: AgreeToGiveUpCommand, connected_accounts: frozenset[str]
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
        self, actor: Actor, command: ThrowDownCommand, connected_accounts: frozenset[str]
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
            lambda table: decide_new_series(table, actor, command),
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

    def agree_to_abort_hand(
        self, actor: Actor, command: AbortVoteCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            AGREE_TO_ABORT_COMMAND,
            abort_vote_payload(command),
            lambda table: decide_agree_to_abort(table, actor),
        )

    def refuse_to_abort_hand(
        self, actor: Actor, command: AbortVoteCommand, connected_accounts: frozenset[str]
    ) -> CommandResult | None:
        return self._run_command(
            actor,
            connected_accounts,
            command.table_id,
            command.command_id,
            REFUSE_TO_ABORT_COMMAND,
            abort_vote_payload(command),
            lambda table: decide_refuse_to_abort(table, actor),
        )

    def free_chair(self, table_id: TableId, account_id: str, due: AbstractContextManager[bool]) -> bool:
        """The server's step of freeing the account's chair; see `ServerSteps.free_chair`."""
        return self._server_steps().free_chair(table_id, account_id, due)

    def deal_next(self, table_id: TableId, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        """The server's step of dealing the next hand; see `ServerSteps.deal_next`."""
        return self._server_steps().deal_next(table_id, connected_accounts)

    def end_empty_table(
        self,
        table_id: TableId,
        connected_accounts: AbstractContextManager[frozenset[str] | None],
        empty_seconds: int,
    ) -> bool:
        """The server's step of ending an empty table; see `ServerSteps.end_empty_table`."""
        return self._server_steps().end_empty_table(table_id, connected_accounts, empty_seconds)

    def note_presence(
        self,
        table_id: TableId,
        connected_accounts: AbstractContextManager[frozenset[str] | None],
        empty_seconds: int,
    ) -> bool:
        """The server's step of noting who is present; see `ServerSteps.note_presence`."""
        return self._server_steps().note_presence(table_id, connected_accounts, empty_seconds)

    def resume_empty_waits(self, empty_seconds: int) -> dict[str, float]:
        """The server's step at its start; see `ServerSteps.resume_empty_waits`."""
        return self._server_steps().resume_empty_waits(empty_seconds)

    def _server_steps(self) -> ServerSteps:
        return ServerSteps(
            self._transactions,
            self._live_leases,
            self._now,
            self._random_source,
            self._tell_seats,
            self._tell_view,
            self._tell_moments,
        )

    def unplayed_tables(self, days: int) -> tuple[TableId, ...]:
        return unplayed_tables(self._transactions, days, self._now())

    def end_unplayed_table(
        self, table_id: TableId, days: int, writing: AbstractContextManager[frozenset[str] | None]
    ) -> bool:
        """End a dealt table `days` days past its last deal or step of play, on the server's own account."""
        members = end_unplayed_table(self._transactions, table_id, days, writing, self._now)
        if members is None:
            return False
        self._tell_seats(members)
        return True

    def forget_ended_tables(self, days: int) -> None:
        forget_ended_tables(self._transactions, days, self._now())

    def close(self, actor: Actor, command: CloseTable) -> CommandResult | None:
        """Close the table for everyone if the actor opened it, the ended table as the answer, else the refusal
        `not-allowed`; None when no live table has the id.
        """
        closed = close_table(self._transactions, actor, command, self._now)
        if closed is None:
            return None
        self._tell_seats(closed.members)
        return closed.result

    def occupied_chairs(self) -> tuple[OccupiedChair, ...]:
        with self._transactions.begin() as transaction:
            return transaction.occupied_chairs()

    def invite_agent(self, table_id: TableId, facts: CallFacts, lasting: timedelta) -> InvitationOffer | InviteRefusal:
        """Write the call as an invitation standing `lasting` from now, if the decision under the locks offers it."""
        with self._transactions.begin() as transaction:
            table = transaction.locked_table(table_id)
            entry = transaction.locked_book_entry(table_id, facts.agent_account)
            written = decide_invite(table, entry, facts, InvitationId.random(), self._now(), lasting)
            if isinstance(written, InviteRefusal):
                return written
            book_row, offer = written
            if is_new := book_row != entry:
                transaction.save_book_entry(book_row)
        if is_new:
            self._tell(frozenset({facts.agent_account}))
        return offer

    def offers_at(
        self, table_id: TableId, calls: Sequence[CallFacts], seated_facts: Callable[[str], CallFacts]
    ) -> TableOffers | None:
        """Each call's offer and, from the same read of the table and the agents' rows, the offer of each seated agent
        no call names, on the facts `seated_facts` gives for its account; None when no live table has the id.
        """
        with self._transactions.begin() as transaction:
            if not isinstance(table := transaction.table(table_id), TableRecord):
                return None
            entries = [transaction.locked_book_entry(table_id, call.agent_account) for call in calls]
        return table_offers_of(table, calls, entries, seated_facts, self._now())

    def accept_invitation(
        self, agent: Actor, owner_account: str | None, acceptance: Acceptance, connected_accounts: frozenset[str]
    ) -> AcceptResult:
        """Seat the agent for the invitation it names at the chair it held in the running hand, else at the table's
        lowest free chair, in one transaction under the table's row lock, dealing as a sit does; or refuse and say why.

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
                new_hand=drawn_hand(table, self._random_source) if sit_deals(table) else None,
            )
            if decision.entry != entry:
                transaction.save_book_entry(decision.entry)
            if decision.table is not table:
                self._save_decided(transaction, SIT_DOWN_COMMAND, table, decision.table)
        if decision.entry != entry:
            self._tell(frozenset({agent.account_id}))
        self._tell_view(table_id, view_recipients(table, decision.table))
        self._tell_moments(
            moment_recipients(table, decision.table) | (agents_seated_at(decision.table) - agents_seated_at(table))
        )
        return AcceptResult(decision.refusal, result_pending(decision.table))

    def standings_of(self, agent_account: str) -> tuple[TableStanding, ...]:
        return standings_of(self._transactions, agent_account, self._now())

    def _tell(self, accounts: frozenset[str]) -> None:
        if accounts:
            self._standings_changed(accounts)

    def _tell_seats(self, accounts: frozenset[str]) -> None:
        """Tell agents that sat down or left: their standing changed and, with it, the tools they are offered."""
        self._tell(accounts)
        self._tell_moments(accounts)

    def _tell_view(self, table_id: TableId, accounts: frozenset[str]) -> None:
        if accounts:
            self._view_changed(table_id, accounts)

    def _tell_moments(self, accounts: frozenset[str]) -> None:
        if accounts:
            self._tools_changed(accounts)

    def _run_command(
        self,
        actor: Actor,
        connected_accounts: frozenset[str],
        table_id: str,
        command_id: str,
        command: str,
        payload: str,
        decide: Callable[[TableRecord], Decision],
        after_accepted: Callable[[TableTransaction, TableRecord], None] | None = None,
    ) -> CommandResult | None:
        """Run the command once; `after_accepted` writes more inside the transaction, after an accepted first run."""
        arguments = (actor, connected_accounts, table_id, command_id, command, payload, decide, after_accepted)
        try:
            return self._run_command_once(*arguments)
        except DuplicateReceiptError:
            # The same command id committed on another table between this one's lookup and its receipt;
            # the retry finds that receipt and replays it or refuses the reuse.
            return self._run_command_once(*arguments)

    def _run_command_once(
        self,
        actor: Actor,
        connected_accounts: frozenset[str],
        table_id: str,
        command_id: str,
        command: str,
        payload: str,
        decide: Callable[[TableRecord], Decision],
        after_accepted: Callable[[TableTransaction, TableRecord], None] | None,
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
            moved_on: frozenset[str] = frozenset()
            if replay is None:
                decision = decide(table)
                if decision.refusal is None:
                    self._save_decided(transaction, command, table, decision.table)
                    if after_accepted is not None:
                        after_accepted(transaction, decision.table)
                    told = agents_seated_at(table) ^ agents_seated_at(decision.table)
                    viewers = view_recipients(table, decision.table)
                    moved_on = moment_recipients(table, decision.table)
                if decision.refusal is not Refusal.NOT_ALLOWED:
                    # A refused authority is no outcome: the id stays free once the person has the right.
                    transaction.add_receipt(command_receipt(actor, command_id, command, payload, decision))
            else:
                decision = replayed_decision(replay, command, payload)
            present = present_at(decision.table, connected_accounts, self._live_leases())
            if replay is None:
                seated_when_hand_ended = seated_if_hand_ended(table, decision.table)
            result = CommandResult(
                view_of(decision.table, actor.account_id, present, transaction.opener_account(identifier)),
                decision.refusal,
                decision.holder,
                seated_when_hand_ended,
            )
        self._tell_seats(told)
        self._tell_view(identifier, viewers)
        self._tell_moments(moved_on)
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
        table, opener = table_with_opener(self._transactions, table_id)
        if table is None:
            return None
        present = (
            connected_accounts
            if isinstance(table, EndedTable)
            else present_at(table, connected_accounts, self._live_leases())
        )
        return view_of(table, actor.account_id, present, opener)

    def accounts_at_the_table(self, table_id: TableId, connected_accounts: frozenset[str]) -> frozenset[str]:
        """Who is at the live table for a call; an ended or missing table counts the open streams only."""
        table = self._table_read(table_id.value)
        return at_the_table(table, connected_accounts) if isinstance(table, TableRecord) else connected_accounts

    def member_view(self, account_id: str, table_id: str, connected_accounts: frozenset[str]) -> MemberView | None:
        """The live table's view for the account that holds a chair there, with whether the table waits for it; None
        for any other account, an ended table and a table that is not there.
        """
        table, opener = table_with_opener(self._transactions, table_id)
        if not isinstance(table, TableRecord):
            return None
        present = present_at(table, connected_accounts, self._live_leases())
        return member_view_of(table, account_id, present, opener)

    def member_acts(self, account_id: str, table_id: str) -> MemberActs | None:
        """The acts of the live table's latest hand for the account that holds a chair there; None for any other
        account, an ended table and a table that is not there.
        """
        table = self._table_read(table_id)
        return member_acts_of(table, account_id) if isinstance(table, TableRecord) else None

    def moments_of(self, account_id: str) -> frozenset[TableMoment]:
        """The moments of the account's seats at the live tables it holds a chair at, from one read; the lobby moment
        when it holds none.
        """
        with self._transactions.begin() as transaction:
            tables = [transaction.table(held.table_id) for held in transaction.tables_of(account_id)]
        moments = frozenset(moment_at(table, account_id) for table in tables if isinstance(table, TableRecord))
        return moments or frozenset({TableMoment.LOBBY})

    def agent_in_chair(self, table_id: str, seat: int) -> str | None:
        """The account of the agent that holds the chair `seat` of the live table; None for a person, a free chair,
        a table that ended and a table that is not there.
        """
        table = self._table_read(table_id)
        if not isinstance(table, TableRecord):
            return None
        return agent_in_chair(table, seat)

    def series_list(self, table_id: str) -> tuple[SeriesEntryView | RamschSeriesEntryView, ...] | None:
        """The table's list of finished games, the same for every viewer; None for no table, empty once it ended."""
        table = self._table_read(table_id)
        if table is None:
            return None
        return () if isinstance(table, EndedTable) else series_list_view_of(table)
