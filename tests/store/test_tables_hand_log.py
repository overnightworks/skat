"""Both stores of a hand, written by this release and by the releases beside it, read back the hand over every scene.

The release before writes the step tables and the table row's hand columns alone; the release after writes the hand
log alone. Each is built from today's writers, never from SQL repeated here: the shared rows, then its own store.
"""

from dataclasses import replace

import pytest
from sqlalchemy import delete, func, select

from skat.store.hand_log import hand_steps, hands, save_hand_log, stamped_hand
from skat.store.tables import save_shared, save_step_tables
from skat.table.records import EndedTable, TableId
from tests.support.hand_log_scenes import scene_on, scenes, traced
from tests.support.seated_tables import ended_at, save, undealt_table
from tests.support.stored_game import seated_table_id

pytestmark = pytest.mark.postgres

SCENES = {scene.name: scene for scene in scenes()}
DEALT_SCENES = {name: scene for name, scene in SCENES.items() if scene.dealt}


def release_0_saves(engine, table):
    with engine.begin() as connection:
        moment = save_shared(connection, table, None)
        save_step_tables(connection, table, moment, rewrite=False)


def release_2_saves(engine, table):
    with engine.begin() as connection:
        moment = save_shared(connection, table, None)
        save_hand_log(connection, table, rewrite=moment.dealt or moment.forgot)


def read_by_release_0(engine, transactions, stored, table_id):
    """The table as the release before reads it: from the old store, as it does not know the `hands` row."""
    with engine.begin() as connection:
        connection.execute(delete(hands).where(hands.c.table_id == table_id))
    return stored(transactions, table_id)


def is_stamped(engine, table_id):
    with engine.connect() as connection:
        return stamped_hand(connection, table_id) is not None


def held(table):
    """What the stores of a hand hold of the table: its progress and the traces of its version, steps and end."""
    return table.progress, table.traces


@pytest.fixture(params=SCENES.values(), ids=SCENES.keys())
def scene(request):
    return request.param


@pytest.fixture(params=DEALT_SCENES.values(), ids=DEALT_SCENES.keys())
def dealt_scene(request):
    return request.param


def base_of(service, transactions, stored, scene):
    table_id = seated_table_id(service, scene.options) if scene.dealt else undealt_table(service, "undealt").value
    return stored(transactions, table_id)


def test_release_0s_write_reads_back_through_the_old_store(service, transactions, stored, engine, scene):
    table = scene_on(scene, base_of(service, transactions, stored, scene))

    release_0_saves(engine, table)

    assert (is_stamped(engine, table.id.value), held(stored(transactions, table.id.value))) == (False, held(table))


def test_release_1s_write_reads_back_through_the_reader_of_the_release_before(
    service, transactions, stored, engine, scene
):
    table = scene_on(scene, base_of(service, transactions, stored, scene))

    save(transactions, table)

    assert held(read_by_release_0(engine, transactions, stored, table.id.value)) == held(table)


def test_release_1s_write_reads_back_through_the_stamped_log(service, transactions, stored, engine, scene):
    table = scene_on(scene, base_of(service, transactions, stored, scene))

    save(transactions, table)

    assert (is_stamped(engine, table.id.value), held(stored(transactions, table.id.value))) == (
        scene.dealt,
        held(table),
    )


@pytest.mark.parametrize("other_release_saves", [release_0_saves, release_2_saves], ids=["release-0", "release-2"])
def test_a_save_after_another_release_ended_a_hand_and_dealt_the_next_reads_back_through_both_stores(
    service, transactions, stored, engine, dealt_scene, other_release_saves
):
    base = base_of(service, transactions, stored, dealt_scene)
    bid = scene_on(SCENES["mid-auction"], base)
    save(transactions, bid)
    aborted = scene_on(SCENES["aborted, between hands"], bid)
    other_release_saves(engine, aborted)
    other_release_saves(engine, scene_on(dealt_scene, replace(aborted, hand=base.hand)))
    moved = stored(transactions, base.id.value)
    table = traced(replace(moved, version=moved.version + 1))

    save(transactions, table)

    assert (
        is_stamped(engine, table.id.value),
        held(stored(transactions, table.id.value)),
        held(read_by_release_0(engine, transactions, stored, table.id.value)),
    ) == (True, held(table), held(table))


def test_the_end_of_a_table_forgets_its_hand_log(service, transactions, stored, engine, dealt_scene):
    table = scene_on(dealt_scene, base_of(service, transactions, stored, dealt_scene))
    save(transactions, table)

    ended_at(transactions, TableId(table.id.value))

    with engine.connect() as connection:
        counts = [
            connection.execute(
                select(func.count()).select_from(each).where(each.c.table_id == table.id.value)
            ).scalar_one()
            for each in (hand_steps, hands)
        ]
    assert (counts, type(stored(transactions, table.id.value))) == ([0, 0], EndedTable)
