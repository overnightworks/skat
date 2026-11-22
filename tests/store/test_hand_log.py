"""The hand log's codec: each step a command takes extends the log or, where the hand's end forgets its steps, empties
it, and the log with the hand's standing state decodes to the hand's progress and traces.
"""

from dataclasses import replace

import pytest

from skat.store.hand_log import StepKind, decoded, encoded
from tests.support.hand_log_scenes import LogAfter, a_dealt_table, scene_on, scenes, stepped

SCENES = {scene.name: scene for scene in scenes()}
STEPS = {f"{scene.name}, then {step.name}": (scene, step) for scene in SCENES.values() for step in scene.next_steps}


def scene_table(scene):
    return scene_on(scene, a_dealt_table(scene.options))


@pytest.mark.parametrize(("scene", "step"), STEPS.values(), ids=STEPS.keys())
def test_the_log_after_a_step_extends_the_log_before_or_empties_where_the_hand_forgets_its_steps(scene, step):
    before = scene_table(scene)
    after = stepped(before, step)

    log_before, log_after = encoded(before), encoded(after)

    match step.log_after:
        case LogAfter.EXTENDS:
            assert log_after[: len(log_before)] == log_before
            assert len(log_after) >= len(log_before)
        case LogAfter.EMPTIES:
            assert log_after == ()
        case LogAfter.STARTS_OVER:
            assert [row.kind for row in log_after] == [StepKind.DEAL]


@pytest.mark.parametrize("scene", SCENES.values(), ids=SCENES.keys())
def test_the_log_with_the_standing_state_decodes_to_the_hands_progress_and_traces(scene):
    table = scene_table(scene)
    standing = replace(table.progress, auction=(), pushing=(), declaring=(), plays=(), words=())

    decoding = decoded(encoded(table), standing, table.traces.ending)

    assert decoding == (table.progress, replace(table.traces, version=None))


def _without_rank(row):
    return replace(row, rank=None) if row.kind is StepKind.CARD else row


def _pass_with_a_value(row):
    return replace(row, kind=StepKind.PASS, value=18) if row.kind is StepKind.BID else row


def _bid_without_a_value(row):
    return replace(row, value=None) if row.kind is StepKind.BID else row


def _card_without_a_position(row):
    return replace(row, position=None) if row.kind is StepKind.CARD else row


def _declare_without_a_game(row):
    return replace(row, game=None) if row.kind is StepKind.DECLARE else row


def _word_without_a_word(row):
    return replace(row, word=None) if row.kind is StepKind.WORD else row


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (_without_rank, "card without its suit or rank"),
        (_pass_with_a_value, "pass step carries a value"),
        (_bid_without_a_value, "bid step names no value"),
        (_card_without_a_position, "card step names no position"),
        (_declare_without_a_game, "declare step names no whole game"),
        (_word_without_a_word, "word step names no word"),
    ],
    ids=[
        "a card without its rank",
        "a pass with a value",
        "a bid without a value",
        "a card without a position",
        "a declare without a game",
        "a word without a word",
    ],
)
def test_a_stored_step_whose_payload_misfits_its_kind_decodes_loud(broken, message):
    table = scene_table(SCENES["cards with words, a word after the last card"])
    log = tuple(broken(row) for row in encoded(table))

    with pytest.raises(ValueError, match=message):
        decoded(log, table.progress, table.traces.ending)
