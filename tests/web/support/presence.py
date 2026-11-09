import asyncio
from contextlib import contextmanager

from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN

TABLE = "t" * 32
OTHER_TABLE = "o" * 32
HOLD_SECONDS = 300
FAILURE_NAMING_AN_ACCOUNT = "account anna"
NAMED_FAILURE = ("error", "ConnectionError")
THIRD_PASS_COMMAND = "pass-seat-3"


class Wakes:
    """What each subscriber was told: one counter per name."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def callback(self, name):
        self.counts.setdefault(name, 0)

        def wake():
            self.counts[name] += 1

        return wake


class Releases:
    """The freeing command as the presence calls it: what it was asked, and what it answers or raises next."""

    def __init__(self):
        self.calls = []
        self.failures = []
        self.freed = True
        self.meanwhile = None
        self.within = None
        self.outcomes = []

    async def free_chair(self, table_id, account_id, due):
        self.calls.append((table_id, account_id))
        if self.failures:
            raise self.failures.pop(0)
        if self.meanwhile is not None:
            await self.meanwhile()
        with due as still_due:
            outcome = self.freed and still_due
            if self.within is not None:
                await self.within()
        self.outcomes.append(outcome)
        return outcome


class Deals:
    """The deal command as the presence calls it: what it was asked, and what it answers or raises next."""

    def __init__(self):
        self.calls = []
        self.failures = []
        self.dealt = True
        self.meanwhile = None

    async def deal_next(self, table_id, connected_accounts):
        if self.failures:
            raise self.failures.pop(0)
        if self.meanwhile is not None:
            await self.meanwhile()
        with connected_accounts as connected:
            self.calls.append((table_id, connected))
        return self.dealt


def run(scenario):
    return asyncio.run(scenario)


def connect(presence, table_id, account_id, wake):
    return run(presence.subscribe(table_id, account_id, wake))


def post_pass(skat, table_id, headers, *, command_id, version):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_SUFFIX}",
        json={"command_id": command_id, "version": version, "action": "pass"},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def pass_hand_in(skat, table_id, people, seats_in_turn=(1, 2, 3)):
    """By default in `seated_three`'s turn: it dealt seat 1 the middlehand, seat 2 the rearhand, seat 3 the forehand."""
    for seat in seats_in_turn:
        version = skat.store.tables[table_id].version
        answer = post_pass(skat, table_id, people[seat - 1][0], command_id=f"pass-at-{version}", version=version)
        assert answer.status_code == 200, answer.text


def occupied_seats(skat, table_id):
    return {chair.seat for chair in skat.store.tables[table_id].chairs if chair.occupant is not None}


class OvertakenStore(FakeTableStore):
    """A store another caller overtakes: `meanwhile` runs once when the next row lock is asked, `after_commit` once
    when the next transaction has committed."""

    def __init__(self):
        super().__init__()
        self.meanwhile = None
        self.after_commit = None

    @contextmanager
    def begin(self):
        with super().begin() as transaction:
            yield transaction
        if self.after_commit is not None:
            action, self.after_commit = self.after_commit, None
            action()

    def locked_table(self, table_id):
        if self.meanwhile is not None:
            action, self.meanwhile = self.meanwhile, None
            action()
        return super().locked_table(table_id)
