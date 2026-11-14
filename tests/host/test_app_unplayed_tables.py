import asyncio
import itertools
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs
from webauth.config import install_web_auth_config, installed_web_auth_config

from skat.host.app import UNPLAYED_SWEEP_SECONDS, create_app
from skat.table.records import Actor, CloseTable, CreateTable, EndReason, SitDown, TableId
from skat.table.service import TableService
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import FakeTableStore
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import (
    fixture_page_build,
)
from tests.support.signed_in import seed_member

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


@pytest.fixture
def unplayed(sign_in_settings):
    return UnplayedTables(sign_in_settings)


class TestUnplayedTables:
    @pytest.mark.parametrize(
        ("seconds_past_the_end", "ends"),
        [pytest.param(-1, False, id="a-second-before-the-end"), pytest.param(0, True, id="exactly-at-the-end")],
    )
    def test_a_table_past_its_days_when_the_server_starts_has_ended_before_the_first_request(
        self, unplayed, seconds_past_the_end, ends
    ):
        table_id = unplayed.dealt("command-open")
        unplayed.play_on(UNPLAYED_DAYS, seconds_past_the_end)

        with TestClient(unplayed.app()):
            ended = unplayed.ended(table_id)

        assert (ended is not None) is ends
        if ends:
            assert (ended.reason, ended.empty_seconds, ended.unplayed_days) == (EndReason.UNPLAYED, None, UNPLAYED_DAYS)

    def test_a_table_that_crosses_the_line_while_the_server_runs_ends_with_the_next_hourly_run(self, unplayed):
        table_id = unplayed.dealt("command-open")
        with TestClient(unplayed.app()) as client:
            ((delay, tick),) = unplayed.scheduler.sweeps()
            unplayed.play_on(UNPLAYED_DAYS - 1)
            client.portal.call(tick)
            before_the_line = unplayed.ended(table_id)
            unplayed.play_on(UNPLAYED_DAYS)
            client.portal.call(tick)
            after_the_line = unplayed.ended(table_id)
            runs_asked_for = len(unplayed.scheduler.sweeps())

        assert delay == UNPLAYED_SWEEP_SECONDS
        assert before_the_line is None
        assert after_the_line.reason is EndReason.UNPLAYED
        assert runs_asked_for == 3

    def test_a_table_that_fails_at_the_start_fails_the_start(self, sign_in_settings):
        class Failing(TableService):
            def end_unplayed_table(self, table_id, days, writing):
                raise ConnectionError

        unplayed = UnplayedTables(sign_in_settings, Failing)
        unplayed.dealt("command-open")
        unplayed.play_on(UNPLAYED_DAYS)

        with pytest.raises(ConnectionError), TestClient(unplayed.app()):
            pass

    def test_a_table_that_fails_in_an_hourly_run_leaves_the_others_ending_and_is_tried_again(self, sign_in_settings):
        class FailingOnce(TableService):
            failing = None

            def end_unplayed_table(self, table_id, days, writing):
                if table_id == self.failing:
                    type(self).failing = None
                    raise ConnectionError("account-anna")
                return super().end_unplayed_table(table_id, days, writing)

        unplayed = UnplayedTables(sign_in_settings, FailingOnce)
        first, second = unplayed.dealt("command-first"), unplayed.dealt("command-second")
        FailingOnce.failing = first
        with TestClient(unplayed.app()) as client:
            ((_, tick),) = unplayed.scheduler.sweeps()
            unplayed.play_on(UNPLAYED_DAYS)
            with capture_logs() as logs:
                client.portal.call(tick)
            ((_, tick_again),) = unplayed.scheduler.sweeps()[1:]
            failed_one = (unplayed.ended(first), unplayed.ended(second).reason)
            client.portal.call(tick_again)
            retried = unplayed.ended(first).reason

        assert failed_one == (None, EndReason.UNPLAYED)
        assert retried is EndReason.UNPLAYED
        assert [entry["error"] for entry in logs] == ["ConnectionError"]
        assert "account-anna" not in str(logs)

    def test_a_table_read_as_due_that_is_not_due_when_the_row_is_locked_is_left_alone(self, sign_in_settings):
        listed = []

        class ReadsListedTablesAsDue(TableService):
            def unplayed_tables(self, days):
                return tuple(listed)

        unplayed = UnplayedTables(sign_in_settings, ReadsListedTablesAsDue)
        table_id = unplayed.dealt("command-open")
        listed.append(table_id)
        with TestClient(unplayed.app()):
            ended = unplayed.ended(table_id)

        assert ended is None

    def test_a_failed_read_in_an_hourly_run_is_logged_and_the_next_run_still_comes(self, sign_in_settings):
        class UnreadableAfterTheStart(TableService):
            reads = itertools.count(1)

            def unplayed_tables(self, days):
                if next(self.reads) > 1:
                    raise ConnectionError("account-anna")
                return super().unplayed_tables(days)

        unplayed = UnplayedTables(sign_in_settings, UnreadableAfterTheStart)
        with TestClient(unplayed.app()) as client:
            ((_, tick),) = unplayed.scheduler.sweeps()
            with capture_logs() as logs:
                client.portal.call(tick)
            runs_asked_for = len(unplayed.scheduler.sweeps())

        assert [entry["error"] for entry in logs] == ["ConnectionError"]
        assert "account-anna" not in str(logs)
        assert runs_asked_for == 2

    def test_a_run_after_the_server_stopped_ends_no_table(self, unplayed):
        table_id = unplayed.dealt("command-open")
        with TestClient(unplayed.app()):
            ((_, tick),) = unplayed.scheduler.sweeps()
        unplayed.play_on(UNPLAYED_DAYS)

        asyncio.run(tick())

        assert unplayed.ended(table_id) is None

    def test_a_run_that_awaits_the_row_lock_when_the_server_stops_ends_no_table(self, sign_in_settings):
        store = HeldStore()
        unplayed = UnplayedTables(sign_in_settings, store=store)
        table_id = unplayed.dealt("command-open")
        store.holds_the_row = True

        asyncio.run(unplayed.stop_while_held(store.awaiting_the_row, store.row_free, free_during_the_stop=False))

        assert unplayed.ended(table_id) is None

    def test_the_lifespan_returns_only_after_an_unplayed_end_awaiting_its_commit_has_committed(self, sign_in_settings):
        store = HeldStore()
        unplayed = UnplayedTables(sign_in_settings, store=store)
        table_id = unplayed.dealt("command-open")
        store.holds_the_commit = True

        committed_at_return = asyncio.run(
            unplayed.stop_while_held(store.awaiting_the_commit, store.commit_free, free_during_the_stop=True)
        )

        assert committed_at_return
        assert unplayed.ended(table_id).reason is EndReason.UNPLAYED

    def test_a_run_after_the_server_stopped_asks_for_no_further_run(self, unplayed):
        with TestClient(unplayed.app()):
            ((_, tick),) = unplayed.scheduler.sweeps()
            unplayed.scheduler.actions.clear()

        asyncio.run(tick())

        assert unplayed.scheduler.sweeps() == []


class TestEndedTables:
    @pytest.fixture
    def closed(self, unplayed):
        """A table its opener closed at NOW, which has no game in the history."""
        table_id = unplayed.dealt("command-open")
        assert unplayed.tables.close(OPENER, CloseTable("command-close", table_id.value)).refusal is None
        return table_id

    @pytest.mark.parametrize(
        ("seconds_past_the_days", "forgotten"),
        [pytest.param(-1, False, id="a-second-before-the-days"), pytest.param(0, True, id="exactly-at-the-days")],
    )
    def test_a_table_ended_longer_ago_than_the_days_when_the_server_starts_is_gone_before_the_first_request(
        self, unplayed, closed, seconds_past_the_days, forgotten
    ):
        unplayed.play_on(ENDED_DAYS, seconds_past_the_days)

        with TestClient(unplayed.app()):
            view = unplayed.tables.view(OPENER, closed.value, frozenset())

        assert (view is None) is forgotten

    def test_a_table_that_passes_its_days_while_the_server_runs_is_gone_with_the_next_hourly_run(
        self, unplayed, closed
    ):
        with TestClient(unplayed.app()) as client:
            ((_, tick),) = unplayed.scheduler.sweeps()
            unplayed.play_on(ENDED_DAYS - 1)
            client.portal.call(tick)
            before_the_days = unplayed.tables.view(OPENER, closed.value, frozenset())
            unplayed.play_on(ENDED_DAYS)
            client.portal.call(tick)
            after_the_days = unplayed.tables.view(OPENER, closed.value, frozenset())

        assert before_the_days.ended.closed_by_name == OPENER.display_name
        assert after_the_days is None

    def test_a_store_failure_at_the_start_fails_the_start(self, sign_in_settings):
        class Failing(TableService):
            def forget_ended_tables(self, days):
                raise ConnectionError

        unplayed = UnplayedTables(sign_in_settings, Failing)

        with pytest.raises(ConnectionError), TestClient(unplayed.app()):
            pass

    def test_a_store_failure_in_an_hourly_run_is_logged_by_its_type_and_the_next_run_tries_again(
        self, sign_in_settings
    ):
        class FailingOnce(TableService):
            failing = True

            def forget_ended_tables(self, days):
                if type(self).failing:
                    type(self).failing = False
                    raise ConnectionError("account-anna")
                return super().forget_ended_tables(days)

        FailingOnce.failing = False
        unplayed = UnplayedTables(sign_in_settings, FailingOnce)
        table_id = unplayed.dealt("command-open")
        unplayed.tables.close(OPENER, CloseTable("command-close", table_id.value))
        with TestClient(unplayed.app()) as client:
            ((_, tick),) = unplayed.scheduler.sweeps()
            unplayed.play_on(ENDED_DAYS)
            FailingOnce.failing = True
            with capture_logs() as logs:
                client.portal.call(tick)
            ((_, tick_again),) = unplayed.scheduler.sweeps()[1:]
            kept = unplayed.tables.view(OPENER, table_id.value, frozenset())
            client.portal.call(tick_again)
            forgotten = unplayed.tables.view(OPENER, table_id.value, frozenset())

        assert (kept is None, forgotten is None) == (False, True)
        assert [entry["error"] for entry in logs] == ["ConnectionError"]
        assert "account-anna" not in str(logs)


class SessionsThatCanFailToExpire:
    """The sessions of a store whose expiry raises once `failure` is set."""

    def __init__(self, sessions):
        self._sessions = sessions
        self.failure = None

    def delete_expired(self, now):
        if self.failure is not None:
            raise self.failure
        return self._sessions.delete_expired(now)

    def __getattr__(self, name):
        return getattr(self._sessions, name)


class StoresWithSessionsThatCanFailToExpire:
    def __init__(self, stores):
        self.sessions = SessionsThatCanFailToExpire(stores.sessions)
        self.transaction = stores.transaction


class TestExpiredSessions:
    @pytest.fixture
    def now(self):
        return [NOW.timestamp()]

    @pytest.fixture
    def app(self, unplayed, now):
        return unplayed.app_on_a_clock(lambda: now[0])

    def seeded(self, unplayed, app, expires_in):
        return seed_member(unplayed.stores, installed_web_auth_config(app), expires_in=expires_in)

    def test_are_gone_before_the_first_request_and_the_live_ones_stay_when_the_server_starts(self, unplayed, app):
        expired = self.seeded(unplayed, app, timedelta(seconds=-1))
        live = self.seeded(unplayed, app, timedelta(hours=1))

        with TestClient(app):
            kept = [unplayed.stores.sessions.load(member.session.id) is not None for member in (expired, live)]

        assert kept == [False, True]

    def test_that_expire_while_the_server_runs_are_gone_with_the_next_hourly_run(self, unplayed, app, now):
        member = self.seeded(unplayed, app, timedelta(hours=1))

        with TestClient(app) as client:
            ((_, tick),) = unplayed.scheduler.sweeps()
            client.portal.call(tick)
            before_the_expiry = unplayed.stores.sessions.load(member.session.id)
            now[0] += timedelta(hours=1, seconds=1).total_seconds()
            client.portal.call(tick)
            after_the_expiry = unplayed.stores.sessions.load(member.session.id)

        assert (before_the_expiry is not None, after_the_expiry) == (True, None)

    def test_whose_deletion_fails_in_an_hourly_run_are_logged_by_type_and_the_run_still_ends_tables(self, unplayed):
        unplayed.stores = StoresWithSessionsThatCanFailToExpire(unplayed.stores)
        table_id = unplayed.dealt("command-open")
        with TestClient(unplayed.app()) as client:
            ((_, tick),) = unplayed.scheduler.sweeps()
            unplayed.play_on(UNPLAYED_DAYS)
            unplayed.stores.sessions.failure = ConnectionError("account-anna")
            with capture_logs() as logs:
                client.portal.call(tick)

        assert unplayed.ended(table_id).reason is EndReason.UNPLAYED
        assert [entry["error"] for entry in logs] == ["ConnectionError"]
        assert "account-anna" not in str(logs)
