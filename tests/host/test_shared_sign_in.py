"""Two apps on one database share what signing in writes: a person's session and an agent's account."""

from dataclasses import dataclass
from urllib.parse import urlencode

import pytest
from agents.mcp_wire import MCP_ENDPOINT_PATH
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from webauth.ports import AccountKind

from skat.host.app import create_app
from skat.store.migrate import create_store_engine
from skat.store.schema import accounts
from skat.store.sign_in import PostgresSignInStores
from skat.web.constants import ACCOUNT_PATH, AUTH_CALLBACK_PATH, AUTH_START_PATH, BACKCHANNEL_LOGOUT_PATH, LOGIN_GROUP
from skat.web.sign_in import LoggingAuditSink
from tests.support.fake_issuer import FakeIssuer
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import in_memory_tables
from tests.support.page_build import fixture_page_build
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import mcp_message

pytestmark = pytest.mark.postgres

FETCH = {"accept": "application/json"}
FORM_POST = {"content-type": "application/x-www-form-urlencoded"}
AGENT_SUBJECT = "agent-subject-shared"
AGENT_TOKEN_HEADERS = {"accept": "application/json, text/event-stream"}


@dataclass(frozen=True)
class App:
    client: TestClient

    def as_cookie_of(self, browser: TestClient) -> dict[str, str]:
        return {"cookie": "; ".join(f"{name}={value}" for name, value in browser.cookies.items())}

    def account_name(self, cookie: dict[str, str]):
        return self.client.get(ACCOUNT_PATH, headers={**FETCH, **cookie})


@dataclass(frozen=True)
class TwoApps:
    first: App
    second: App
    issuer: FakeIssuer
    engine: object

    def signed_in_on_the_first(self, *, subject: str, username: str) -> dict[str, str]:
        """A browser's sign-in through the issuer on the first app; the cookie header it then sends to any app."""
        browser = TestClient(self.first.client.app, base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False)
        start = browser.get(AUTH_START_PATH)
        query = self.issuer.authorize(
            start.headers["location"], subject=subject, groups=[LOGIN_GROUP], username=username
        )
        browser.get(f"{AUTH_CALLBACK_PATH}?{query}")
        return self.first.as_cookie_of(browser)

    def account_count(self) -> int:
        with self.engine.connect() as connection:
            return connection.execute(select(func.count()).select_from(accounts)).scalar_one()


@pytest.fixture
def apps(sign_in_settings, database_url):
    sign_in = sign_in_settings()
    issuer = FakeIssuer(sign_in)
    engine = create_store_engine(database_url)

    def app_on_the_database():
        app = create_app(
            sign_in.settings,
            page_build=fixture_page_build(),
            tables=in_memory_tables(),
            rule_sets=in_memory_rule_sets(),
            stores=PostgresSignInStores(engine, audit=LoggingAuditSink()),
            issuer_transports=issuer.transports,
        )
        return App(TestClient(app, base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False))

    first, second = app_on_the_database(), app_on_the_database()
    with first.client, second.client:
        yield TwoApps(first, second, issuer, engine)
    engine.dispose()


class TestASignInOnOneApp:
    def test_is_admitted_by_the_other_app_as_the_same_account(self, apps):
        cookie = apps.signed_in_on_the_first(subject="subject-anna", username="anna")

        on_the_first, on_the_second = apps.first.account_name(cookie), apps.second.account_name(cookie)

        assert (on_the_first.status_code, on_the_second.status_code) == (200, 200)
        assert (on_the_first.json(), on_the_second.json()) == ({"name": "anna"}, {"name": "anna"})
        assert apps.account_count() == 1

    def test_ends_on_both_apps_with_the_issuers_back_channel_logout_sent_to_one(self, apps):
        phone = apps.signed_in_on_the_first(subject="subject-anna", username="anna")
        laptop = apps.signed_in_on_the_first(subject="subject-anna", username="anna")
        bystander = apps.signed_in_on_the_first(subject="subject-ben", username="ben")
        body = urlencode({"logout_token": apps.issuer.logout_token("subject-anna")}).encode()

        ended = apps.first.client.post(
            f"http://skat:8080{BACKCHANNEL_LOGOUT_PATH}", content=body, headers={**FORM_POST, "host": "skat:8080"}
        )

        assert ended.status_code == 200
        refused = [apps.second.account_name(cookie).status_code for cookie in (phone, laptop)]
        assert (refused, apps.second.account_name(bystander).status_code) == ([401, 401], 200)


class TestAnAgentsTokenOnOneApp:
    def call(self, app, apps):
        headers, body = mcp_message("tools/list")
        token = apps.issuer.agent_token(AGENT_SUBJECT)
        return app.client.post(
            MCP_ENDPOINT_PATH,
            json=body,
            headers={"authorization": f"Bearer {token}", **AGENT_TOKEN_HEADERS, **headers},
        )

    def test_that_registers_the_agent_on_its_first_call_is_admitted_by_the_other_app_on_the_same_account(self, apps):
        answers = [self.call(apps.first, apps).status_code, self.call(apps.second, apps).status_code]

        with apps.engine.connect() as connection:
            stored = connection.execute(select(accounts.c.id, accounts.c.kind)).all()
        assert (answers, [(row.id, row.kind) for row in stored]) == (
            [200, 200],
            [(AGENT_SUBJECT, AccountKind.AGENT.value)],
        )
