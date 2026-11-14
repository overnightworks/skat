from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from webauth.admission import AppRole
from webauth.ports import AccountKind

from skat.web.words import SOURCE_LANGUAGE
from tests.e2e.support.audio import RECORDING_AUDIO_SCRIPT, playing_table
from tests.e2e.support.browser_coverage import BrowserCoverage
from tests.e2e.support.deal_pause import HeldDealPause
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.failure_record import FailureRecord
from tests.e2e.support.people import PERSON_ADDRESS_BASE, person_address_offsets, playwright_cookie
from tests.e2e.support.server import RunningServer, skat_on_new_database
from tests.e2e.support.shards import select_shard
from tests.support.signed_in import SeededMember, new_account, seed_member

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import BrowserContext, Page, Request

    from tests.e2e.support.hands import PlayingTable

PAGE_NAVIGATED_AWAY = "net::ERR_ABORTED"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    select_shard(config, items, Path(__file__).parent)


@pytest.fixture(scope="session")
def deal_pause_scheduler() -> HeldDealPause:
    return HeldDealPause()


@pytest.fixture(scope="session")
def e2e_server(
    tmp_path_factory: pytest.TempPathFactory, deal_pause_scheduler: HeldDealPause
) -> Iterator[RunningServer]:
    """Skat on a free loopback port over a database of its own, its issuer a fake."""
    with skat_on_new_database(tmp_path_factory, chair_scheduler=deal_pause_scheduler) as server:
        yield server


@pytest.fixture
def held_deal_pause(deal_pause_scheduler: HeldDealPause) -> Iterator[HeldDealPause]:
    """The pause before a table's next deal stays pending until the test releases it, or until the test ends."""
    deal_pause_scheduler.hold()
    yield deal_pause_scheduler
    deal_pause_scheduler.release()


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
    return {**browser_context_args, "ignore_https_errors": True}


PAGE_TIMELINE_SECTION = "page timeline"
TIMELINE_PRINTED = pytest.StashKey[bool]()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[None]:
    """A test that fails while its pages run, in the test or in a fixture's teardown, carries the timeline of its
    pages, so the CI log shows more than the assertion; a failed call and a failed teardown print it once.
    """
    report = yield
    record = getattr(item, "funcargs", {}).get("failure_record")
    if (
        report.when in ("call", "teardown")
        and report.failed
        and isinstance(record, FailureRecord)
        and TIMELINE_PRINTED not in item.stash
    ):
        item.stash[TIMELINE_PRINTED] = True
        report.sections.append((f"Captured {PAGE_TIMELINE_SECTION}", record.render()))
    return report


@pytest.fixture
def failure_record() -> FailureRecord:
    """The timeline of every page this test opens through `open_person`."""
    return FailureRecord()


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


def sign_in(
    context: BrowserContext, server: RunningServer, username: str | None, groups: tuple[str, ...] | None
) -> SeededMember:
    if username is None:
        account = new_account(server.stores, server.config)
    else:
        # A person who signs in again, in this test or in an earlier one, is the account the database already holds.
        with server.stores.transaction() as entry:
            account = entry.accounts.get(f"subject-{username}") or entry.accounts.create_for_subject(
                f"subject-{username}", username, role=AppRole.USER, kind=AccountKind.PERSON
            )
    # With `groups` the session holds a refresh token and the issuer reports them as the person's groups.
    refresh_token = None if groups is None else server.issuer.refresh_token_for(account.id)
    if groups is not None:
        server.issuer.grant_groups(account.id, groups)
    member = seed_member(server.stores, server.config, account=account, refresh_token=refresh_token)
    context.add_cookies([playwright_cookie(header, server.config, server.host) for header in member.set_cookie_headers])
    return member


@pytest.fixture
def open_person(
    new_context: Callable[..., BrowserContext],
    e2e_server: RunningServer,
    seeded_members: dict[Page, SeededMember],
    expected_request_failures: list[str],
    browser_coverage: BrowserCoverage,
    failure_record: FailureRecord,
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
        person_number = next(person_address_offsets)
        person_address = PERSON_ADDRESS_BASE + person_number
        # The plugin's factory traces the context, so a failing test leaves its trace in the output directory.
        # A measured card is not in motion: a test that needs motion names "no-preference" itself.
        # Every context asks for the source language unless a test names another, so the suite stays in it when a
        # further catalog lands; the factory merges the session's context arguments, so the locale lives here.
        context = new_context(
            **{
                "locale": SOURCE_LANGUAGE,
                "reduced_motion": "reduce",
                "extra_http_headers": {"X-Forwarded-For": str(person_address)},
                **device_options,
            }
        )
        contexts.append(context)
        context.add_init_script(path=RECORDING_AUDIO_SCRIPT)
        browser_coverage.watch(context)
        context.on("requestfailed", note_failed_request)
        page = context.new_page()
        failure_record.watch(page, username or f"person-{person_number}")
        if signed_in:
            seeded_members[page] = sign_in(context, server, username, groups)
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


@pytest.fixture
def table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> PlayingTable:
    """Three people at a table in the play of a Kreuz game, a watcher beside them."""
    return playing_table(open_person, e2e_server, member_of, page_errors)
