import secrets
from typing import TYPE_CHECKING

import pytest
import structlog
from fastapi.testclient import TestClient
from starlette.requests import Request
from webauth.config import WebAuthConfig, installed_web_auth_config
from webauth.dependencies import session_id_from_request

from skat.host.app import create_app
from skat.web.constants import ACCOUNT_PATH, AUTH_CALLBACK_PATH, AUTH_START_PATH, LOGIN_GROUP
from skat.web.secret_files import StartRefusedError
from skat.web.stores import SignInStores
from tests.support.fake_issuer import FakeIssuer
from tests.support.page_build import FIXTURE_SCRIPT_HASH, SIGN_IN_STYLESHEET, fixture_page_build
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member

if TYPE_CHECKING:
    from skat.web.settings import ServerSettings

SESSION_COOKIE = "__Host-session_id"


def signed_in_client(settings: ServerSettings) -> TestClient:
    stores = SignInStores.in_memory()
    app = create_app(settings, page_build=fixture_page_build(), stores=stores)
    member = seed_member(stores, installed_web_auth_config(app))
    headers = {"cookie": cookie_header(member.set_cookie_headers)}
    return TestClient(app, base_url=TEST_PUBLIC_ORIGIN, headers=headers, follow_redirects=False)


def sign_in_through_issuer(browser: TestClient, issuer: FakeIssuer) -> None:
    start = browser.get(AUTH_START_PATH)
    query = issuer.authorize(start.headers["location"], subject="subject", groups=[LOGIN_GROUP], username="alice")
    browser.get(f"{AUTH_CALLBACK_PATH}?{query}")


class TestCreateApp:
    def test_installs_the_web_auth_config_built_from_its_settings(self, sign_in_settings):
        sign_in = sign_in_settings()
        config = installed_web_auth_config(create_app(sign_in.settings, page_build=fixture_page_build()))
        assert isinstance(config, WebAuthConfig)
        assert config.session_secret.get_secret_value() == sign_in.session_secret

    def test_does_not_start_without_its_sign_in_files(self, sign_in_settings):
        settings = sign_in_settings().settings
        settings.session_secret_file.unlink()
        page_build = fixture_page_build()
        with pytest.raises(StartRefusedError, match="session_secret_file"):
            create_app(settings, page_build=page_build)

    def test_account_route_reads_the_sessions_the_sign_in_wrote(self, sign_in_settings):
        sign_in = sign_in_settings()
        issuer = FakeIssuer(sign_in)
        app = create_app(sign_in.settings, page_build=fixture_page_build(), issuer_transports=issuer.transports)
        browser = TestClient(app, base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False)
        sign_in_through_issuer(browser, issuer)

        answer = browser.get(ACCOUNT_PATH)

        assert (answer.status_code, answer.json()) == (200, {"name": "alice"})

    def test_signs_members_in_to_the_stores_it_is_given(self, sign_in_settings):
        sign_in = sign_in_settings()
        issuer = FakeIssuer(sign_in)
        stores = SignInStores.in_memory()
        app = create_app(
            sign_in.settings, page_build=fixture_page_build(), issuer_transports=issuer.transports, stores=stores
        )
        browser = TestClient(app, base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False)
        sign_in_through_issuer(browser, issuer)
        cookie = f"{SESSION_COOKIE}={browser.cookies[SESSION_COOKIE]}"
        session_id = session_id_from_request(
            Request({"type": "http", "headers": [(b"cookie", cookie.encode())]}), installed_web_auth_config(app)
        )
        assert session_id is not None
        session = stores.sessions.load(session_id)
        assert session is not None
        assert session.user.id == "subject"

    @pytest.mark.parametrize("path", ["/", SIGN_IN_STYLESHEET])
    def test_serves_the_page_and_its_assets_to_a_member(self, sign_in_settings, path):
        assert signed_in_client(sign_in_settings().settings).get(path).status_code == 200

    def test_the_policy_admits_the_scripts_of_the_shell_by_their_hash(self, sign_in_settings):
        response = signed_in_client(sign_in_settings().settings).get("/health")

        assert f"script-src 'self' '{FIXTURE_SCRIPT_HASH}';" in response.headers["content-security-policy"]

    @pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
    def test_generated_documentation_is_not_served(self, sign_in_settings, path):
        assert signed_in_client(sign_in_settings().settings).get(path).status_code == 404


class TestLoggedExceptions:
    def test_rendered_traceback_leaves_out_the_values_of_local_variables(self, sign_in_settings, capsys):
        create_app(sign_in_settings().settings, page_build=fixture_page_build())
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
