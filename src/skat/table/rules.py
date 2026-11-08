from dataclasses import replace
from typing import Final

from skat.table.records import (
    Actor,
    Chair,
    CreateTable,
    Decision,
    FirstDeal,
    Occupant,
    Receipt,
    Refusal,
    Replay,
    SitDown,
    StandUp,
    TableId,
    TableRecord,
)

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
    )


def create_receipt(actor: Actor, command: CreateTable, table: TableRecord) -> Receipt:
    return Receipt(actor.account_id, command.command_id, CREATE_TABLE_COMMAND, CREATE_TABLE_PAYLOAD, table.id)


def replayed_table(replay: Replay) -> TableRecord:
    """The table a create request already made; any other request under its key is refused."""
    return _replayed(replay, CREATE_TABLE_COMMAND, CREATE_TABLE_PAYLOAD).table


def _replayed(replay: Replay, command: str, payload: str) -> Replay:
    if (replay.command, replay.payload) != (command, payload):
        raise CommandIdReusedError
    return replay


def _seat_of(table: TableRecord, account_id: str) -> Chair | None:
    return next((chair for chair in table.chairs if chair.occupant and chair.occupant.account_id == account_id), None)


def _with_occupant(table: TableRecord, seat: int, occupant: Occupant | None) -> TableRecord:
    chairs = tuple(Chair(seat, occupant) if chair.seat == seat else chair for chair in table.chairs)
    return TableRecord(id=table.id, version=table.version + 1, chairs=chairs, dealer=table.dealer, hand=table.hand)


def sit_deals(table: TableRecord) -> bool:
    """A sit deals when it fills the last free chair and no hand runs."""
    free_chairs = sum(chair.occupant is None for chair in table.chairs)
    return free_chairs == 1 and not hand_runs(table)


def hand_runs(table: TableRecord) -> bool:
    return table.hand is not None


def decide_sit(table: TableRecord, actor: Actor, seat: int, first_deal: FirstDeal | None) -> Decision:
    """The actor takes a free chair; a taken chair names its holder, and nobody holds two chairs.

    The sit that fills the last chair stores the drawn `first_deal` in the same version bump.
    """
    if _seat_of(table, actor.account_id) is not None:
        return Decision(table, Refusal.ALREADY_SEATED)
    holder = table.chairs[seat - 1].occupant
    if holder is not None:
        return Decision(table, Refusal.SEAT_TAKEN, holder.display_name)
    seated = _with_occupant(table, seat, Occupant(actor.account_id, actor.display_name))
    if first_deal is not None and sit_deals(table):
        seated = replace(seated, dealer=first_deal.dealer, hand=first_deal.hand)
    return Decision(seated)


def decide_stand(table: TableRecord, actor: Actor) -> Decision:
    """The actor leaves their own chair, which keeps its number; nobody leaves while a hand runs."""
    return decide_free_chair(table, actor.account_id)


def decide_free_chair(table: TableRecord, account_id: str) -> Decision:
    """The account's chair is freed and keeps its number, only while the account still holds it and no hand runs.

    A person standing up and the server ending an away member's hold ask the same question.
    """
    own = _seat_of(table, account_id)
    if own is None:
        return Decision(table, Refusal.NOT_SEATED)
    if hand_runs(table):
        return Decision(table, Refusal.HAND_RUNNING)
    return Decision(_with_occupant(table, own.seat, None))


def sit_payload(command: SitDown) -> str:
    return f"{command.table_id}:{command.seat}"


def stand_payload(command: StandUp) -> str:
    return command.table_id


def seating_receipt(actor: Actor, command_id: str, command: str, payload: str, decision: Decision) -> Receipt:
    return Receipt(actor.account_id, command_id, command, payload, decision.table.id, decision.refusal, decision.holder)


def replayed_decision(replay: Replay, command: str, payload: str) -> Decision:
    """The outcome a seating request already had; any other request under its key is refused."""
    first = _replayed(replay, command, payload)
    return Decision(first.table, first.refusal, first.holder)
