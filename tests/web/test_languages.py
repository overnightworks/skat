import re
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from webauth.config import installed_web_auth_config

from skat.host.app import create_app
from skat.web import languages
from skat.web.constants import CALL_SIGN_IN_PATH, HOME_PATH, LOGIN_PATH, NO_ACCESS_PATH
from skat.web.tables import TABLE_PAGE_PREFIX
from skat.web.words import LANGUAGES, SOURCE_LANGUAGE
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import in_memory_tables
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import fixture_page_build
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member

if TYPE_CHECKING:
    from fastapi import FastAPI


def skat_app(sign_in_settings, stores=None) -> FastAPI:
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


class TestPlainSignInPages:
    @pytest.mark.parametrize("path", [LOGIN_PATH, NO_ACCESS_PATH, CALL_SIGN_IN_PATH])
    def test_a_plain_sign_in_page_says_the_source_language_its_words_are_in(self, sign_in_settings, path):
        client = TestClient(skat_app(sign_in_settings), base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False)

        assert html_lang_of(client.get(path).content) == SOURCE_LANGUAGE
