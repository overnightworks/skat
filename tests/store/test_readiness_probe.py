import asyncio

import pytest
from structlog.testing import capture_logs

from skat.store.migrate import READINESS_REUSE_SECONDS, DatabaseHealth, ReadinessProbe

READY = DatabaseHealth(serves_queries=True, at_head=True)
UNREACHABLE = DatabaseHealth(serves_queries=False, at_head=False)
NOT_AT_HEAD = DatabaseHealth(serves_queries=True, at_head=False)
BURST_SIZE = 50


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class ScriptedDatabase:
    """Stands in for the probe against a database whose health the test sets."""

    def __init__(self) -> None:
        self.health = READY
        self.probes_started = 0
        self.probes_running = 0
        self.most_probes_running = 0

    def probe(self) -> DatabaseHealth:
        self.probes_started += 1
        self.probes_running += 1
        self.most_probes_running = max(self.most_probes_running, self.probes_running)
        health = self.health
        self.probes_running -= 1
        return health


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def database() -> ScriptedDatabase:
    return ScriptedDatabase()


@pytest.fixture
def readiness(database, clock) -> ReadinessProbe:
    return ReadinessProbe(database.probe, clock=clock)


async def burst(readiness: ReadinessProbe) -> list[bool]:
    return await asyncio.gather(*(readiness() for _ in range(BURST_SIZE)))


class TestReadinessProbe:
    def test_a_burst_of_asks_is_answered_by_one_probe(self, readiness, database):
        verdicts = asyncio.run(burst(readiness))

        assert (verdicts, database.probes_started, database.most_probes_running) == ([True] * BURST_SIZE, 1, 1)

    def test_a_burst_during_a_probe_gets_that_probes_verdict(self, readiness, database):
        database.health = UNREACHABLE

        assert asyncio.run(burst(readiness)) == [False] * BURST_SIZE

    def test_a_second_ask_within_the_reuse_time_costs_no_probe(self, readiness, database, clock):
        asyncio.run(readiness())
        clock.now += READINESS_REUSE_SECONDS / 2
        asyncio.run(readiness())

        assert database.probes_started == 1

    @pytest.mark.parametrize("health", [UNREACHABLE, NOT_AT_HEAD], ids=["unreachable", "not-at-head"])
    def test_the_verdict_turns_unready_and_ready_again_after_the_reuse_time(self, readiness, database, clock, health):
        before = asyncio.run(readiness())
        database.health = health
        clock.now += READINESS_REUSE_SECONDS
        stopped = asyncio.run(readiness())
        database.health = READY
        clock.now += READINESS_REUSE_SECONDS
        recovered = asyncio.run(readiness())

        assert (before, stopped, recovered) == (True, False, True)

    def test_a_probe_after_the_reuse_time_is_a_new_one_at_a_time_again(self, readiness, database, clock):
        asyncio.run(burst(readiness))
        clock.now += READINESS_REUSE_SECONDS
        asyncio.run(burst(readiness))

        assert (database.probes_started, database.most_probes_running) == (2, 1)


class TestReadinessLogging:
    def test_a_changed_verdict_is_logged_once_with_its_cause(self, readiness, database, clock):
        asyncio.run(readiness())
        database.health = NOT_AT_HEAD
        clock.now += READINESS_REUSE_SECONDS

        with capture_logs() as logs:
            asyncio.run(burst(readiness))

        assert [(entry["event"], entry["was"], entry["now"]) for entry in logs] == [
            ("database_readiness_changed", "ready", "not_at_head")
        ]

    def test_a_steady_verdict_logs_nothing(self, readiness, clock):
        with capture_logs() as logs:
            for _ in range(3):
                asyncio.run(readiness())
                clock.now += READINESS_REUSE_SECONDS

        assert logs == []

    def test_a_verdict_that_stays_unready_is_logged_only_when_it_first_turned(self, readiness, database, clock):
        database.health = UNREACHABLE

        with capture_logs() as logs:
            for _ in range(3):
                asyncio.run(readiness())
                clock.now += READINESS_REUSE_SECONDS

        assert [(entry["was"], entry["now"]) for entry in logs] == [("ready", "unreachable")]
