import asyncio
import itertools
import secrets
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import structlog
from fastapi.testclient import TestClient
from starlette.requests import Request
from structlog.testing import capture_logs
from webauth.config import WebAuthConfig, install_web_auth_config, installed_web_auth_config
from webauth.dependencies import session_id_from_request

from skat.host.app import UNPLAYED_SWEEP_SECONDS, create_app
from skat.table.records import Actor, CloseTable, CreateTable, EndReason, SitDown, TableId
from skat.table.service import TableService
from skat.web.constants import ACCOUNT_PATH, AUTH_CALLBACK_PATH, AUTH_START_PATH, LOGIN_GROUP
from skat.web.paused import PAUSED_TABLES_PATH
from skat.web.secret_files import StartRefusedError
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from tests.support.fake_issuer import FakeIssuer
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import FakeTableStore, in_memory_tables
from tests.support.idle_presence import IdleScheduler
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import (
    CALL_PAGE_SCRIPT_HASHES,
    FIXTURE_SCRIPT_HASH,
    SIGN_IN_STYLESHEET,
    fixture_page_build,
)
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member

if TYPE_CHECKING:
    from skat.web.settings import ServerSettings

OPENER = Actor(account_id="account-anna", display_name="Anna")
VISITOR = Actor(account_id="account-ben", display_name="Ben")
THIRD = Actor(account_id="account-cleo", display_name="Cleo")


def signed_in_client(settings: ServerSettings) -> TestClient:
    stores = in_memory_stores()
    app = create_app(
        settings,
        page_build=fixture_page_build(),
        tables=in_memory_tables(),
        rule_sets=in_memory_rule_sets(),
        stores=stores,
    )
    member = seed_member(stores, installed_web_auth_config(app))
    headers = {"cookie": cookie_header(member.set_cookie_headers)}
    return TestClient(app, base_url=TEST_PUBLIC_ORIGIN, headers=headers, follow_redirects=False)


def sign_in_through_issuer(browser: TestClient, issuer: FakeIssuer) -> None:
    start = browser.get(AUTH_START_PATH)
    query = issuer.authorize(start.headers["location"], subject="subject", groups=[LOGIN_GROUP], username="alice")
    browser.get(f"{AUTH_CALLBACK_PATH}?{query}")


def directives(response) -> dict[str, str]:
    policy = response.headers["content-security-policy"]
    return dict(directive.strip().partition(" ")[::2] for directive in policy.split(";") if directive.strip())


class FreeingSignal(TableService):
    """A table service that tells when a chair was freed."""

    def __init__(self, store: FakeTableStore) -> None:
        super().__init__(store)
        self.chair_freed = threading.Event()

    def free_chair(self, table_id, account_id, due):
        freed = super().free_chair(table_id, account_id, due)
        if freed:
            self.chair_freed.set()
        return freed


class EndingSignal(TableService):
    """A table service that tells when a table was ended, and can hold an end inside its transaction."""

    def __init__(self, store: FakeTableStore) -> None:
        super().__init__(store)
        self.table_ended = threading.Event()
        self.end_checked = threading.Event()
        self.end_entered = threading.Event()
        self.release_end = threading.Event()

    def end_empty_table(self, table_id, connected_accounts, empty_seconds):
        @contextmanager
        def held_inside_the_end():
            with connected_accounts as connected:
                self.end_entered.set()
                assert self.release_end.wait(timeout=10)
                yield connected

        ended = super().end_empty_table(table_id, held_inside_the_end(), empty_seconds)
        if ended:
            self.table_ended.set()
        self.end_checked.set()
        return ended


class TestCreateApp:
    def test_a_chair_seated_when_the_server_starts_turns_free_after_the_hold_when_nobody_connects(
        self, sign_in_settings
    ):
        tables = FreeingSignal(FakeTableStore())
        tables.create(Actor(account_id="account-anna", display_name="Anna"), CreateTable(command_id="command-open"))
        settings = sign_in_settings().settings.model_copy(update={"chair_hold_seconds": 0.05})
        app = create_app(
            settings,
            page_build=fixture_page_build(),
            tables=tables,
            rule_sets=in_memory_rule_sets(),
            stores=in_memory_stores(),
        )

        with TestClient(app):
            assert tables.chair_freed.wait(timeout=10)

        assert tables.occupied_chairs() == ()

    def test_a_table_read_live_when_the_server_starts_ends_after_the_wait_when_nobody_connects(self, sign_in_settings):
        tables = EndingSignal(FakeTableStore())
        tables.release_end.set()
        opened = tables.create(OPENER, CreateTable(command_id="command-open"))
        settings = sign_in_settings(empty_table_seconds=1).settings
        app = create_app(
            settings,
            page_build=fixture_page_build(),
            tables=tables,
            rule_sets=in_memory_rule_sets(),
            stores=in_memory_stores(),
        )

        with TestClient(app):
            assert tables.table_ended.wait(timeout=10)

        assert tables.view(OPENER, opened.id, frozenset()).ended.empty_seconds == 1

    def test_a_table_already_past_its_wait_when_the_server_starts_has_ended_before_the_first_request(
        self, sign_in_settings
    ):
        store = FakeTableStore()
        tables = TableService(store)
        opened = tables.create(OPENER, CreateTable(command_id="command-open"))
        store.empty_since_by_table[opened.id] = datetime(2026, 1, 1, tzinfo=UTC)
        settings = sign_in_settings(empty_table_seconds=1800).settings
        stores = in_memory_stores()
        app = create_app(
            settings,
            page_build=fixture_page_build(),
            tables=tables,
            rule_sets=in_memory_rule_sets(),
            stores=stores,
            chair_scheduler=IdleScheduler(),
        )
        member = seed_member(stores, installed_web_auth_config(app))
        headers = {"cookie": cookie_header(member.set_cookie_headers), "accept": "application/json"}

        with TestClient(app, base_url=TEST_PUBLIC_ORIGIN, headers=headers) as client:
            answer = client.get(f"{TABLES_PATH}/{opened.id}")

        assert answer.json()["ended"] == {
            "reason": EndReason.EMPTY,
            "empty_seconds": 1800,
            "unplayed_days": None,
            "closed_by_name": None,
        }

    def test_the_paused_table_days_setting_decides_the_end_a_paused_entry_names(self, sign_in_settings):
        dealt_at = datetime(2026, 11, 1, 12, tzinfo=UTC)
        tables = TableService(FakeTableStore(), now=lambda: dealt_at)
        stores = in_memory_stores()
        settings = sign_in_settings(paused_table_days=7).settings
        app = create_app(
            settings,
            page_build=fixture_page_build(),
            tables=tables,
            rule_sets=in_memory_rule_sets(),
            stores=stores,
            chair_scheduler=IdleScheduler(),
        )
        member = seed_member(stores, installed_web_auth_config(app))
        opened = tables.create(Actor(member.account.id, "Anna"), CreateTable(command_id="command-open"))
        for seat, person in ((2, VISITOR), (3, THIRD)):
            tables.sit(person, SitDown(f"command-{seat}", opened.id, seat), frozenset())
        headers = {"cookie": cookie_header(member.set_cookie_headers), "accept": "application/json"}

        with TestClient(app, base_url=TEST_PUBLIC_ORIGIN, headers=headers) as client:
            answer = client.get(PAUSED_TABLES_PATH)

        (entry,) = answer.json()["tables"]
        assert entry["ends_at"] == (dealt_at + timedelta(days=7)).isoformat().replace("+00:00", "Z")

    def test_a_store_failure_when_the_server_starts_fails_the_start(self, sign_in_settings):
        class Unreadable(FakeTableStore):
            def live_empty_since(self):
                raise ConnectionError

        app = create_app(
            sign_in_settings().settings,
            page_build=fixture_page_build(),
            tables=TableService(Unreadable()),
            rule_sets=in_memory_rule_sets(),
            stores=in_memory_stores(),
        )

        with pytest.raises(ConnectionError), TestClient(app):
            pass

    def test_a_dealt_table_is_kept_and_gets_no_wait_when_the_server_starts(self, sign_in_settings):
        store = FakeTableStore()
        tables = EndingSignal(store)
        tables.release_end.set()
        opened = tables.create(OPENER, CreateTable(command_id="command-open"))
        tables.sit(VISITOR, SitDown("command-sit-ben", opened.id, 2), frozenset())
        tables.sit(THIRD, SitDown("command-sit-cleo", opened.id, 3), frozenset())
        store.empty_since_by_table[opened.id] = datetime(2026, 1, 1, tzinfo=UTC)
        settings = sign_in_settings(empty_table_seconds=1).settings
        app = create_app(
            settings,
            page_build=fixture_page_build(),
            tables=tables,
            rule_sets=in_memory_rule_sets(),
            chair_scheduler=IdleScheduler(),
            stores=in_memory_stores(),
        )

        with TestClient(app):
            pass

        assert tables.end_checked.is_set() is False
        assert tables.view(OPENER, opened.id, frozenset()).ended is None

    def test_the_lifespan_returns_only_after_an_end_whose_check_passed_has_committed(self, sign_in_settings):
        tables = EndingSignal(FakeTableStore())
        opened = tables.create(OPENER, CreateTable(command_id="command-open"))
        settings = sign_in_settings(empty_table_seconds=1).settings
        app = create_app(
            settings,
            page_build=fixture_page_build(),
            tables=tables,
            rule_sets=in_memory_rule_sets(),
            stores=in_memory_stores(),
        )
        client = TestClient(app)
        client.__enter__()
        assert tables.end_entered.wait(timeout=10)
        app.state.stop_streams()

        closing = threading.Thread(target=client.__exit__, args=(None, None, None))
        closing.start()
        closing.join(timeout=0.3)
        waited_for_the_end = closing.is_alive()
        tables.release_end.set()
        closing.join(timeout=10)

        ended = tables.view(OPENER, opened.id, frozenset()).ended
        assert (waited_for_the_end, closing.is_alive(), ended is not None) == (True, False, True)

    def test_installs_the_web_auth_config_built_from_its_settings(self, sign_in_settings):
        sign_in = sign_in_settings()
        config = installed_web_auth_config(
            create_app(
                sign_in.settings,
                page_build=fixture_page_build(),
                tables=in_memory_tables(),
                rule_sets=in_memory_rule_sets(),
                stores=in_memory_stores(),
            )
        )
        assert isinstance(config, WebAuthConfig)
        assert config.session_secret.get_secret_value() == sign_in.session_secret

    def test_does_not_start_without_its_sign_in_files(self, sign_in_settings):
        settings = sign_in_settings().settings
        settings.session_secret_file.unlink()
        page_build = fixture_page_build()
        tables = in_memory_tables()
        rule_sets = in_memory_rule_sets()
        with pytest.raises(StartRefusedError, match="session_secret_file"):
            create_app(settings, page_build=page_build, tables=tables, rule_sets=rule_sets, stores=in_memory_stores())

    def test_account_route_reads_the_sessions_the_sign_in_wrote(self, sign_in_settings):
        sign_in = sign_in_settings()
        issuer = FakeIssuer(sign_in)
        app = create_app(
            sign_in.settings,
            page_build=fixture_page_build(),
            tables=in_memory_tables(),
            rule_sets=in_memory_rule_sets(),
            issuer_transports=issuer.transports,
            stores=in_memory_stores(),
        )
        browser = TestClient(app, base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False)
        sign_in_through_issuer(browser, issuer)

        answer = browser.get(ACCOUNT_PATH)

        assert (answer.status_code, answer.json()) == (200, {"name": "alice"})

    def test_signs_members_in_to_the_stores_it_is_given(self, sign_in_settings):
        sign_in = sign_in_settings()
        issuer = FakeIssuer(sign_in)
        stores = in_memory_stores()
        app = create_app(
            sign_in.settings,
            page_build=fixture_page_build(),
            tables=in_memory_tables(),
            rule_sets=in_memory_rule_sets(),
            issuer_transports=issuer.transports,
            stores=stores,
        )
        browser = TestClient(app, base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False)
        sign_in_through_issuer(browser, issuer)
        config = installed_web_auth_config(app)
        cookie = f"{config.session_cookie_name}={browser.cookies[config.session_cookie_name]}"
        request = Request({"type": "http", "headers": [(b"cookie", cookie.encode())]})
        session_id = session_id_from_request(request, config)
        assert session_id is not None
        session = stores.sessions.load(session_id)
        assert session is not None
        assert session.user.id == "subject"

    @pytest.mark.parametrize("path", ["/", SIGN_IN_STYLESHEET])
    def test_serves_the_page_and_its_assets_to_a_member(self, sign_in_settings, path):
        assert signed_in_client(sign_in_settings().settings).get(path).status_code == 200

    @pytest.mark.parametrize("path", [f"{TABLE_PAGE_PREFIX}table-1%0A", f"{TABLES_PATH}/table-1%0A"])
    def test_a_path_with_a_control_character_answers_400_through_the_app(self, sign_in_settings, path):
        response = signed_in_client(sign_in_settings().settings).get(path)

        assert response.status_code == 400
        assert response.json() == {"detail": "Malformed request path"}

    def test_the_policy_admits_the_scripts_of_the_shell_and_of_every_languages_call_sign_in_page_by_their_hash(
        self, sign_in_settings
    ):
        response = signed_in_client(sign_in_settings().settings).get("/health")

        assert (
            f"script-src 'self' '{FIXTURE_SCRIPT_HASH}' '{CALL_PAGE_SCRIPT_HASHES['de']}' "
            f"'{CALL_PAGE_SCRIPT_HASHES['en']}';" in response.headers["content-security-policy"]
        )

    def test_the_policy_refuses_all_framing_while_no_call_origin_is_set(self, sign_in_settings):
        policy = directives(signed_in_client(sign_in_settings().settings).get("/health"))

        assert policy["frame-ancestors"] == "'none'"

    def test_the_policy_admits_the_call_origin_as_the_only_frame_ancestor_and_changes_nothing_else(
        self, sign_in_settings
    ):
        origin = "https://call.test.invalid:8443"
        unset = directives(signed_in_client(sign_in_settings().settings).get("/health"))
        configured = directives(signed_in_client(sign_in_settings(call_origin=origin).settings).get("/health"))

        assert configured.pop("frame-ancestors") == origin
        unset.pop("frame-ancestors")
        assert configured == unset

    @pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
    def test_generated_documentation_is_not_served(self, sign_in_settings, path):
        assert signed_in_client(sign_in_settings().settings).get(path).status_code == 404


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


class TestLoggedExceptions:
    def test_rendered_traceback_leaves_out_the_values_of_local_variables(self, sign_in_settings, capsys):
        create_app(
            sign_in_settings().settings,
            page_build=fixture_page_build(),
            tables=in_memory_tables(),
            rule_sets=in_memory_rule_sets(),
            stores=in_memory_stores(),
        )
        sentinel = secrets.token_urlsafe(16)

        def fail_holding_the_sentinel():
            held_secret = sentinel
            raise ValueError(len(held_secret))

        try:
            fail_holding_the_sentinel()
        except ValueError:
            structlog.get_logger().exception("failed")

        rendered = capsys.readouterr().out
        assert "ValueError" in rendered
        assert sentinel not in rendered


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


def failing_with(message):
    def fail(_now):
        raise ConnectionError(message)

    return fail


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

    def test_whose_deletion_fails_in_an_hourly_run_are_logged_by_type_and_the_run_still_ends_tables(
        self, unplayed, app
    ):
        table_id = unplayed.dealt("command-open")
        with TestClient(app) as client:
            ((_, tick),) = unplayed.scheduler.sweeps()
            unplayed.play_on(UNPLAYED_DAYS)
            unplayed.stores.sessions.delete_expired = failing_with("account-anna")
            with capture_logs() as logs:
                client.portal.call(tick)

        assert unplayed.ended(table_id).reason is EndReason.UNPLAYED
        assert [entry["error"] for entry in logs] == ["ConnectionError"]
        assert "account-anna" not in str(logs)
