from contextlib import nullcontext
from dataclasses import replace

from skat.engine.deal import positions_from
from skat.table.records import Series, TableId
from skat.table.service import TableService
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, with_known_deal
from tests.support.played_game import a_whole_game
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import Table


def tap_weiter(skat, headers, table_id, command_id, ordinal=1):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_READY_SUFFIX}",
        json={"command_id": command_id, "ordinal": ordinal},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def headers_of(table):
    """The headers of the three people at the table, in seat order."""
    position_of = positions_from(DEALER_SEAT)
    return [table.at[position_of[seat]] for seat in (1, 2, 3)]


def pass_the_hand_in(skat, table):
    """Everyone passes in turn until no hand runs."""
    people = headers_of(table)
    for _ in range(3):
        view = table.read_as(table.watcher).json()
        if view["hand"] is None:
            break
        answer = skat.client.post(
            f"{TABLES_PATH}/{table.table_id}{TABLE_AUCTION_PASS_SUFFIX}",
            json={"command_id": f"pass-at-{view['version']}", "version": view["version"]},
            headers={"origin": TEST_PUBLIC_ORIGIN, **people[view["hand"]["auction"]["turn_seat"] - 1]},
        )
        assert answer.status_code == 200, answer.text
    assert table.read_as(table.watcher).json()["hand"] is None


def play_a_series(skat, game_count=3, *, swap_after_first=None, passed_in_hand=None):
    """A series of `game_count` hands, each played card by card, with Weiter and the next deal between them.

    `swap_after_first` is a seat whose person stands up after the first game for the table's watcher.
    `passed_in_hand` is the number of a hand everyone passes in instead of playing; it leaves no list row.
    Returns the table and the display names of the three people who first sat.
    """
    table = Table(skat)
    skat.store.tables[table.table_id] = replace(table.record, series=Series(game_count, 1))
    first_names = [chair.occupant.display_name for chair in table.record.chairs]
    for game in range(1, game_count + 1):
        if game == passed_in_hand:
            pass_the_hand_in(skat, table)
        else:
            table.declared_hand_game()
            table.played_out(each.card for each in a_whole_game(table.record))
        if game == game_count:
            break
        if game == 1 and swap_after_first is not None:
            position = positions_from(DEALER_SEAT)[swap_after_first]
            stood = skat.stand(table.at[position], table.table_id, command_id="stand-for-swap")
            assert stood.status_code == 200, stood.text
            assert (
                skat.sit(table.watcher, table.table_id, swap_after_first, command_id="sit-for-swap").status_code == 200
            )
            table.at[position] = table.watcher
        for chair in table.record.chairs if game != passed_in_hand else ():
            if not chair.ready:
                position = positions_from(DEALER_SEAT)[chair.seat]
                answer = tap_weiter(skat, table.at[position], table.table_id, f"weiter-{game}-{chair.seat}", game)
                assert answer.status_code == 200, answer.text
        accounts = frozenset(chair.occupant.account_id for chair in table.record.chairs)
        assert TableService(skat.store).deal_next(TableId(table.table_id), nullcontext(accounts))
        with_known_deal(skat, table.table_id)
    return table, first_names
