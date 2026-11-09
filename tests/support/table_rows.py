import time
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from skat.store.schema import metadata, tables
from tests.support.faulty_tables import HANG_DEADLINE_SECONDS

if TYPE_CHECKING:
    import threading


def rows_of(engine, table_id: str) -> dict[str, list[tuple[object, ...]]]:
    """Every row of the store that belongs to the table, in every store table."""
    with engine.connect() as connection:
        return {
            each.name: [
                tuple(row)
                for row in connection.execute(
                    select(each)
                    .where((each.c.id if each is tables else each.c.table_id) == table_id)
                    .order_by(*each.primary_key.columns)
                )
            ]
            for each in metadata.sorted_tables
        }


def wait_until_a_session_waits_for_a_lock(engine, reader: threading.Thread) -> None:
    """Returns when a session waits for a lock; fails when the reader ends without that, or hangs elsewhere."""
    hang_deadline = time.monotonic() + HANG_DEADLINE_SECONDS
    with engine.connect() as watcher:
        while reader.is_alive() and time.monotonic() < hang_deadline:
            waiting = watcher.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            ).scalar_one()
            if waiting:
                return
    pytest.fail("no session waited for a lock")
