from agents.member import LEASE_SECONDS

from skat.web.presence import NEXT_DEAL_PAUSE_SECONDS, AgentLease, ChairHold, EmptyTable, NextDeal, Presence
from skat.web.settings import DEFAULT_EMPTY_TABLE_SECONDS
from skat.web.wakes import WakeList


class IdleScheduler:
    """A scheduler that never runs anything, for tests that do not look at the chair hold."""

    def schedule(self, delay, action):
        pass

    def cancel_all(self):
        pass


async def free_no_chair(table_id, account_id, due):
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


def idle_hold() -> ChairHold:
    return ChairHold(300, lambda: 0.0, IdleScheduler(), free_no_chair)


def idle_agent_lease() -> AgentLease:
    return AgentLease(LEASE_SECONDS, seat_nowhere)


def idle_presence(wakes: WakeList | None = None) -> Presence:
    return Presence(idle_hold(), idle_next_deal(), idle_empty_table(), idle_agent_lease(), wakes or WakeList())
