"""Two servers of one Skat on one Redis, as two pods: an agent that listens on one is listed on the page of the other,
and the key the page of one gave calls the agent through the other.
"""

import asyncio
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING

import httpx2
import pytest
from redis.asyncio import Redis
from tandem.testing import settle_epoch
from webauth.config import installed_web_auth_config

from skat.host.app import PodLinks, create_app
from skat.store.redis_clients import (
    WAKE_KEY_PREFIX,
    shared_agent_records,
    shared_place_store,
    shared_rate_limits,
    shared_stream_leases,
    shared_wake_channel,
)
from skat.web.calling import AGENT_ADDERS_GROUP, TABLE_AGENT_CALL_SUFFIX, TABLE_AGENTS_SUFFIX
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.e2e.support.listening_agent import ListeningAgent
from tests.support.fake_issuer import FakeIssuer
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import in_memory_tables
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import fixture_page_build
from tests.support.running_server import STARTED_WITHIN_SECONDS, started_server
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, new_account, seed_member
from tests.support.skat_process import LOOPBACK, free_port, unnamed_event_data

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.redis

NOVA = "agent-nova"


def pod_links(redis_url):
    return PodLinks(
        rate_limits=shared_rate_limits(redis_url),
        wake_channel=shared_wake_channel(redis_url),
        place_store=shared_place_store(redis_url),
        agent_records=shared_agent_records(redis_url),
        stream_leases=shared_stream_leases(redis_url),
    )


def settled_leases(redis_url):
    async def settle():
        client = Redis.from_url(redis_url)  # pyright: ignore[reportUnknownMemberType]
        try:
            await settle_epoch(client, key_prefix=WAKE_KEY_PREFIX)
        finally:
            await client.aclose()

    asyncio.run(settle())


@pytest.fixture
def pods(sign_in_settings, redis_url):
    """Two servers of one app over one set of accounts and tables and one Redis; each a `SimpleNamespace` of the
    address and the issuer that signs the agents' tokens, which both trust.
    """
    settled_leases(redis_url)
    settings = sign_in_settings(host=LOOPBACK, port=free_port(), redis_url=redis_url)
    issuer = FakeIssuer(settings)
    stores, tables = in_memory_stores(), in_memory_tables()
    with ExitStack() as running:
        servers = []
        for port in (settings.settings.port, free_port()):
            pod_settings = settings.settings.model_copy(update={"port": port})
            app = create_app(
                pod_settings,
                page_build=fixture_page_build(),
                tables=tables,
                rule_sets=in_memory_rule_sets(),
                stores=stores,
                issuer_transports=issuer.transports,
                pods=pod_links(redis_url),
            )
            server, thread = started_server(app, pod_settings)
            running.callback(thread.join, STARTED_WITHIN_SECONDS)
            running.callback(setattr, server, "should_exit", True)
            servers.append(
                SimpleNamespace(
                    redis_url=redis_url,
                    base_url=f"http://{LOOPBACK}:{port}",
                    issuer=issuer,
                    stores=stores,
                    config=installed_web_auth_config(app),
                )
            )
        yield servers


def felix_of(pod, issuer):
    account = new_account(pod.stores, pod.config)
    token = issuer.refresh_token_for(account.id)
    member = seed_member(pod.stores, pod.config, account=account, refresh_token=token)
    issuer.grant_groups(account.id, (AGENT_ADDERS_GROUP,))
    return SimpleNamespace(id=account.id, cookie=cookie_header(member.set_cookie_headers))


def agents_at(pod, felix, table_id):
    return httpx2.get(
        f"{pod.base_url}{TABLES_PATH}/{table_id}{TABLE_AGENTS_SUFFIX}",
        headers={"cookie": felix.cookie, "accept": "application/json"},
        timeout=STARTED_WITHIN_SECONDS,
    ).json()


@contextmanager
def felix_watching(pod, felix, table_id) -> Iterator[None]:
    """Felix has an open stream on his table at `pod`."""
    with httpx2.stream(
        "GET",
        f"{pod.base_url}{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}",
        headers={"cookie": felix.cookie},
        timeout=STARTED_WITHIN_SECONDS,
    ) as stream:
        events = unnamed_event_data(stream.iter_lines())
        next(events)
        yield


@pytest.mark.parametrize(("listens_on", "page_on"), [(0, 1), (1, 0)], ids=["listens-on-a", "listens-on-b"])
def test_an_agent_listening_on_one_server_is_listed_and_called_through_the_other_with_the_key_it_gave(
    pods, listens_on, page_on
):
    issuer = pods[0].issuer
    felix = felix_of(pods[0], issuer)
    opened = httpx2.post(
        f"{pods[0].base_url}{TABLES_PATH}",
        json={"command_id": "command-open", "series_length": 3},
        headers={"cookie": felix.cookie, "origin": TEST_PUBLIC_ORIGIN, "accept": "application/json"},
        timeout=STARTED_WITHIN_SECONDS,
    )
    table_id = opened.json()["id"]
    agent = ListeningAgent(pods[listens_on], felix.id, "Nova", NOVA)
    try:
        with felix_watching(pods[listens_on], felix, table_id):
            gave = agents_at(pods[listens_on], felix, table_id)
            seen = agents_at(pods[page_on], felix, table_id)
            (row,) = seen["rows"]
            called = httpx2.post(
                f"{pods[page_on].base_url}{TABLES_PATH}/{table_id}{TABLE_AGENTS_SUFFIX}/{row['key']}{TABLE_AGENT_CALL_SUFFIX}",
                headers={"cookie": felix.cookie, "origin": TEST_PUBLIC_ORIGIN, "accept": "application/json"},
                timeout=STARTED_WITHIN_SECONDS,
            )
    finally:
        agent.close()

    assert [(each["name"], each["key"]) for each in gave["rows"]] == [("Nova", row["key"])]
    assert (row["name"], row["state"], called.status_code) == ("Nova", "available", 200)
    assert called.json()["rows"][0]["state"] == "inviting"
