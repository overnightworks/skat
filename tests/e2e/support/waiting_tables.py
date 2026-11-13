import itertools
import json
from typing import TYPE_CHECKING

from skat.web.tables import TABLE_SIT_SUFFIX, TABLES_PATH
from tests.e2e.support.raw_http import RawSession
from tests.support.signed_in import new_account, seed_member

if TYPE_CHECKING:
    from tests.e2e.support.server import RunningServer

# Each deal gives the first turn to a seat by lot, so a table is dealt again until the turn is the person's.
ATTEMPTS = 40
command_numbers = itertools.count(1)


def a_member_of(server: RunningServer) -> RawSession:
    return RawSession(
        server, seed_member(server.stores, server.config, account=new_account(server.stores, server.config))
    )


def _command_id() -> str:
    return f"waiting-{next(command_numbers):06d}"


def deal_a_table_that_waits_for(server: RunningServer, him: RawSession) -> str:
    """The id of a dealt table whose first turn is his, opened and filled through the API by two other members."""
    opener, other = a_member_of(server), a_member_of(server)
    for _ in range(ATTEMPTS):
        table_id = json.loads(opener.post(TABLES_PATH, {"command_id": _command_id(), "series_length": 36}))["id"]
        sit_path = f"{TABLES_PATH}/{table_id}{TABLE_SIT_SUFFIX}"
        other.post(sit_path, {"command_id": _command_id(), "seat": 2})
        him.post(sit_path, {"command_id": _command_id(), "seat": 3})
        auction = json.loads(him.get(f"{TABLES_PATH}/{table_id}"))["hand"]["auction"]
        if auction["turn_seat"] == 3:
            return table_id
    message = f"no table of {ATTEMPTS} gave the first turn to the person"
    raise AssertionError(message)
