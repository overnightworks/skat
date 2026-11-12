import pytest

from skat.web.wakes import Topic, WakeList
from tests.web.support.presence import Wakes

FIRST_TABLE = Topic("a" * 32)
SECOND_TABLE = Topic("b" * 32)


@pytest.fixture
def wakes():
    return Wakes()


class TestWakeList:
    def test_a_wake_reaches_the_registrations_of_its_topic_and_no_other(self, wakes):
        wake_list = WakeList()
        wake_list.register([FIRST_TABLE], wakes.callback("first"))
        wake_list.register([FIRST_TABLE], wakes.callback("also first"))
        wake_list.register([SECOND_TABLE], wakes.callback("second"))

        wake_list.wake(FIRST_TABLE)

        assert wakes.counts == {"first": 1, "also first": 1, "second": 0}

    def test_a_wake_spares_the_registration_it_names(self, wakes):
        wake_list = WakeList()
        spared = wake_list.register([FIRST_TABLE], wakes.callback("spared"))
        wake_list.register([FIRST_TABLE], wakes.callback("other"))

        wake_list.wake(FIRST_TABLE, sparing=spared)

        assert wakes.counts == {"spared": 0, "other": 1}

    def test_an_unregistered_registration_is_no_longer_woken(self, wakes):
        wake_list = WakeList()
        ended = wake_list.register([FIRST_TABLE, SECOND_TABLE], wakes.callback("ended"))
        wake_list.register([FIRST_TABLE], wakes.callback("kept"))

        wake_list.unregister(ended)
        wake_list.wake(FIRST_TABLE)
        wake_list.wake(SECOND_TABLE)

        assert wakes.counts == {"ended": 0, "kept": 1}

    def test_wake_all_reaches_every_registration_once(self, wakes):
        wake_list = WakeList()
        wake_list.register([FIRST_TABLE, SECOND_TABLE], wakes.callback("both"))
        wake_list.register([SECOND_TABLE], wakes.callback("second"))

        wake_list.wake_all()

        assert wakes.counts == {"both": 1, "second": 1}
