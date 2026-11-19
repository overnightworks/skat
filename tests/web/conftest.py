import pytest

from skat.engine.deal import Position
from skat.web.presence import NEXT_DEAL_PAUSE_SECONDS, EmptyTable, NextDeal, Presence
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from tests.support.fake_issuer import FakeIssuer
from tests.support.idle_presence import idle_agent_lease, idle_presence, idle_wakes, note_nothing
from tests.support.in_memory_leases import InMemoryLeases
from tests.web.support.agent import Agent
from tests.web.support.presence import Deals, Holds, Lapses, Wakes, chair_hold, on_a_worker
from tests.web.support.skat import AgentTable, FakeTime, Skat

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

    async def end(self, table_id, connected_accounts):
        if self.failures:
            raise self.failures.pop(0)
        if self.meanwhile is not None:
            await self.meanwhile()
        connected = await on_a_worker(connected_accounts, lambda yielded: yielded, self.within)
        self.calls.append((table_id, connected))
        outcome = self.ended and connected is not None
        self.outcomes.append(outcome)
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
    return Presence(
        chair_hold(time, holds),
        NextDeal(NEXT_DEAL_PAUSE_SECONDS, deals.deal_next),
        EmptyTable(DEFAULT_EMPTY_TABLE_SECONDS, ends.end, note_nothing),
        idle_agent_lease(),
        idle_wakes(),
        leases,
    )


@pytest.fixture
def hold(sign_in_settings):
    return sign_in_settings()


@pytest.fixture
def server(hold, time):
    """`create_app`'s own wiring and its own routes; only the clock and the timers run on the test's time."""
    skat = Skat(lambda: hold, chair_clock=time.clock, chair_scheduler=time)
    with skat.client:
        yield skat
