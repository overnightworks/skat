import pytest
from fastapi.testclient import TestClient
from webauth.config import installed_web_auth_config

from skat.web.constants import ACCOUNT_CONSOLE_PATH, ACCOUNT_PATH
from tests.support.in_memory_stores import in_memory_stores
from tests.support.sign_in_settings import TEST_ISSUER, TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member
from tests.web.support.skat import skat_app


@pytest.fixture
def stores():
    return in_memory_stores()


app = pytest.fixture(name="app")(skat_app)


@pytest.fixture
def browser(app):
    return TestClient(app, base_url=TEST_PUBLIC_ORIGIN)


class TestAccountRoute:
    def test_answers_a_signed_in_member_with_exactly_their_username(self, app, stores, browser):
        member = seed_member(stores, installed_web_auth_config(app))

        answer = browser.get(ACCOUNT_PATH, headers={"cookie": cookie_header(member.set_cookie_headers)})

        assert (answer.status_code, answer.json()) == (200, {"name": member.account.username})

    def test_lets_no_cache_keep_the_answer(self, app, stores, browser):
        member = seed_member(stores, installed_web_auth_config(app))

        answer = browser.get(ACCOUNT_PATH, headers={"cookie": cookie_header(member.set_cookie_headers)})

        assert answer.headers["cache-control"] == "no-store"

    @pytest.mark.parametrize("session", ["absent", "ended"])
    def test_refuses_a_request_without_a_live_session_and_names_nobody(self, app, stores, browser, session):
        member = seed_member(stores, installed_web_auth_config(app))
        headers = {"accept": "application/json"}
        if session == "ended":
            stores.sessions.delete(member.session.id)
            headers["cookie"] = cookie_header(member.set_cookie_headers)

        answer = browser.get(ACCOUNT_PATH, headers=headers)

        assert answer.status_code == 401
        assert member.account.username not in answer.text


class TestAccountConsoleRoute:
    @pytest.mark.parametrize("method", ["GET", "HEAD"])
    def test_sends_a_signed_in_member_to_the_issuers_account_console(self, app, stores, browser, method):
        member = seed_member(stores, installed_web_auth_config(app))

        answer = browser.request(
            method,
            ACCOUNT_CONSOLE_PATH,
            params={"next": "https://example.org"},
            headers={"cookie": cookie_header(member.set_cookie_headers)},
            follow_redirects=False,
        )

        assert (answer.status_code, answer.headers["location"]) == (303, f"{TEST_ISSUER}/account")
