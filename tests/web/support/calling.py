"""A person who calls agents, the agents that listen for it, the control's routes and the table fixtures for them."""

import json
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from skat.web.calling import (
    AGENT_ADDERS_GROUP,
    TABLE_AGENT_CALL_SUFFIX,
    TABLE_AGENT_SEND_AWAY_SUFFIX,
    TABLE_AGENTS_SUFFIX,
)
from skat.web.tables import TABLES_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import new_account
from tests.web.support.agent import Agent
from tests.web.support.changes import RecordedChanges
from tests.web.support.sdk_agent import SdkAgent
from tests.web.support.skat import FETCH, Skat, streams_of


@dataclass(frozen=True)
class Person:
    """A signed-in person: the headers of their session and their account id."""

    headers: dict[str, str]
    id: str


def person(skat, issuer, *, groups=(AGENT_ADDERS_GROUP,), refresh_token=True) -> Person:
    """A member whose session holds a refresh token the issuer honours, and whose groups the issuer reports."""
    account = new_account(skat.stores, skat.config)
    token = issuer.refresh_token_for(account.id) if refresh_token else None
    headers, account = skat.member(account, refresh_token=token)
    issuer.grant_groups(account.id, groups)
    return Person(headers, account.id)


def running_skat(hold, issuer, time, **wiring):
    """A Skat with its client open, for a fixture to `yield from`; `wiring` is passed on to `Skat`."""
    skat = Skat(
        lambda: hold,
        issuer_transports=issuer.transports,
        chair_clock=time.clock,
        chair_scheduler=time,
        now=time.moment,
        **wiring,
    )
    with skat.client:
        yield skat


def refresh_grants(issuer):
    return len(issuer.access_tokens_issued("refresh_token"))


def control_path(table_id):
    return f"{TABLES_PATH}/{table_id}{TABLE_AGENTS_SUFFIX}"


def read_control(skat, who, table_id, **headers):
    return skat.client.get(control_path(table_id), headers={**who.headers, **headers})


def call(skat, who, table_id, key):
    return skat.client.post(
        f"{control_path(table_id)}/{key}{TABLE_AGENT_CALL_SUFFIX}",
        headers={"origin": TEST_PUBLIC_ORIGIN, **who.headers, **FETCH},
    )


def send_away(skat, who, table_id, key, command_id="command-send-away"):
    return skat.client.post(
        f"{control_path(table_id)}/{key}{TABLE_AGENT_SEND_AWAY_SUFFIX}",
        json={"command_id": command_id},
        headers={"origin": TEST_PUBLIC_ORIGIN, **who.headers, **FETCH},
    )


def only_row(skat, who, table_id):
    rows = read_control(skat, who, table_id).json()["rows"]
    assert len(rows) == 1, rows
    return rows[0]


@contextmanager
def listening(skat, issuer, owner, name, subject):
    """The agent `name` of `owner`, listening on its standing as a runner does, for as long as the block runs."""
    session = SdkAgent(skat, issuer, subject, agent_owner=owner.id, agent_name=name)
    with session.connected() as connected, connected.listening():
        yield Agent(skat, issuer, subject, agent_owner=owner.id, agent_name=name)


def invitations_of(agent):
    return [standing for standing in json.loads(agent.standing())["standings"] if standing["state"] == "invited"]


def offer_of(agent):
    """The agent's only open invitation as `accept` takes it."""
    (standing,) = invitations_of(agent)
    return SimpleNamespace(id=standing["invitation"]["id"], epoch=standing["invitation"]["epoch"])


def seat_of_nobody_but(skat, table_id, count):
    """`count` more people sit down at the table."""
    for seat in range(2, 2 + count):
        skat.sit(skat.member()[0], table_id, seat, command_id=f"command-sit-{seat}")
    skat.client.cookies.clear()


class CallingTable:
    """The fixtures of a member who calls agents at a table of their own; a test class inherits them."""

    @pytest.fixture
    def changes(self):
        return RecordedChanges()

    @pytest.fixture
    def skat(self, hold, issuer, time, changes):
        yield from running_skat(hold, issuer, time, resource_changes=changes.wired)

    @pytest.fixture
    def felix(self, skat, issuer):
        return person(skat, issuer)

    @pytest.fixture
    def table_id(self, skat, felix):
        """A table Felix opened and sits at."""
        created = skat.create(felix.headers)
        skat.client.cookies.clear()
        return created.json()["id"]

    @pytest.fixture
    def watching(self, skat, felix, table_id):
        """Felix has an open stream on his table."""
        with streams_of(skat, table_id, [(felix.headers, None)]):
            yield
