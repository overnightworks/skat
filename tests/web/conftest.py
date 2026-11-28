import pytest

from skat.engine.deal import Position
from tests.support.fake_issuer import FakeIssuer
from tests.support.idle_presence import idle_presence
from tests.support.in_memory_leases import InMemoryLeases
from tests.web.support.agent import Agent
from tests.web.support.member_client import MemberClient
from tests.web.support.playing import EIGHT_CARDS, Table
from tests.web.support.presence import Deals, Holds, Lapses, Wakes, on_a_worker, presence_on
from tests.web.support.skat import AgentTable, FakeTime, Skat
from tests.web.support.waiting_table import WaitingTable

FOREHAND, MIDDLEHAND = Position.FOREHAND, Position.MIDDLEHAND


@pytest.fixture
def skat(sign_in_settings):
    return Skat(sign_in_settings)


@pytest.fixture
def issuer(hold):
    return FakeIssuer(hold)


@pytest.fixture
def agent(skat, issuer):
    return Agent(skat, issuer)


@pytest.fixture
def middlehand_auction(skat, agent):
    """A dealt table, no step taken yet, where the agent holds the middlehand chair, whose turn it is."""
    table = AgentTable(skat, agent, MIDDLEHAND)
    skat.client.cookies.clear()
    return table


@pytest.fixture
def forehand_table(skat, agent):
    """A Hand game declared at a table where the agent holds the forehand, whose turn it is."""
    table = AgentTable(skat, agent, FOREHAND)
    table.declared_hand_game()
    skat.client.cookies.clear()
    return table


@pytest.fixture
def forehand_auction(skat, agent):
    """A dealt table, no step taken yet, where the agent holds the forehand chair."""
    table = AgentTable(skat, agent, FOREHAND)
    skat.client.cookies.clear()
    return table


@pytest.fixture
def wakes():
    return Wakes()


@pytest.fixture
def time():
    return FakeTime()


@pytest.fixture
def holds():
    return Holds()


@pytest.fixture
def deals():
    return Deals()


class Ends:
    """The end command as the presence calls it: what it was asked, and what it answers or raises next.

    A call records who was connected when the presence entered its context, or None when the presence had stopped
    or the check was superseded.
    """

    def __init__(self):
        self.calls = []
        self.outcomes = []
        self.failures = []
        self.ended = True
        self.meanwhile = None
        self.within = None
        self.due_now = []
        self.due_failures = []

    async def due(self):
        if self.due_failures:
            raise self.due_failures.pop(0)
        return list(self.due_now)

    async def end(self, table_id, connected_accounts):
        if self.failures:
            raise self.failures.pop(0)
        if self.meanwhile is not None:
            await self.meanwhile()
        connected = await on_a_worker(connected_accounts, lambda yielded: yielded, self.within)
        self.calls.append((table_id, connected))
        outcome = self.ended and connected == frozenset()
        self.outcomes.append(outcome)
        if connected is not None and table_id in self.due_now:
            self.due_now.remove(table_id)
        return outcome


@pytest.fixture
def lapses():
    return Lapses()


@pytest.fixture
def ends():
    return Ends()


@pytest.fixture
def leases():
    return InMemoryLeases()


@pytest.fixture
def elsewhere(leases):
    """The other pod of `holding`: it holds streams on the same leases and runs no timer."""
    return idle_presence(leases=leases)


@pytest.fixture
def holding(time, holds, deals, ends, leases):
    return presence_on(time, holds, deals, ends, leases=leases)


@pytest.fixture
def hold(sign_in_settings):
    return sign_in_settings()


@pytest.fixture
def server(hold, time):
    """`create_app`'s own wiring and its own routes; only the clock and the timers run on the test's time."""
    skat = Skat(lambda: hold, chair_clock=time.clock, chair_scheduler=time)
    with skat.client:
        yield skat


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


@pytest.fixture
def sdk(skat, issuer):
    return MemberClient(skat, issuer)


@pytest.fixture
def pulses(changes):
    """Every change the app told, as (account, uri), in the order told."""
    return changes.told


@pytest.fixture
def eight_cards(herz_hand):
    herz_hand.played_out(EIGHT_CARDS)
    return herz_hand


@pytest.fixture
def waiting(skat, issuer):
    """The agent in seat 1 and the person in seat 3 sit at a hand that waits for seat 2."""
    table = WaitingTable(skat, issuer)
    table.send_the_second_agent_away()
    return table
