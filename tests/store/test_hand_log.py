"""The hand log's codec: each step a command takes extends the log or, where the hand's end forgets its steps, empties
it, and the log with the hand's standing state decodes to the hand's progress and traces.
"""

from dataclasses import replace

import pytest

from skat.store.hand_log import StepKind, decoded, encoded
from tests.support.hand_log_scenes import LogAfter, a_dealt_table, scene_on, scenes, stepped

SCENES = {scene.name: scene for scene in scenes(a_dealt_table())}
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

    decoding = decoded(encoded(table), table.progress, table.traces.ending)

    assert decoding == (table.progress, replace(table.traces, version=None))


def test_a_stored_card_without_its_rank_decodes_loud():
    table = scene_table(SCENES["cards with words, a word after the last card"])
    broken = tuple(replace(row, rank=None) if row.kind is StepKind.CARD else row for row in encoded(table))

    with pytest.raises(ValueError, match="card without its suit or rank"):
        decoded(broken, table.progress, table.traces.ending)
