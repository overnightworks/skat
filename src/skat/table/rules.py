from typing import Final

from skat.table.records import Actor, Chair, CreateTable, Occupant, Receipt, Replay, TableId, TableRecord

CHAIRS_PER_TABLE: Final = 3
FIRST_VERSION: Final = 1
CREATE_TABLE_COMMAND: Final = "create-table"
CREATE_TABLE_PAYLOAD: Final = "{}"


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
    if (replay.command, replay.payload) != (CREATE_TABLE_COMMAND, CREATE_TABLE_PAYLOAD):
        raise CommandIdReusedError
    return replay.table
