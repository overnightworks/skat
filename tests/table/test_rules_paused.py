from dataclasses import replace

import pytest

from skat.table.auction import AUCTION_STEP_COMMAND
from skat.table.declaring import DECLARING_STEP_COMMAND
from skat.table.kontra import KONTRA_COMMAND
from skat.table.ready import NEW_SERIES_COMMAND, READY_COMMAND
from skat.table.rules import (
    AGREE_TO_GIVE_UP_COMMAND,
    DECLINE_GIVE_UP_COMMAND,
    GIVE_UP_COMMAND,
    PLAY_CARD_COMMAND,
    SIT_DOWN_COMMAND,
    STAND_UP_COMMAND,
    THROW_DOWN_COMMAND,
    is_deal_or_step_of_play,
)
from skat.table.series_end import AGREE_TO_END_SERIES_COMMAND, REFUSE_TO_END_SERIES_COMMAND
from tests.support.open_chairs import before_the_first_card

running = pytest.fixture(name="running")(before_the_first_card)


@pytest.fixture
def waiting(running):
    return replace(running, hand=None)


def raised(table):
    return replace(table, version=table.version + 1)


PLAY_COMMANDS = [PLAY_CARD_COMMAND, GIVE_UP_COMMAND, AGREE_TO_GIVE_UP_COMMAND, THROW_DOWN_COMMAND]
OTHER_COMMANDS = [
    AUCTION_STEP_COMMAND,
    DECLARING_STEP_COMMAND,
    KONTRA_COMMAND,
    DECLINE_GIVE_UP_COMMAND,
    READY_COMMAND,
    NEW_SERIES_COMMAND,
    AGREE_TO_END_SERIES_COMMAND,
    REFUSE_TO_END_SERIES_COMMAND,
    STAND_UP_COMMAND,
    SIT_DOWN_COMMAND,
]


class TestAStepOfPlay:
    @pytest.mark.parametrize(
        ("command", "is_a_step"),
        [*((command, True) for command in PLAY_COMMANDS), *((command, False) for command in OTHER_COMMANDS)],
    )
    def test_a_play_command_that_changed_the_table_is_one_and_a_bid_a_declaration_or_any_other_is_none(
        self, running, command, is_a_step
    ):
        assert is_deal_or_step_of_play(command, running, raised(running)) is is_a_step

    @pytest.mark.parametrize("command", PLAY_COMMANDS)
    def test_a_play_command_that_changed_nothing_is_none(self, running, command):
        assert is_deal_or_step_of_play(command, running, running) is False


class TestADeal:
    def test_a_decision_after_which_a_hand_runs_that_did_not_before_is_one(self, waiting, running):
        assert is_deal_or_step_of_play(SIT_DOWN_COMMAND, waiting, raised(running)) is True

    def test_a_decision_after_which_no_hand_runs_is_none(self, waiting):
        assert is_deal_or_step_of_play(SIT_DOWN_COMMAND, waiting, raised(waiting)) is False

    def test_the_hand_that_ends_by_a_third_pass_is_none(self, running, waiting):
        assert is_deal_or_step_of_play(AUCTION_STEP_COMMAND, running, raised(waiting)) is False
