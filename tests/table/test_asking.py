"""A seat the table waits for is asked again after a pause: how many asks are due after a wait, and the revision a
reader of the seat's view sees for a version and a count of asks.
"""

import pytest

from skat.table.asking import ASK_AGAIN_AFTER, ASKS_AGAIN, asks_due, revision_of

WAITING_SINCE = 1000.0


class TestAsksDue:
    @pytest.mark.parametrize(
        ("waited", "asks"),
        [
            pytest.param(0, 0, id="at-the-start"),
            pytest.param(ASK_AGAIN_AFTER - 1, 0, id="just-before-the-first-deadline"),
            pytest.param(ASK_AGAIN_AFTER, 1, id="at-the-first-deadline"),
            pytest.param(2 * ASK_AGAIN_AFTER - 1, 1, id="just-before-the-second-deadline"),
            pytest.param(2 * ASK_AGAIN_AFTER, 2, id="at-the-second-deadline"),
            pytest.param(2 * ASK_AGAIN_AFTER + 1, 2, id="after-the-second-deadline"),
            pytest.param(1000 * ASK_AGAIN_AFTER, ASKS_AGAIN, id="far-past-the-cap"),
        ],
    )
    def test_the_asks_due_rise_by_one_at_each_full_pause_and_stop_at_the_cap(self, waited, asks):
        assert asks_due(WAITING_SINCE, WAITING_SINCE + waited) == asks

    def test_a_time_before_the_start_of_the_wait_has_no_asks_due(self):
        assert asks_due(WAITING_SINCE, WAITING_SINCE - ASK_AGAIN_AFTER) == 0


class TestRevisionOf:
    def test_one_version_and_one_count_give_the_same_revision(self):
        assert revision_of(7, 1) == revision_of(7, 1)

    def test_every_count_of_a_version_stays_below_the_next_version(self):
        highest = max(revision_of(7, asks) for asks in range(ASKS_AGAIN + 1))

        assert highest < revision_of(8, 0)

    def test_the_counts_of_one_version_are_different_revisions_in_order(self):
        revisions = [revision_of(7, asks) for asks in range(ASKS_AGAIN + 1)]

        assert revisions == sorted(set(revisions))
