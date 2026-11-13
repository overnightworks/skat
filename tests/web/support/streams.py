import asyncio
from concurrent.futures import ThreadPoolExecutor

from skat.table.records import Actor
from skat.web.streams import SourceMessage, TableSource, stream_messages
from skat.web.tables import TableAnswer

OPENER = Actor(account_id="opener", display_name="Anna")
VISITOR = Actor(account_id="visitor", display_name="Ben")
ALLOWED_SECONDS = 2
NO_HEARTBEAT_SECONDS = 3600
SHORT_HEARTBEAT_SECONDS = 0.01


def reader(service, table_id):
    async def read_view(actor, connected):
        return service.view(actor, table_id, connected)

    return read_view


def admitting(actor):
    async def admitted():
        return actor

    return admitted


def stream_of(
    presence,
    service,
    actor,
    table_id,
    admit=None,
    heartbeat_seconds=NO_HEARTBEAT_SECONDS,
    read_view=None,
    more_sources=(),
):
    table = TableSource(presence, read_view or reader(service, table_id), table_id, actor.account_id)
    return stream_messages(
        [table, *more_sources], admit or admitting(actor), lambda: presence.stopped, heartbeat_seconds=heartbeat_seconds
    )


def run_on_a_loop_of_its_own(scenario):
    """A thread of its own keeps the loop apart from one that a browser driver left running in this one."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, scenario).result()


async def next_view(stream):
    """The next view; the idle heartbeats before it send no view and are passed over."""
    async with asyncio.timeout(ALLOWED_SECONDS):
        while True:
            item = await anext(stream)
            if isinstance(item, SourceMessage):
                return TableAnswer.model_validate_json(item.data)


async def next_item(stream):
    """The next item of the stream, a view or a heartbeat marker, within the allowed time."""
    async with asyncio.timeout(ALLOWED_SECONDS):
        return await anext(stream)


class Admission:
    """An admission that answers from a script: True admits `actor`, False refuses, an exception is raised."""

    def __init__(self, *answers, then=True, actor=OPENER):
        self.answers = list(answers)
        self.then = then
        self.actor = actor
        self.asked = 0

    async def __call__(self):
        self.asked += 1
        answer = self.answers.pop(0) if self.answers else self.then
        if isinstance(answer, Exception):
            raise answer
        return self.actor if answer else None
