import pytest

from skat.engine.deal import Position
from tests.web.support.playing import HERZ_GAME, PLAIN_DEAL, PLAIN_HAND, Table, three_pass

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
EVERY_VIEWER = [
    pytest.param(MIDDLEHAND, id="declarer"),
    pytest.param(FOREHAND, id="forehand"),
    pytest.param(REARHAND, id="rearhand"),
    pytest.param(None, id="watcher"),
]


@pytest.fixture
def table(skat):
    return Table(skat)


def taken_as_read(table, viewer):
    headers = table.watcher if viewer is None else table.at[viewer]
    return table.read_as(headers).json()["hand"]["playing"]["taken"]


def counts(*tricks):
    return [{"seat": seat, "tricks": each} for seat, each in enumerate(tricks, start=1)]


class TestTheTricksEachSeatTook:
    @pytest.mark.parametrize("viewer", EVERY_VIEWER)
    @pytest.mark.parametrize(
        ("cards_played", "tricks"),
        [
            pytest.param(0, (0, 0, 0), id="none-before-the-first-card"),
            pytest.param(3, (1, 0, 0), id="one-after-the-first-trick"),
            pytest.param(6, (1, 0, 1), id="two-seats-after-the-second-trick"),
            pytest.param(7, (1, 0, 1), id="a-trick-in-progress-counts-for-nobody"),
            pytest.param(26, (6, 1, 1), id="after-eight-tricks"),
            pytest.param(29, (6, 2, 1), id="with-the-last-card-due"),
        ],
    )
    def test_a_suit_game_counts_the_tricks_taken_so_far(self, table, viewer, cards_played, tricks):
        table.declared_hand_game()
        table.played_out(HERZ_GAME[:cards_played])

        assert taken_as_read(table, viewer) == counts(*tricks)

    @pytest.mark.parametrize("viewer", EVERY_VIEWER)
    def test_a_ramsch_counts_the_tricks_each_seat_took_with_zero_for_the_others(self, skat, viewer):
        ramsch = {"occasion": "passed-in", "scoring": "points", "jungfrau": "doubles-loser", "durchmarsch": "wins-120"}
        table = Table(skat, {"ramsch": ramsch})
        table.with_deal(PLAIN_DEAL)
        three_pass(table)
        table.played_out(PLAIN_HAND[:12])

        assert taken_as_read(table, viewer) == counts(0, 4, 0)
