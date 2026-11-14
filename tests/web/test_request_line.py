import logline
import pytest
import structlog.testing
from fastapi.testclient import TestClient
from webauth.config import installed_web_auth_config

from skat.host.app import create_app
from skat.web.constants import ACCOUNT_PATH, APP_ASSET_PATH, LOGIN_PATH
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import in_memory_tables
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import IMMUTABLE_FILE, fixture_page_build
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member

PROXY_ADDRESS = "203.0.113.9"
FORWARDED_CLIENT = "198.51.100.7"


@pytest.fixture
def stores():
    return in_memory_stores()


@pytest.fixture
def app(sign_in_settings, stores):
    return create_app(
        sign_in_settings(trusted_proxies=PROXY_ADDRESS).settings,
        page_build=fixture_page_build(),
        tables=in_memory_tables(),
        rule_sets=in_memory_rule_sets(),
        stores=stores,
    )


@pytest.fixture
def browser(app):
    return TestClient(
        app,
        base_url=TEST_PUBLIC_ORIGIN,
        client=(PROXY_ADDRESS, 50000),
        headers={"x-forwarded-for": FORWARDED_CLIENT, "accept": "application/json"},
    )


def request_lines_of(logs):
    return [log for log in logs if log["event"] == logline.REQUEST_EVENT]


class TestRequestLine:
    def test_names_the_signed_in_person_and_the_client_behind_the_trusted_proxy(self, app, stores, browser):
        member = seed_member(stores, installed_web_auth_config(app))

        with structlog.testing.capture_logs() as logs:
            browser.get(ACCOUNT_PATH, headers={"cookie": cookie_header(member.set_cookie_headers)})

        (line,) = request_lines_of(logs)
        assert (line["sub"], line["ip"], line["status"]) == (member.account.id, FORWARDED_CLIENT, 200)

    @pytest.mark.parametrize("path", [ACCOUNT_PATH, LOGIN_PATH])
    def test_names_no_person_for_a_request_without_a_session_and_still_names_the_client(self, browser, path):
        with structlog.testing.capture_logs() as logs:
            browser.get(path)

        (line,) = request_lines_of(logs)
        assert (line["sub"], line["ip"]) == (None, FORWARDED_CLIENT)

    def test_names_the_asset_mount_pattern_as_the_route_never_the_asset_path(self, browser):
        with structlog.testing.capture_logs() as logs:
            answer = browser.get(IMMUTABLE_FILE)

        (line,) = request_lines_of(logs)
        assert (answer.status_code, line["route"]) == (200, APP_ASSET_PATH)
