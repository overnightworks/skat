import asyncio
from concurrent.futures import ThreadPoolExecutor

from skat.table.records import Actor
from skat.web.streams import table_views

OPENER = Actor(account_id="opener", display_name="Anna")
VISITOR = Actor(account_id="visitor", display_name="Ben")
ALLOWED_SECONDS = 2
NO_HEARTBEAT_SECONDS = 3600


def reader(service, table_id):
    async def read_view(actor, connected):
        return service.view(actor, table_id, connected)

    return read_view


def admitting(actor):
    async def admitted():
        return actor

    return admitted


def stream_of(presence, service, actor, table_id, admit=None, heartbeat_seconds=NO_HEARTBEAT_SECONDS):
    return table_views(
        presence,
        reader(service, table_id),
        admit or admitting(actor),
        table_id,
        actor.account_id,
        heartbeat_seconds=heartbeat_seconds,
    )


def run_on_a_loop_of_its_own(scenario):
    """A thread of its own keeps the loop apart from one that a browser driver left running in this one."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, scenario).result()


async def next_view(stream):
    return await asyncio.wait_for(anext(stream), ALLOWED_SECONDS)
