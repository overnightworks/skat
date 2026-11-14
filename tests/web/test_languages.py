import re
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from webauth.config import installed_web_auth_config

from skat.host.app import create_app
from skat.web import languages
from skat.web.constants import AUTH_CALLBACK_PATH, CALL_SIGN_IN_PATH, HOME_PATH, LOGIN_PATH, NO_ACCESS_PATH
from skat.web.tables import TABLE_PAGE_PREFIX
from skat.web.words import LANGUAGES, SOURCE_LANGUAGE
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import in_memory_tables
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import fixture_page_build, served_page
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member

if TYPE_CHECKING:
    from fastapi import FastAPI


def skat_app(sign_in_settings, stores) -> FastAPI:
    return create_app(
        sign_in_settings().settings,
        page_build=fixture_page_build(),
        tables=in_memory_tables(),
        rule_sets=in_memory_rule_sets(),
        stores=stores,
    )


def member_client(sign_in_settings, *, account_language: str | None, accept_language: str | None) -> TestClient:
    stores = in_memory_stores()
    app = skat_app(sign_in_settings, stores)
    member = seed_member(stores, installed_web_auth_config(app), account_language=account_language)
    headers = {"cookie": cookie_header(member.set_cookie_headers)}
    if accept_language is not None:
        headers["accept-language"] = accept_language
    return TestClient(app, base_url=TEST_PUBLIC_ORIGIN, headers=headers, follow_redirects=False)


SHELL_PATHS = pytest.mark.parametrize("path", [HOME_PATH, f"{TABLE_PAGE_PREFIX}table-1"], ids=["home", "table"])
UNOFFERED_TAG = "tlh"


def html_lang_of(content: bytes) -> str:
    return re.search(rb'<html lang="([^"]+)">', content).group(1).decode()


class TestShellLanguage:
    @SHELL_PATHS
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_a_browser_asking_for_an_offered_language_gets_the_shell_in_it(self, sign_in_settings, path, language):
        client = member_client(sign_in_settings, account_language=None, accept_language=language)

        assert html_lang_of(client.get(path).content) == language

    @SHELL_PATHS
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_an_account_language_wins_over_a_browser_asking_for_a_tag_no_catalog_has(
        self, sign_in_settings, path, language
    ):
        client = member_client(sign_in_settings, account_language=language, accept_language=UNOFFERED_TAG)

        assert html_lang_of(client.get(path).content) == language

    @SHELL_PATHS
    @pytest.mark.parametrize(
        ("account_language", "accept_language"),
        [(None, None), (None, UNOFFERED_TAG), (UNOFFERED_TAG, None), (UNOFFERED_TAG, UNOFFERED_TAG)],
        ids=["no-language", "unoffered-browser", "unoffered-account", "both-unoffered"],
    )
    def test_a_person_asking_only_for_tags_no_catalog_has_gets_the_source_language(
        self, sign_in_settings, path, account_language, accept_language
    ):
        client = member_client(sign_in_settings, account_language=account_language, accept_language=accept_language)

        assert html_lang_of(client.get(path).content) == SOURCE_LANGUAGE

    def test_the_offer_is_the_languages_of_the_catalogs_with_the_source_language_as_default(self):
        assert languages.APP_LANGUAGES.offered == LANGUAGES
        assert languages.APP_LANGUAGES.default == SOURCE_LANGUAGE

    @SHELL_PATHS
    def test_a_shell_chosen_by_language_says_so_to_caches(self, sign_in_settings, path):
        client = member_client(sign_in_settings, account_language=None, accept_language=None)

        varied = {token.strip().lower() for token in client.get(path).headers["vary"].split(",")}

        assert {"accept-language", "cookie"} <= varied


SIGN_IN_PAGES = pytest.mark.parametrize(
    ("path", "name", "status"),
    [
        (LOGIN_PATH, "login.html", 200),
        (NO_ACCESS_PATH, "no-access.html", 200),
        (CALL_SIGN_IN_PATH, "login/call.html", 200),
        (f"{AUTH_CALLBACK_PATH}?state=forged&code=x", "login-failed.html", 403),
    ],
    ids=["signed-out", "no-access", "call", "login-failed"],
)


def anonymous_client(sign_in_settings, *, accept_language: str | None) -> TestClient:
    headers = {} if accept_language is None else {"accept-language": accept_language}
    return TestClient(
        skat_app(sign_in_settings, in_memory_stores()),
        base_url=TEST_PUBLIC_ORIGIN,
        headers=headers,
        follow_redirects=False,
    )


class TestSignInPageLanguage:
    @SIGN_IN_PAGES
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_an_account_language_decides_the_page_whatever_the_browser_asks_for(
        self, sign_in_settings, path, name, status, language
    ):
        client = member_client(sign_in_settings, account_language=language, accept_language=UNOFFERED_TAG)

        response = client.get(path)

        assert (response.status_code, response.content) == (status, served_page(name, language))

    @SIGN_IN_PAGES
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_a_browser_with_no_account_language_gets_the_page_in_the_language_it_asks_for(
        self, sign_in_settings, path, name, status, language
    ):
        client = anonymous_client(sign_in_settings, accept_language=language)

        response = client.get(path)

        assert (response.status_code, response.content) == (status, served_page(name, language))

    @SIGN_IN_PAGES
    @pytest.mark.parametrize("accept_language", [None, UNOFFERED_TAG])
    def test_a_person_asking_for_no_language_a_catalog_has_gets_the_source_language(
        self, sign_in_settings, path, name, status, accept_language
    ):
        client = anonymous_client(sign_in_settings, accept_language=accept_language)

        response = client.get(path)

        assert (response.status_code, response.content) == (status, served_page(name, SOURCE_LANGUAGE))

    @SIGN_IN_PAGES
    def test_a_page_chosen_by_language_says_so_to_caches_and_has_an_etag_of_its_own_per_language(
        self, sign_in_settings, path, name, status
    ):
        responses = [anonymous_client(sign_in_settings, accept_language=language).get(path) for language in LANGUAGES]

        for response in responses:
            varied = {token.strip().lower() for token in response.headers["vary"].split(",")}
            assert {"accept-language", "cookie"} <= varied
        assert len({response.headers["etag"] for response in responses}) == len(LANGUAGES)
