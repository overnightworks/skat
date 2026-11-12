from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from webauth.admission import AppRole
from webauth.ports import AccountKind

from skat.web.words import SOURCE_LANGUAGE
from tests.e2e.support.audio import RECORDING_AUDIO_SCRIPT
from tests.e2e.support.browser_coverage import BrowserCoverage
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.people import PERSON_ADDRESS_BASE, person_address_offsets, playwright_cookie
from tests.e2e.support.server import RunningServer, skat_on_new_database
from tests.e2e.support.shards import select_shard
from tests.support.signed_in import SeededMember, new_account, seed_member

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import Browser, BrowserContext, Page, Request

PAGE_NAVIGATED_AWAY = "net::ERR_ABORTED"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    select_shard(config, items, Path(__file__).parent)


@pytest.fixture(scope="session")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """Skat on a free loopback port over a database of its own, its issuer a fake."""
    with skat_on_new_database(tmp_path_factory) as server:
        yield server


@pytest.fixture(scope="session")
def base_url() -> None:
    # Every test opens its server's absolute address, so no session-wide address ties the browser to one server.
    return None


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict[str, Any]) -> dict[str, Any]:
    # The test certificate is self-signed: the per-request waiver of ignore_https_errors restarts a request
    # once per failed handshake, up to Chromium's cap, and a stylesheet that hits it never loads.
    # A page that Playwright answers itself has no address, so Chromium counts it public and blocks its requests
    # to Skat on loopback; the framing tests serve their call page that way.
    return {
        **browser_type_launch_args,
        "args": ["--ignore-certificate-errors", "--disable-features=LocalNetworkAccessChecks"],
    }


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    # A measured card is not in motion: a test that needs motion names "no-preference" itself.
    # Every context asks for the source language, so the suite stays in it when a further catalog lands.
    return {
        **browser_context_args,
        "ignore_https_errors": True,
        "reduced_motion": "reduce",
        "locale": SOURCE_LANGUAGE,
    }


@pytest.fixture
def seeded_members() -> dict[Page, SeededMember]:
    return {}


@pytest.fixture
def member_of(seeded_members: dict[Page, SeededMember]) -> Callable[[Page], SeededMember]:
    return seeded_members.__getitem__


@pytest.fixture
def expected_request_failures() -> list[str]:
    """URL prefixes of requests a test breaks on purpose; it appends them before the request is made."""
    return []


@pytest.fixture
def browser_coverage() -> BrowserCoverage:
    """The one collector of this test; with collection off it routes nothing and records nothing."""
    return BrowserCoverage.from_environment()


@pytest.fixture
def realm_reusing_refresh_tokens(e2e_server: RunningServer) -> Iterator[None]:
    # The realm lets a refresh token be used again, so overlapping reads of one session both succeed.
    e2e_server.issuer.reuses_refresh_tokens = True
    yield
    e2e_server.issuer.reuses_refresh_tokens = False


@pytest.fixture
def open_person(
    browser: Browser,
    browser_context_args: dict[str, Any],
    e2e_server: RunningServer,
    seeded_members: dict[Page, SeededMember],
    expected_request_failures: list[str],
    browser_coverage: BrowserCoverage,
) -> Iterator[Callable[..., Page]]:
    contexts: list[BrowserContext] = []
    failed_requests: list[str] = []

    def note_failed_request(request: Request) -> None:
        if request.failure != PAGE_NAVIGATED_AWAY and not request.url.startswith(tuple(expected_request_failures)):
            failed_requests.append(f"{request.url}: {request.failure}")

    def open_page(
        *,
        signed_in: bool = True,
        username: str | None = None,
        server: RunningServer = e2e_server,
        groups: tuple[str, ...] | None = None,
        **device_options: Any,
    ) -> Page:
        person_address = PERSON_ADDRESS_BASE + next(person_address_offsets)
        context = browser.new_context(
            **{**browser_context_args, "extra_http_headers": {"X-Forwarded-For": str(person_address)}, **device_options}
        )
        contexts.append(context)
        context.add_init_script(path=RECORDING_AUDIO_SCRIPT)
        browser_coverage.watch(context)
        context.on("requestfailed", note_failed_request)
        page = context.new_page()
        if signed_in:
            if username is None:
                account = new_account(server.stores, server.config)
            else:
                account = server.stores.accounts.create_for_subject(
                    f"subject-{username}", username, role=AppRole.USER, kind=AccountKind.PERSON
                )
            # With `groups` the session holds a refresh token and the issuer reports them as the person's groups.
            refresh_token = None if groups is None else server.issuer.refresh_token_for(account.id)
            if groups is not None:
                server.issuer.grant_groups(account.id, groups)
            member = seed_member(server.stores, server.config, account=account, refresh_token=refresh_token)
            context.add_cookies(
                [playwright_cookie(header, server.config, server.host) for header in member.set_cookie_headers]
            )
            seeded_members[page] = member
        return page

    yield open_page
    browser_coverage.write()
    for context in contexts:
        context.close()
    assert failed_requests == []


@pytest.fixture
def page_errors() -> Iterator[list[str]]:
    errors: list[str] = []
    yield errors
    assert errors == []


@pytest.fixture
def deal_a_declaring_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., DeclaringTable]:
    def deal(form_factor: dict[str, Any], *, console: bool = True) -> DeclaringTable:
        return DeclaringTable(open_person, e2e_server, member_of, page_errors, form_factor, console=console)

    return deal
