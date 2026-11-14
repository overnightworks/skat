import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from webauth.config import WebAuthConfig, installed_web_auth_config
from webauth.dependencies import session_id_from_request

from skat.host.app import create_app
from skat.table.records import Actor, CreateTable, EndReason, SitDown
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
