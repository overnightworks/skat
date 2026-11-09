import asyncio
from contextlib import contextmanager

from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.support.played_game import after_the_first_game
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN

TABLE = "t" * 32
OTHER_TABLE = "o" * 32
HOLD_SECONDS = 300
FAILURE_NAMING_AN_ACCOUNT = "account anna"
NAMED_FAILURE = ("error", "ConnectionError")
THIRD_PASS_COMMAND = "pass-seat-3"


def view_of_version(messages, version):
    return next(view for view in messages if view["version"] >= version)


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
        f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_PASS_SUFFIX}",
        json={"command_id": command_id, "version": version},
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


def end_the_first_game(store, table_id, *ready_seats):
    store.tables[table_id] = after_the_first_game(store.tables[table_id], *ready_seats)
    return store.tables[table_id]


class OvertakenStore(FakeTableStore):
    """A store another caller overtakes: `meanwhile` runs once when the next row lock is asked, `after_commit` once
    when the next transaction has committed, `after_commit_of_command` once when the transaction that recorded the
    receipt of the named command has committed, whatever other transactions commit before it."""

    def __init__(self):
        super().__init__()
        self.meanwhile = None
        self.after_commit = None
        self.after_commit_of_command = None
        self._command_recorded = False

    @contextmanager
    def begin(self):
        with super().begin() as transaction:
            yield transaction
        if self.after_commit is not None:
            action, self.after_commit = self.after_commit, None
            action()
        if self._command_recorded:
            self._command_recorded = False
            action, self.after_commit_of_command = self.after_commit_of_command[1], None
            action()

    def add_receipt(self, receipt):
        super().add_receipt(receipt)
        if self.after_commit_of_command is not None and receipt.command_id == self.after_commit_of_command[0]:
            self._command_recorded = True

    def locked_table(self, table_id):
        if self.meanwhile is not None:
            action, self.meanwhile = self.meanwhile, None
            action()
        return super().locked_table(table_id)
