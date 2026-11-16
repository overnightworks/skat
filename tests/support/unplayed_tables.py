import asyncio
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from webauth.config import install_web_auth_config, installed_web_auth_config

from skat.host.app import UNPLAYED_SWEEP_SECONDS, create_app
from skat.table.records import Actor, CreateTable, SitDown, TableId
from skat.table.service import TableService
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import FakeTableStore
from tests.support.in_memory_stores import in_memory_stores, single_pod
from tests.support.page_build import (
    fixture_page_build,
)

OPENER = Actor(account_id="account-anna", display_name="Anna")
VISITOR = Actor(account_id="account-ben", display_name="Ben")
THIRD = Actor(account_id="account-cleo", display_name="Cleo")


class RecordedScheduler:
    """A scheduler that keeps what it is asked to run, for the test to run on the app's loop."""

    def __init__(self):
        self.actions = []

    def schedule(self, delay, action):
        self.actions.append((delay, action))

    def cancel_all(self):
        self.actions.clear()

    def sweeps(self):
        """The runs asked for the hourly end of unplayed tables, each as its delay and action."""
        return [(delay, action) for delay, action in self.actions if delay == UNPLAYED_SWEEP_SECONDS]


UNPLAYED_DAYS = 7
ENDED_DAYS = 3
NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)


class HeldStore(FakeTableStore):
    """A store whose row lock waits for the test and whose commit of an end waits for the test."""

    def __init__(self):
        super().__init__()
        self.holds_the_row = False
        self.holds_the_commit = False
        self.awaiting_the_row = threading.Event()
        self.row_free = threading.Event()
        self.awaiting_the_commit = threading.Event()
        self.commit_free = threading.Event()
        self.committed = threading.Event()
        self._ended = False

    def locked_table(self, table_id):
        if self.holds_the_row:
            self.awaiting_the_row.set()
            assert self.row_free.wait(timeout=10)
        return super().locked_table(table_id)

    def end_table(self, table_id, at, ending):
        self._ended = True
        super().end_table(table_id, at, ending)

    @contextmanager
    def begin(self):
        with super().begin() as transaction:
            yield transaction
            if self.holds_the_commit and self._ended:
                self.awaiting_the_commit.set()
                assert self.commit_free.wait(timeout=10)
        if self._ended:
            self.committed.set()


class UnplayedTables:
    """Dealt tables on a service whose clock the test moves, started by an app on a scheduler the test runs."""

    def __init__(self, sign_in_settings, service=TableService, store=None):
        self.clock = [NOW]
        self.store = FakeTableStore() if store is None else store
        self.tables = service(self.store, now=lambda: self.clock[0])
        self.scheduler = RecordedScheduler()
        self.settings = sign_in_settings(paused_table_days=UNPLAYED_DAYS, ended_table_days=ENDED_DAYS).settings
        self.stores = in_memory_stores()

    def dealt(self, command_id):
        table = self.tables.create(OPENER, CreateTable(command_id=command_id))
        for seat, person in ((2, VISITOR), (3, THIRD)):
            self.tables.sit(person, SitDown(f"{command_id}-{seat}", table.id, seat), frozenset())
        return TableId(table.id)

    def play_on(self, days, seconds=0):
        self.clock[0] = NOW + timedelta(days=days, seconds=seconds)

    def app(self):
        return create_app(
            self.settings,
            page_build=fixture_page_build(),
            tables=self.tables,
            rule_sets=in_memory_rule_sets(),
            chair_scheduler=self.scheduler,
            stores=self.stores,
            **single_pod(),
        )

    def app_on_a_clock(self, wall_clock):
        """The app with webauth reading `wall_clock`, as the sessions' expiry is judged by it."""
        app = self.app()
        install_web_auth_config(app, replace(installed_web_auth_config(app), wall_clock=wall_clock))
        return app

    async def stop_while_held(self, reached, free, *, free_during_the_stop):
        """Serve until the hourly run, started past the days, reaches the hold `reached`, then stop the server.
        The hold `free` is freed once the stop has started when `free_during_the_stop`, else once the lifespan has
        returned. Answers whether the unplayed end had committed when the lifespan returned.
        """
        app = self.app()

        async def serve():
            async with app.router.lifespan_context(app):
                ((_, tick),) = self.scheduler.sweeps()
                self.play_on(UNPLAYED_DAYS)
                running = asyncio.create_task(tick())
                assert await asyncio.to_thread(reached.wait, 10)
                if free_during_the_stop:
                    freeing = asyncio.create_task(self.free_after_a_turn(free))
            committed = self.store.committed.is_set()
            if not free_during_the_stop:
                free.set()
            await running
            if free_during_the_stop:
                await freeing
            return committed

        return await asyncio.wait_for(serve(), timeout=30)

    @staticmethod
    async def free_after_a_turn(free):
        """Frees the hold once the stop is under way: the task first runs when the lifespan exit yields."""
        free.set()

    def ended(self, table_id):
        return self.tables.view(OPENER, table_id.value, frozenset()).ended
