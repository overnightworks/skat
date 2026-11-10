import pytest
from fastapi.testclient import TestClient
from webauth.config import installed_web_auth_config

from skat.host.app import create_app
from skat.web.call import CALL_ORIGIN_PATH
from skat.web.stores import SignInStores
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import in_memory_tables
from tests.support.page_build import fixture_page_build
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member

CALL_ORIGIN = "https://call.test.invalid"


def _client(sign_in_settings, stores, **overrides):
    app = create_app(
        sign_in_settings(**overrides).settings,
        page_build=fixture_page_build(),
        tables=in_memory_tables(),
        rule_sets=in_memory_rule_sets(),
        stores=stores,
    )
    return app, TestClient(app, base_url=TEST_PUBLIC_ORIGIN)


@pytest.fixture
def stores():
    return SignInStores.in_memory()


class TestCallOriginRoute:
    @pytest.mark.parametrize(("configured", "expected"), [(CALL_ORIGIN, CALL_ORIGIN), (None, None)])
    def test_answers_the_configured_origin_and_null_when_unset(self, sign_in_settings, stores, configured, expected):
        app, browser = _client(sign_in_settings, stores, call_origin=configured)
        member = seed_member(stores, installed_web_auth_config(app))

        answer = browser.get(CALL_ORIGIN_PATH, headers={"cookie": cookie_header(member.set_cookie_headers)})

        assert (answer.status_code, answer.json()) == (200, {"origin": expected})

    def test_refuses_a_request_without_a_session_and_names_no_origin(self, sign_in_settings, stores):
        _app, browser = _client(sign_in_settings, stores, call_origin=CALL_ORIGIN)

        answer = browser.get(CALL_ORIGIN_PATH, headers={"accept": "application/json"})

        assert answer.status_code == 401
        assert CALL_ORIGIN not in answer.text
