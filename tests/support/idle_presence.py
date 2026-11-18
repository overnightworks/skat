from agents.member import LEASE_SECONDS

from skat.web.presence import NEXT_DEAL_PAUSE_SECONDS, AgentLease, ChairHold, EmptyTable, NextDeal, Presence
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from skat.web.wakes import Topic, WakeList
from tests.support.in_memory_leases import InMemoryLeases


class IdleScheduler:
    """A scheduler that never runs anything, for tests that do not look at the chair hold."""

    def schedule(self, delay, action):
        pass

    def cancel_all(self):
        pass


async def store_no_leave(table_id, account_id):
    pass


async def clear_no_hold(table_id, account_id):
    pass


async def nothing_due():
    return []


async def free_no_chair(table_id, account_id, absent):
    return False


async def seat_nowhere(account_id):
    return []


async def deal_no_hand(table_id, connected_accounts):
    return False


async def end_no_table(table_id, connected_accounts):
    return False


async def note_nothing(table_id, connected_accounts):
    return False


def idle_empty_table() -> EmptyTable:
    return EmptyTable(DEFAULT_EMPTY_TABLE_SECONDS, end_no_table, note_nothing)


def idle_next_deal() -> NextDeal:
    return NextDeal(NEXT_DEAL_PAUSE_SECONDS, deal_no_hand)


def idle_hold(clock=lambda: 0.0, scheduler=None) -> ChairHold:
    """A chair hold whose store keeps nothing, on `clock` and `scheduler`, which by default runs nothing."""
    return ChairHold(
        clock, scheduler or IdleScheduler(), store_no_leave, store_no_leave, clear_no_hold, nothing_due, free_no_chair
    )


def idle_agent_lease() -> AgentLease:
    return AgentLease(LEASE_SECONDS, seat_nowhere)


def publish_nowhere(_topic: Topic) -> None:
    """Tells no other pod."""


def idle_wakes() -> WakeList:
    """The wakes of a deployment of one pod: nothing is told to other pods."""
    return WakeList(publish_nowhere)


def idle_presence(wakes: WakeList | None = None, leases: InMemoryLeases | None = None) -> Presence:
    return Presence(
        idle_hold(),
        idle_next_deal(),
        idle_empty_table(),
        idle_agent_lease(),
        wakes or idle_wakes(),
        leases or InMemoryLeases(),
    )
