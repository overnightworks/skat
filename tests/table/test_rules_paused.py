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
from tests.support.played_game import declared_herz_hand, table_in


@pytest.fixture
def running():
    return table_in(declared_herz_hand())


@pytest.fixture
def waiting(running):
    return replace(running, hand=None)


def raised(table):
    return replace(table, version=table.version + 1)


class TestAStepOfPlay:
    @pytest.mark.parametrize(
        "command", [PLAY_CARD_COMMAND, GIVE_UP_COMMAND, AGREE_TO_GIVE_UP_COMMAND, THROW_DOWN_COMMAND]
    )
    def test_a_play_command_that_changed_the_table_is_one(self, running, command):
        assert is_deal_or_step_of_play(command, running, raised(running)) is True

    @pytest.mark.parametrize(
        "command", [PLAY_CARD_COMMAND, GIVE_UP_COMMAND, AGREE_TO_GIVE_UP_COMMAND, THROW_DOWN_COMMAND]
    )
    def test_a_play_command_that_changed_nothing_is_none(self, running, command):
        assert is_deal_or_step_of_play(command, running, running) is False

    @pytest.mark.parametrize(
        "command",
        [
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
        ],
    )
    def test_a_bid_a_declaration_a_kontra_word_and_the_other_commands_are_none_while_the_hand_runs(
        self, running, command
    ):
        assert is_deal_or_step_of_play(command, running, raised(running)) is False


class TestADeal:
    def test_a_decision_after_which_a_hand_runs_that_did_not_before_is_one(self, waiting, running):
        assert is_deal_or_step_of_play(SIT_DOWN_COMMAND, waiting, raised(running)) is True

    def test_a_decision_after_which_no_hand_runs_is_none(self, waiting):
        assert is_deal_or_step_of_play(SIT_DOWN_COMMAND, waiting, raised(waiting)) is False

    def test_the_hand_that_ends_by_a_third_pass_is_none(self, running, waiting):
        assert is_deal_or_step_of_play(AUCTION_STEP_COMMAND, running, raised(waiting)) is False
