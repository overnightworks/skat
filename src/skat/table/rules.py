from dataclasses import replace
from typing import TYPE_CHECKING, Final, overload

from skat.engine.deal import positions_from
from skat.table.records import (
    Actor,
    Chair,
    CreateTable,
    Decision,
    HandProgress,
    NewHand,
    Occupant,
    Receipt,
    Refusal,
    Replay,
    SitDown,
    StandUp,
    TableId,
    TableRecord,
)

if TYPE_CHECKING:
    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.table.records import EndedTable

CHAIRS_PER_TABLE: Final = 3
FIRST_VERSION: Final = 1
CREATE_TABLE_COMMAND: Final = "create-table"
CREATE_TABLE_PAYLOAD: Final = "{}"
SIT_DOWN_COMMAND: Final = "sit-down"
STAND_UP_COMMAND: Final = "stand-up"


class CommandIdReusedError(Exception):
    """A command id came back with a request other than the one it first carried."""


def decide_create(actor: Actor, table_id: TableId) -> TableRecord:
    """A new table with its opener in chair 1 and the other chairs free."""
    opener = Chair(1, Occupant(actor.account_id, actor.display_name))
    return TableRecord(
        id=table_id,
        version=FIRST_VERSION,
        chairs=(opener, *(Chair(seat, None) for seat in range(2, CHAIRS_PER_TABLE + 1))),
        dealer=None,
        hand=None,
        progress=HandProgress(),
        game_list=(),
    )


def create_receipt(actor: Actor, command: CreateTable, table: TableRecord) -> Receipt:
    return Receipt(actor.account_id, command.command_id, CREATE_TABLE_COMMAND, CREATE_TABLE_PAYLOAD, table.id)


def replayed_table(replay: Replay) -> TableRecord | EndedTable:
    """The table a create request already made; any other request under its key is refused."""
    return _replayed(replay, CREATE_TABLE_COMMAND, CREATE_TABLE_PAYLOAD).table


def _replayed(replay: Replay, command: str, payload: str) -> Replay:
    if (replay.command, replay.payload) != (command, payload):
        raise CommandIdReusedError
    return replay


def seat_of(table: TableRecord, account_id: str) -> Chair | None:
    return next((chair for chair in table.chairs if chair.occupant and chair.occupant.account_id == account_id), None)


def _with_occupant(table: TableRecord, seat: int, occupant: Occupant | None) -> TableRecord:
    """The table with a chair's new occupant, the one way a chair changes hands.

    A freed chair is never ready, and whoever sits while a result is pending counts as ready.
    """
    ready = occupant is not None and result_pending(table)
    chairs = tuple(Chair(seat, occupant, ready=ready) if chair.seat == seat else chair for chair in table.chairs)
    return TableRecord(
        id=table.id,
        version=table.version + 1,
        chairs=chairs,
        dealer=table.dealer,
        hand=table.hand,
        progress=table.progress,
        game_list=table.game_list,
    )


def sit_deals(table: TableRecord) -> bool:
    """A sit deals when it fills the last free chair, no hand runs and no result is pending."""
    free_chairs = sum(chair.occupant is None for chair in table.chairs)
    return free_chairs == 1 and not hand_runs(table) and not result_pending(table)


def hand_runs(table: TableRecord) -> bool:
    return table.hand is not None


def seated_if_hand_ended(before: TableRecord, after: TableRecord) -> frozenset[str]:
    """Who sat at the table when this change ended its hand; nobody when it ended none."""
    if not hand_runs(before) or hand_runs(after):
        return frozenset()
    return frozenset(chair.occupant.account_id for chair in after.chairs if chair.occupant is not None)


def dealt(table: TableRecord, new_hand: NewHand, *, version: int) -> TableRecord:
    """The table with a new hand: its dealer, its cards, an empty auction and no chair ready; every deal goes through
    here.
    """
    return TableRecord(
        id=table.id,
        version=version,
        chairs=tuple(replace(chair, ready=False) for chair in table.chairs),
        dealer=new_hand.dealer,
        hand=new_hand.hand,
        progress=HandProgress(),
        game_list=table.game_list,
    )


def hand_was_dealt(table: TableRecord) -> bool:
    """A hand was dealt on the table at some time: the store writes the dealer with the first hand."""
    return table.dealer is not None


def result_pending(table: TableRecord) -> bool:
    """A played game's result stands: no hand runs, a dealer and a list entry exist, and no auction steps are kept.

    A passed-in hand keeps its steps until the next deal, which tells it apart from a played one.
    """
    return not hand_runs(table) and hand_was_dealt(table) and bool(table.game_list) and not table.progress.auction


@overload
def present_at(table: TableRecord, streams: frozenset[str], leases: frozenset[str]) -> frozenset[str]: ...


@overload
def present_at(table: TableRecord, streams: frozenset[str] | None, leases: frozenset[str]) -> frozenset[str] | None: ...


def present_at(table: TableRecord, streams: frozenset[str] | None, leases: frozenset[str]) -> frozenset[str] | None:
    """Who counts as present at the table: whoever holds an open stream, and every occupant with a live lease; a
    lease never counts for anyone who does not sit here. None says the presence cannot tell any more.
    """
    if streams is None:
        return None
    occupants = {chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}
    return streams | (leases & occupants)


def ends_empty(table: TableRecord, connected_accounts: frozenset[str] | None) -> bool:
    """A table ends for being empty only while no hand was dealt on it and nobody is connected; a table with a dealer
    pauses and is kept. None says the presence cannot tell any more.
    """
    return not hand_was_dealt(table) and connected_accounts is not None and not connected_accounts


def next_deal_due(table: TableRecord, connected_accounts: frozenset[str]) -> bool:
    """The next hand is due when no hand runs, the table has a dealer and all three occupants are connected; while a
    result is pending, all three chairs must be ready too.
    """
    occupants = [chair.occupant.account_id for chair in table.chairs if chair.occupant is not None]
    return (
        not hand_runs(table)
        and hand_was_dealt(table)
        and len(occupants) == CHAIRS_PER_TABLE
        and connected_accounts.issuperset(occupants)
        and (not result_pending(table) or all(chair.ready for chair in table.chairs))
    )


def dealt_next(table: TableRecord, new_hand: NewHand) -> TableRecord:
    """The table with the next hand, which is its own change and so bumps the version itself."""
    return dealt(table, new_hand, version=table.version + 1)


def decide_sit(table: TableRecord, actor: Actor, seat: int, new_hand: NewHand | None) -> Decision:
    """The actor takes a free chair; a taken chair names its holder, and nobody holds two chairs.

    The sit that fills the last chair deals `new_hand` in the same version bump, unless a result is pending; then
    the sitter counts as ready instead.
    """
    if seat_of(table, actor.account_id) is not None:
        return Decision(table, Refusal.ALREADY_SEATED)
    holder = table.chairs[seat - 1].occupant
    if holder is not None:
        return Decision(table, Refusal.SEAT_TAKEN, holder.display_name)
    seated = _with_occupant(table, seat, Occupant(actor.account_id, actor.display_name))
    if new_hand is not None and sit_deals(table):
        seated = dealt(seated, new_hand, version=seated.version)
    return Decision(seated)


def decide_stand(table: TableRecord, actor: Actor) -> Decision:
    """The actor leaves their own chair, which keeps its number; nobody leaves while a hand runs."""
    return decide_free_chair(table, actor.account_id)


def decide_free_chair(table: TableRecord, account_id: str) -> Decision:
    """The account's chair is freed and keeps its number, only while the account still holds it and no hand runs.

    A person standing up and the server ending an away member's hold ask the same question.
    """
    own = seat_of(table, account_id)
    if own is None:
        return Decision(table, Refusal.NOT_SEATED)
    if hand_runs(table):
        return Decision(table, Refusal.HAND_RUNNING)
    return Decision(_with_occupant(table, own.seat, None))


def acting_position(table: TableRecord, actor: Actor, version: int) -> Position | Refusal:
    """The actor's position in the running hand, or why a hand command stops: no hand, no chair, a stale version."""
    if table.dealer is None or not hand_runs(table):
        return Refusal.NO_HAND
    chair = seat_of(table, actor.account_id)
    if chair is None:
        return Refusal.NOT_SEATED
    if version != table.version:
        return Refusal.STALE_VERSION
    return positions_from(table.dealer)[chair.seat]


def card_text(card: Card) -> str:
    """A card as a receipt's payload names it."""
    return f"{card.suit.name}-{card.rank.name}"


def sit_payload(command: SitDown) -> str:
    return f"{command.table_id}:{command.seat}"


def stand_payload(command: StandUp) -> str:
    return command.table_id


def command_receipt(actor: Actor, command_id: str, command: str, payload: str, decision: Decision) -> Receipt:
    return Receipt(actor.account_id, command_id, command, payload, decision.table.id, decision.refusal, decision.holder)


def replayed_decision(replay: Replay, command: str, payload: str) -> Decision:
    """The outcome a command already had; any other request under its key is refused."""
    first = _replayed(replay, command, payload)
    # Only a create receipt outlives a table's end, and `_replayed` refused every other command.
    assert isinstance(first.table, TableRecord)  # noqa: S101 - narrows the type for a table the end rules out
    return Decision(first.table, first.refusal, first.holder)
