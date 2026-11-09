import pytest

from skat.web.presence import NEXT_DEAL_PAUSE_SECONDS, ChairHold, NextDeal, Presence
from tests.web.support.presence import HOLD_SECONDS, Deals, Releases, Wakes
from tests.web.support.skat import FakeTime, Skat


@pytest.fixture
def skat(sign_in_settings):
    return Skat(sign_in_settings)


@pytest.fixture
def wakes():
    return Wakes()


@pytest.fixture
def time():
    return FakeTime()


@pytest.fixture
def releases():
    return Releases()


@pytest.fixture
def deals():
    return Deals()


@pytest.fixture
def holding(time, releases, deals):
    return Presence(
        ChairHold(HOLD_SECONDS, time.clock, time, releases.free_chair),
        NextDeal(NEXT_DEAL_PAUSE_SECONDS, deals.deal_next),
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
