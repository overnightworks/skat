import random
from contextlib import nullcontext
from dataclasses import replace

from skat.engine.deal import positions_from
from skat.table.records import Series, TableId
from skat.table.service import TableService
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.ready import TABLE_NEW_SERIES_SUFFIX, TABLE_READY_SUFFIX
from skat.web.series_end import TABLE_SERIES_END_AGREE_SUFFIX, TABLE_SERIES_END_REFUSE_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, with_known_deal
from tests.support.played_game import a_whole_game
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import Table


def tap_weiter(skat, headers, table_id, command_id, ordinal=1, series=1):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_READY_SUFFIX}",
        json={"command_id": command_id, "ordinal": ordinal, "series": series},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def tap_new_series(skat, headers, table_id, command_id, series=1):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_NEW_SERIES_SUFFIX}",
        json={"command_id": command_id, "series": series},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def agree_to_end(skat, headers, table_id, command_id):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_SERIES_END_AGREE_SUFFIX}",
        json={"command_id": command_id},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def refuse_to_end(skat, headers, table_id, command_id):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_SERIES_END_REFUSE_SUFFIX}",
        json={"command_id": command_id},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def headers_of(table):
    """The headers of the three people at the table, in seat order."""
    position_of = positions_from(DEALER_SEAT)
    return [table.at[position_of[seat]] for seat in (1, 2, 3)]


def pass_the_hand_in(skat, table_id, people_headers):
    """Everyone passes in turn until no hand runs; `people_headers` are the three people's, in seat order."""

    def view():
        return skat.client.get(f"{TABLES_PATH}/{table_id}", headers=people_headers[0]).json()

    for _ in range(3):
        current = view()
        if current["hand"] is None:
            break
        answer = skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_PASS_SUFFIX}",
            json={"command_id": f"pass-at-{current['version']}", "version": current["version"]},
            headers={"origin": TEST_PUBLIC_ORIGIN, **people_headers[current["hand"]["auction"]["turn_seat"] - 1]},
        )
        assert answer.status_code == 200, answer.text
    assert view()["hand"] is None


def deal_next(skat, table_id, accounts):
    """The service's deal step for a table whose `accounts` are connected, from a seeded source."""
    service = TableService(skat.store, random_source=random.Random(3))  # noqa: S311 - a seeded source makes the deal reproducible
    return service.deal_next(TableId(table_id), nullcontext(frozenset(accounts)))


def play_a_series(skat, game_count=3, *, swap_after_first=None, passed_in_hand=None, games_to_play=None):
    """A series of `game_count` hands, each played card by card, with Weiter and the next deal between them.

    `games_to_play` stops the play after that many games, at the last one's pending result or, for a passed-in hand,
    right after the pass.

    `swap_after_first` is a seat whose person stands up after the first game for the table's watcher.
    `passed_in_hand` is the number of a hand everyone passes in instead of playing; it leaves no list row.
    Returns the table and the display names of the three people who first sat.
    """
    table = Table(skat)
    skat.store.tables[table.table_id] = replace(table.record, series=Series(game_count, 1))
    first_names = [chair.occupant.display_name for chair in table.record.chairs]
    play_the_dealt_series(
        skat,
        table,
        game_count,
        swap_after_first=swap_after_first,
        passed_in_hand=passed_in_hand,
        games_to_play=games_to_play,
    )
    return table, first_names


def deal_the_next_game(skat, table, number, game, *, after_pass=False):
    """Every chair not yet ready taps Weiter on game `game` of series `number`, unless everyone passed it in, then the
    next game is dealt.
    """
    for chair in table.record.chairs if not after_pass else ():
        if not chair.ready:
            position = positions_from(DEALER_SEAT)[chair.seat]
            command_id = f"weiter-{number}-{game}-{chair.seat}"
            answer = tap_weiter(skat, table.at[position], table.table_id, command_id, game, number)
            assert answer.status_code == 200, answer.text
    accounts = [chair.occupant.account_id for chair in table.record.chairs]
    assert deal_next(skat, table.table_id, accounts)
    with_known_deal(skat, table.table_id)


def play_the_dealt_series(
    skat,
    table,
    game_count,
    *,
    number=1,
    swap_after_first=None,
    passed_in_hand=None,
    games_to_play=None,
    deal_after_last=False,
):
    """Play series `number`, whose first game is dealt, to its last game's end; options as in `play_a_series`.

    `deal_after_last` also taps Weiter and deals the game that follows the last, which the caller then plays itself.
    """
    for game in range(1, game_count + 1):
        if game == passed_in_hand:
            pass_the_hand_in(skat, table.table_id, headers_of(table))
        else:
            table.declared_hand_game()
            table.played_out(each.card for each in a_whole_game(table.record))
        if game in (game_count, games_to_play):
            break
        if game == 1 and swap_after_first is not None:
            position = positions_from(DEALER_SEAT)[swap_after_first]
            stood = skat.stand(table.at[position], table.table_id, command_id="stand-for-swap")
            assert stood.status_code == 200, stood.text
            assert (
                skat.sit(table.watcher, table.table_id, swap_after_first, command_id="sit-for-swap").status_code == 200
            )
            table.at[position] = table.watcher
        deal_the_next_game(skat, table, number, game, after_pass=game == passed_in_hand)
    if deal_after_last:
        deal_the_next_game(skat, table, number, game)
