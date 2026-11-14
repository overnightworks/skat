"""The lobby stream sends every member the open tables with their free chairs, never a private one."""

import json
from contextlib import nullcontext

from skat.table.records import Actor, TableId, Visibility
from tests.web.support.lobby_scene import ANNA, BEN, CLEO, DORA, Scene, ids_of, next_mine, next_open
from tests.web.support.streams import run_on_a_loop_of_its_own

OPEN_ENTRY_FIELDS = {
    "id",
    "title_name",
    "game_number",
    "game_count",
    "options",
    "watchers",
    "free_chairs",
    "dealt",
    "waiting_seat",
    "ends_at",
    "chairs",
}
OPEN_CHAIR_FIELDS = {"seat", "occupant_name", "occupant_kind", "is_away", "hold_seconds_left"}


class TestTheOpenList:
    def test_a_member_with_no_chair_gets_the_open_tables_with_their_free_chairs_and_the_opener_gets_none_of_his_own(
        self,
    ):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            bens, annas = scene.open_stream(BEN), scene.open_stream(ANNA)
            seen = await next_open(bens), await next_open(annas)
            await bens.aclose()
            await annas.aclose()
            return seen

        bens, annas = run_on_a_loop_of_its_own(scenario())

        assert (ids_of(bens), [chair["occupant_name"] for chair in bens[0]["chairs"]], bens[0]["free_chairs"]) == (
            [table_id],
            ["Anna", None, None],
            2,
        )
        assert annas == []

    def test_a_private_table_is_in_no_open_list_and_in_the_opener_s_mine_with_a_lock(self):
        scene = Scene()
        table_id = scene.open_table(ANNA, Visibility.PRIVATE)

        async def scenario():
            bens, annas = scene.open_stream(BEN), scene.stream(ANNA)
            seen = await next_open(bens), await next_mine(annas)
            await bens.aclose()
            await annas.aclose()
            return seen

        bens, annas = run_on_a_loop_of_its_own(scenario())

        assert (bens, [(entry["id"], entry["private"]) for entry in annas]) == ([], [(table_id, True)])

    def test_a_private_table_stays_out_of_the_open_list_after_a_sit_and_a_deal(self):
        scene = Scene()
        table_id = scene.open_table(ANNA, Visibility.PRIVATE)
        scene.sit(BEN, table_id, 2)
        scene.sit(CLEO, table_id, 3)

        async def scenario():
            strangers, annas, bens = scene.open_stream(DORA), scene.stream(ANNA), scene.stream(BEN)
            seen = await next_open(strangers), await next_mine(annas), await next_mine(bens)
            await strangers.aclose()
            await annas.aclose()
            await bens.aclose()
            return seen

        strangers, annas, bens = run_on_a_loop_of_its_own(scenario())

        assert (strangers, [entry["private"] for entry in annas], [entry["private"] for entry in bens]) == (
            [],
            [True],
            [True],
        )

    def test_an_open_table_is_not_marked_private_in_mine(self):
        scene = Scene()
        scene.open_table(ANNA)

        async def scenario():
            stream = scene.stream(ANNA)
            mine = await next_mine(stream)
            await stream.aclose()
            return mine

        assert [entry["private"] for entry in run_on_a_loop_of_its_own(scenario())] == [False]

    def test_the_list_follows_a_table_opened_a_sit_a_stand_up_a_close_and_an_end(self):
        scene = Scene()

        async def scenario():
            stream = scene.open_stream(CLEO)
            seen = [await next_open(stream)]
            table_id = scene.open_table(ANNA)
            seen.append(await next_open(stream))
            scene.sit(BEN, table_id, 2)
            seen.append(await next_open(stream))
            scene.stand(BEN, table_id)
            seen.append(await next_open(stream))
            scene.close(ANNA, table_id)
            seen.append(await next_open(stream))
            ended = scene.open_table(ANNA)
            seen.append(await next_open(stream))
            assert scene.service.end_empty_table(TableId(ended), nullcontext(frozenset()), 0)
            scene.presence.wake_table(ended)
            seen.append(await next_open(stream))
            await stream.aclose()
            return table_id, ended, seen

        table_id, ended, seen = run_on_a_loop_of_its_own(scenario())

        assert [ids_of(tables) for tables in seen] == [[], [table_id], [table_id], [table_id], [], [ended], []]
        assert [[chair["occupant_name"] for chair in tables[0]["chairs"]] for tables in seen[1:4]] == [
            ["Anna", None, None],
            ["Anna", "Ben", None],
            ["Anna", None, None],
        ]

    def test_a_table_a_member_sits_at_leaves_his_open_list_and_joins_his_mine(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            open_list, mine = scene.open_stream(BEN), scene.stream(BEN)
            before = await next_open(open_list), await next_mine(mine)
            scene.sit(BEN, table_id, 2)
            after = await next_open(open_list), await next_mine(mine)
            await open_list.aclose()
            await mine.aclose()
            return before, after

        before, after = run_on_a_loop_of_its_own(scenario())

        assert ([ids_of(each) for each in before], [ids_of(each) for each in after]) == (
            [[table_id], []],
            [[], [table_id]],
        )

    def test_a_table_with_a_free_chair_is_listed_before_a_full_one(self):
        scene = Scene()
        full = scene.open_table(ANNA)
        scene.sit(BEN, full, 2)
        scene.sit(CLEO, full, 3)
        free = scene.open_table(ANNA)

        async def scenario():
            stream = scene.open_stream(Actor(account_id="account-dora", display_name="Dora"))
            listed = await next_open(stream)
            await stream.aclose()
            return listed

        listed = run_on_a_loop_of_its_own(scenario())

        assert [(entry["id"], entry["free_chairs"]) for entry in listed] == [(free, 2), (full, 0)]

    def test_an_away_member_at_an_undealt_open_table_shows_the_seconds_left_of_the_hold_from_presence(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)
        scene.presence.hold_chairs([(table_id, ANNA.account_id)])

        async def scenario():
            stream = scene.open_stream(BEN)
            listed = await next_open(stream)
            await stream.aclose()
            return listed

        (entry,) = run_on_a_loop_of_its_own(scenario())

        assert [(chair["is_away"], chair["hold_seconds_left"]) for chair in entry["chairs"]] == [
            (True, 300),
            (False, None),
            (False, None),
        ]

    def test_the_open_entry_carries_the_series_the_options_and_the_watchers_and_no_card_or_account(self):
        scene = Scene()
        table_id = scene.open_table(ANNA)

        async def scenario():
            await scene.presence.subscribe(table_id, CLEO.account_id, lambda: None)
            stream = scene.open_stream(BEN)
            listed = await next_open(stream)
            await stream.aclose()
            return listed

        (entry,) = run_on_a_loop_of_its_own(scenario())

        assert set(entry) == OPEN_ENTRY_FIELDS
        assert all(set(chair) == OPEN_CHAIR_FIELDS for chair in entry["chairs"])
        assert (entry["id"], entry["watchers"], entry["options"]["show_running_points"]) == (table_id, 1, False)
        assert CLEO.account_id not in json.dumps(entry)
