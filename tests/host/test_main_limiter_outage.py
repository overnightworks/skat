"""A Redis that goes away takes the limits and the wake channel with it, and a stream that is open meanwhile keeps
running."""

import json
from http import HTTPStatus

import httpx2
import pytest
from webauth.config import installed_web_auth_config

from skat.host.app import PodLinks, create_app
from skat.store.redis_clients import shared_place_store, shared_rate_limits, shared_wake_channel
from skat.table.records import Actor, CreateTable, SitDown
from skat.web.constants import ACCOUNT_PATH, HEALTH_PATH
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.fake_rule_sets import in_memory_rule_sets
from tests.support.fake_tables import in_memory_tables
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import fixture_page_build
from tests.support.running_server import STARTED_WITHIN_SECONDS, started_server
from tests.support.signed_in import cookie_header, seed_member
from tests.support.skat_process import LOOPBACK, free_port, unnamed_event_data

pytestmark = pytest.mark.redis

# Short, so that a stream whose state changed shows the change within a moment of the next heartbeat.
HEARTBEAT_SECONDS = 0.2


def test_a_stream_open_when_the_limits_fail_still_shows_a_change_while_new_requests_get_a_503_and_health_answers(
    sign_in_settings, redis_url, relay_in_front_of
):
    settings = sign_in_settings(host=LOOPBACK, port=free_port()).settings
    stores = in_memory_stores()
    tables = in_memory_tables()
    redis = relay_in_front_of(redis_url)
    process_ended: list[bool] = []
    app = create_app(
        settings,
        page_build=fixture_page_build(),
        tables=tables,
        rule_sets=in_memory_rule_sets(),
        stores=stores,
        heartbeat_seconds=HEARTBEAT_SECONDS,
        pods=PodLinks(
            rate_limits=shared_rate_limits(redis.url),
            wake_channel=shared_wake_channel(redis.url),
            place_store=shared_place_store(redis.url),
            end_process=lambda: process_ended.append(True),
        ),
    )
    config = installed_web_auth_config(app)
    owner = seed_member(stores, config)
    guest = seed_member(stores, config)
    table = tables.create(Actor(owner.account.id, "Owner"), CreateTable(command_id="open-the-table"))
    base_url = f"http://{LOOPBACK}:{settings.port}"
    server, thread = started_server(app, settings)
    try:
        with httpx2.stream(
            "GET",
            f"{base_url}{TABLES_PATH}/{table.id}{TABLE_EVENTS_SUFFIX}",
            headers={"cookie": cookie_header(owner.set_cookie_headers)},
            timeout=STARTED_WITHIN_SECONDS,
        ) as stream:
            events = unnamed_event_data(stream.iter_lines())
            before = json.loads(next(events))

            redis.sever()
            tables.sit(Actor(guest.account.id, "Guest"), SitDown("take-a-seat", table.id, 2), frozenset())
            after = json.loads(next(events))

            refused = httpx2.get(f"{base_url}{ACCOUNT_PATH}", timeout=STARTED_WITHIN_SECONDS)
            healthy = httpx2.get(f"{base_url}{HEALTH_PATH}", timeout=STARTED_WITHIN_SECONDS)
    finally:
        server.should_exit = True
        thread.join(timeout=STARTED_WITHIN_SECONDS)

    assert after["version"] > before["version"]
    assert process_ended == []
    assert refused.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert healthy.status_code == HTTPStatus.OK
