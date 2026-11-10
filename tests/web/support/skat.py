import copy
import itertools
import json
from contextlib import ExitStack, contextmanager
from dataclasses import replace

from agents.mcp_wire import PROTOCOL_VERSION, PROTOCOL_VERSION_HEADER
from fastapi.testclient import TestClient
from mcp.shared.inbound import MCP_METHOD_HEADER, MCP_NAME_HEADER, NAME_BEARING_METHODS
from mcp_types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY
from webauth.config import install_web_auth_config, installed_web_auth_config

from skat.engine.deal import positions_from
from skat.host.app import create_app
from skat.table.service import TableService
from skat.web.stores import SignInStores
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLE_SIT_SUFFIX, TABLE_STAND_SUFFIX, TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.support.page_build import fixture_page_build
from tests.support.payload_cards import DEALER_SEAT, with_known_deal
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, new_account, seed_member
from tests.web.support.playing import Table

FETCH = {"accept": "application/json"}
NAVIGATION = {"accept": "text/html"}
UNKNOWN_ID = "0" * 32
SERVER_START_SECONDS = 1000.0


def stored(skat):
    return copy.deepcopy((skat.store.tables, skat.store.receipts))


class FakeTime:
    """A monotonic clock and a scheduler on it: `advance` runs every action that falls due, in due order."""

    def __init__(self, now=SERVER_START_SECONDS):
        self.now = now
        self._scheduled = []

    def clock(self):
        return self.now

    def schedule(self, delay, action):
        self._scheduled.append((self.now + delay, action))

    def cancel_all(self):
        self._scheduled.clear()

    @property
    def pending(self):
        return len(self._scheduled)

    async def advance(self, seconds):
        horizon = self.now + seconds
        while due := [entry for entry in self._scheduled if entry[0] <= horizon]:
            entry = min(due, key=lambda scheduled: scheduled[0])
            self._scheduled.remove(entry)
            self.now = max(self.now, entry[0])
            await entry[1]()
        self.now = horizon


class Skat:
    def __init__(self, sign_in_settings, store=None, stores=None, **app_options):
        self.stores = stores if stores is not None else SignInStores.in_memory()
        self.store = store if store is not None else FakeTableStore()
        self.app = create_app(
            sign_in_settings().settings,
            page_build=fixture_page_build(),
            tables=TableService(self.store),
            stores=self.stores,
            **app_options,
        )
        self.config = installed_web_auth_config(self.app)
        self.client = TestClient(self.app, base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False)

    def run_on_clock(self, now):
        """Reads webauth's time from `now[0]`, a list the test moves; call before the first member is seeded."""
        self.config = replace(self.config, wall_clock=lambda: now[0])
        install_web_auth_config(self.app, self.config)

    def member(self, account=None, **seed_options):
        """A member with a session of their own; with `account`, a further device of that account."""
        member = seed_member(
            self.stores, self.config, account=account or new_account(self.stores, self.config), **seed_options
        )
        return {"cookie": cookie_header(member.set_cookie_headers), **FETCH}, member.account

    def create(self, headers, command_id="command-0001", series_length=36, **extra):
        return self.client.post(
            TABLES_PATH,
            json={"command_id": command_id, "series_length": series_length, **extra},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

    def sit(self, headers, table_id, seat, command_id="command-sit", **extra):
        return self.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_SIT_SUFFIX}",
            json={"command_id": command_id, "seat": seat, **extra},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

    def stand(self, headers, table_id, command_id="command-stand", **extra):
        return self.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_STAND_SUFFIX}",
            json={"command_id": command_id, **extra},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )


@contextmanager
def streams_of(server, table_id, people):
    """One open stream per person; yields each stream's decoded messages, its first view already read."""
    with ExitStack() as open_streams:
        decoded = []
        for headers, _ in people:
            stream = open_streams.enter_context(
                server.client.stream("GET", f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}", headers=headers)
            )
            messages = (
                json.loads(line.removeprefix("data: ")) for line in stream.iter_lines() if line.startswith("data: ")
            )
            next(messages)
            server.client.cookies.clear()
            decoded.append(messages)
        yield decoded


def mcp_message(method, params=None):
    """The headers and the JSON-RPC body of one request at the served revision, as an agent's client sends them."""
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {
            **(params or {}),
            "_meta": {PROTOCOL_VERSION_META_KEY: PROTOCOL_VERSION, CLIENT_CAPABILITIES_META_KEY: {}},
        },
    }
    headers = {PROTOCOL_VERSION_HEADER: PROTOCOL_VERSION, MCP_METHOD_HEADER: method}
    if method in NAME_BEARING_METHODS:
        headers[MCP_NAME_HEADER] = body["params"][NAME_BEARING_METHODS[method]]
    return headers, body


class AgentTable(Table):
    """The known hand dealt at a table where the agent's account holds the chair of `position`.

    Sitting is no tool yet, so the agent sits like a person: with a cookie session for the account its first call at
    /mcp created, `agent_headers`. The other two chairs are people's, and the watcher is a fourth member.
    """

    def __init__(self, skat, agent_headers, position):
        self.skat = skat
        self._commands = itertools.count(1)
        agent_seat = next(seat for seat, held in positions_from(DEALER_SEAT).items() if held is position)
        people = [skat.member() for _ in range(3)]
        others = iter(headers for headers, _ in people)
        by_seat = {seat: agent_headers if seat == agent_seat else next(others) for seat in (1, 2, 3)}
        self.table_id = skat.create(by_seat[1]).json()["id"]
        for seat in (2, 3):
            skat.sit(by_seat[seat], self.table_id, seat, command_id=f"command-sit-{seat}")
        with_known_deal(skat, self.table_id)
        self.at = {held: by_seat[seat] for seat, held in positions_from(DEALER_SEAT).items()}
        self.watcher = people[2][0]
