from dataclasses import replace
from typing import Final

from skat.table.records import (
    Actor,
    Chair,
    CreateTable,
    Decision,
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
    return TableRecord(
        id=table.id,
        version=table.version + 1,
        chairs=tuple(replace(chair, occupant=occupant) if chair.seat == seat else chair for chair in table.chairs),
    )


def decide_sit(table: TableRecord, actor: Actor, seat: int) -> Decision:
    """The actor takes a free chair; a taken chair names its holder, and nobody holds two chairs."""
    if _seat_of(table, actor.account_id) is not None:
        return Decision(table, Refusal.ALREADY_SEATED)
    holder = table.chairs[seat - 1].occupant
    if holder is not None:
        return Decision(table, Refusal.SEAT_TAKEN, holder.display_name)
    return Decision(_with_occupant(table, seat, Occupant(actor.account_id, actor.display_name)))


def decide_stand(table: TableRecord, actor: Actor) -> Decision:
    """The actor leaves their own chair, which keeps its number."""
    own = _seat_of(table, actor.account_id)
    if own is None:
        return Decision(table, Refusal.NOT_SEATED)
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
