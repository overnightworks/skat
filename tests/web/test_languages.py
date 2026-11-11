import pytest
from fastapi.testclient import TestClient
from webauth.config import installed_web_auth_config

from skat.host.app import create_app
from skat.web.constants import HOME_PATH
from skat.web.tables import TABLE_PAGE_PREFIX
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import in_memory_tables
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import fixture_page_build
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member


def member_client(sign_in_settings, *, account_language: str | None, accept_language: str | None) -> TestClient:
    stores = in_memory_stores()
    app = create_app(
        sign_in_settings().settings,
        page_build=fixture_page_build(),
        tables=in_memory_tables(),
        rule_sets=in_memory_rule_sets(),
        stores=stores,
    )
    member = seed_member(stores, installed_web_auth_config(app), account_language=account_language)
    headers = {"cookie": cookie_header(member.set_cookie_headers)}
    if accept_language is not None:
        headers["accept-language"] = accept_language
    return TestClient(app, base_url=TEST_PUBLIC_ORIGIN, headers=headers, follow_redirects=False)


class TestShellLanguage:
    @pytest.mark.parametrize("path", [HOME_PATH, f"{TABLE_PAGE_PREFIX}table-1"], ids=["home", "table"])
    @pytest.mark.parametrize(
        ("account_language", "accept_language"),
        [(None, None), (None, "en"), ("de-AT", None), ("fr", None)],
        ids=["no-language", "english-browser", "austrian-account", "unoffered-account"],
    )
    def test_the_shell_says_german_for_every_person_because_german_is_the_only_language_offered(
        self, sign_in_settings, path, account_language, accept_language
    ):
        response = member_client(
            sign_in_settings, account_language=account_language, accept_language=accept_language
        ).get(path)

        assert response.status_code == 200
        assert response.content.count(b'<html lang="de">') == 1
        assert b'<html lang="en">' not in response.content
