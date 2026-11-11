from dataclasses import replace

import pytest

from skat.engine.bock import BockRounds
from skat.table.records import Series
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import cards_in_text, with_known_deal
from tests.support.played_game import a_ramsch_entry
from tests.web.support.playing import (
    FOREHAND,
    HERZ_GAME,
    JUNGFRAU_DEAL,
    JUNGFRAU_HAND,
    MIDDLEHAND,
    PLAIN_DEAL,
    PLAIN_HAND,
    REARHAND,
    SWEEP_DEAL,
    SWEEP_HAND,
    Table,
)
from tests.web.support.series import deal_next, headers_of, tap_new_series, tap_weiter
from tests.web.support.skat import Skat


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


POINTS = {"occasion": "passed-in", "scoring": "points", "jungfrau": "doubles-loser", "durchmarsch": "wins-120"}
EVERY_TRIGGER_BUT_PASSED_IN = ("sixty-sixty", "won-grand-hand", "lost-after-kontra", "re", "schneider", "schwarz")
# Seats 1, 2 and 3 are middlehand, rearhand and forehand: the plain deal's rearhand takes 86 points.
A_ROUND_STARTS = {"games_left": 3, "factor": 2}
NO_ROUND = {"games_left": 0, "factor": 1}


def options_of(*triggers, overlap="append", **ramsch_changed):
    return {
        "ramsch": {**POINTS, **ramsch_changed},
        "bock": {"triggers": list(triggers), "overlap": overlap},
    }


def seat_scores_of(result):
    return [seat["score"] for seat in result["seats"]]


def three_pass(table):
    for position in (MIDDLEHAND, REARHAND, FOREHAND):
        table.passes(position)


def with_pending(table, *rounds):
    table.skat.store.tables[table.table_id] = replace(table.record, bock=BockRounds(rounds))


def with_totals(table, *seat_scores):
    """The list holds one earlier Ramsch whose seats scored `seat_scores`, so the totals start there."""
    accounts = tuple(chair.occupant.account_id for chair in sorted(table.record.chairs, key=lambda chair: chair.seat))
    earlier = a_ramsch_entry(seat_scores, accounts)
    table.skat.store.tables[table.table_id] = replace(table.record, game_list=(earlier,))


def ramsch_table(
    skat, *triggers, deal=PLAIN_DEAL, overlap="append", pending=(), totals=None, series=None, **ramsch_changed
):
    table = Table(skat, options_of(*triggers, overlap=overlap, **ramsch_changed))
    if deal is not None:
        table.with_deal(deal)
    if pending:
        with_pending(table, *pending)
    if totals is not None:
        with_totals(table, *totals)
    if series is not None:
        skat.store.tables[table.table_id] = replace(table.record, series=series)
    return table


def played_ramsch(table, hand=PLAIN_HAND):
    three_pass(table)
    table.played_out(hand)
    return table


def read(table, position=None):
    headers = table.watcher if position is None else table.at[position]
    return table.read_as(headers).json()


def bock_of(table):
    return read(table)["bock"]


def list_rows(table):
    table.skat.client.cookies.clear()
    answer = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher)
    assert answer.status_code == 200, answer.text
    return answer.json()["entries"]


def next_hand(table):
    """Everyone taps „Weiter“ after the game, then the next hand is dealt: PLAIN_DEAL, which all three pass."""
    skat, people = table.skat, headers_of(table)
    games = len(table.record.game_list)
    for chair in table.record.chairs:
        answer = tap_weiter(skat, people[chair.seat - 1], table.table_id, f"weiter-{games}-{chair.seat}", games)
        assert answer.status_code == 200, answer.text
    assert deal_next(skat, table.table_id, [chair.occupant.account_id for chair in table.record.chairs])
    with_known_deal(skat, table.table_id)
    table.with_deal(PLAIN_DEAL)


class TestOpeningATableWithRamschAndBock:
    def test_the_answer_carries_both_and_a_retry_is_the_first_table_while_other_options_are_refused(self, skat):
        headers, _ = skat.member()
        options = options_of("passed-in")

        first = skat.create(headers, options=options)
        same = skat.create(headers, options=options)
        other = skat.create(headers, options=options_of("re"))

        assert first.status_code == 200
        answered = first.json()["options"]
        assert (answered["ramsch"], answered["bock"]) == (
            POINTS,
            {"triggers": ["passed-in"], "overlap": "append"},
        )
        assert (same.json()["id"], other.status_code) == (first.json()["id"], 409)


class TestAnAgentOpeningATableWithRamschAndBock:
    def test_open_table_takes_both_and_answers_them(self, skat, agent):
        agent.admitted()

        opened = agent.open_table(options=options_of("re"))

        assert opened.json()["options"]["ramsch"] == POINTS
        assert opened.json()["options"]["bock"] == {"triggers": ["re"], "overlap": "append"}


class TestWhatARamschInABockGameScores:
    @pytest.mark.parametrize(
        ("deal", "hand", "overlap", "pending", "ramsch_changed", "scores", "factor"),
        [
            pytest.param(PLAIN_DEAL, PLAIN_HAND, "append", (), {}, [0, -86, 0], 1, id="outside-a-bock-game"),
            pytest.param(PLAIN_DEAL, PLAIN_HAND, "append", (2,), {}, [0, -172, 0], 2, id="in-a-bock-game"),
            pytest.param(
                PLAIN_DEAL, PLAIN_HAND, "multiply", (2, 2), {}, [0, -344, 0], 4, id="in-two-multiplied-rounds"
            ),
            pytest.param(
                PLAIN_DEAL, PLAIN_HAND, "append", (2,), {"scoring": "points-by-ten"}, [0, -16, 0], 2, id="by-ten-first"
            ),
            pytest.param(JUNGFRAU_DEAL, JUNGFRAU_HAND, "append", (2,), {}, [-404, 0, 0], 2, id="jungfrau-then-bock"),
            pytest.param(
                JUNGFRAU_DEAL,
                JUNGFRAU_HAND,
                "append",
                (2,),
                {"scoring": "points-by-ten"},
                [-40, 0, 0],
                2,
                id="by-ten-then-jungfrau-then-bock",
            ),
            pytest.param(SWEEP_DEAL, SWEEP_HAND, "append", (2,), {}, [0, 0, 240], 2, id="a-sweep-is-multiplied"),
            pytest.param(
                SWEEP_DEAL,
                SWEEP_HAND,
                "append",
                (2,),
                {"durchmarsch": "wins-120-flat"},
                [0, 0, 120],
                2,
                id="a-flat-sweep-is-not",
            ),
        ],
    )
    def test_the_result_the_row_and_the_totals_carry_the_multiplied_scores_and_the_factor(
        self, skat, deal, hand, overlap, pending, ramsch_changed, scores, factor
    ):
        table = played_ramsch(
            ramsch_table(skat, "passed-in", deal=deal, overlap=overlap, pending=pending, **ramsch_changed), hand
        )

        for position in (FOREHAND, MIDDLEHAND, REARHAND, None):
            result = read(table, position)["result"]
            assert (seat_scores_of(result), result["bock_factor"]) == (scores, factor)
        row = list_rows(table)[0]
        assert ([seat["score"] for seat in row["seats"]], row["bock_factor"]) == (scores, factor)
        assert [chair["total"] for chair in read(table)["chairs"]] == scores
        assert not cards_in_text(table.read_as(table.watcher).text)

    def test_a_declared_game_and_a_ramsch_in_one_round_are_both_multiplied_and_each_uses_a_game_up(self, skat):
        table = ramsch_table(skat, "passed-in", deal=None, pending=(3,))
        table.declared_hand_game()
        table.played_out(HERZ_GAME)
        declared_factor = read(table)["result"]["bock_factor"]
        after_the_declared_game = bock_of(table)

        next_hand(table)
        played_ramsch(table)

        assert (declared_factor, after_the_declared_game) == (2, {"games_left": 2, "factor": 2})
        assert (read(table)["result"]["bock_factor"], seat_scores_of(read(table)["result"])) == (2, [0, -172, 0])
        assert bock_of(table) == {"games_left": 4, "factor": 2}

    def test_the_hand_stays_and_the_bock_games_stay_pending_when_the_third_pass_comes(self, skat):
        table = ramsch_table(skat, "passed-in", pending=(2,))
        before = bock_of(table)

        three_pass(table)

        answer = read(table, MIDDLEHAND)
        assert (answer["hand"]["ramsch"], answer["bock"]) == (True, before)
        assert before == {"games_left": 2, "factor": 2}


class TestWhatARamschStartsAndUsesUp:
    @pytest.mark.parametrize(
        ("triggers", "overlap", "pending", "expected"),
        [
            pytest.param(("passed-in",), "append", (), A_ROUND_STARTS, id="starts-a-round"),
            pytest.param(
                ("passed-in",), "append", (2,), {"games_left": 4, "factor": 2}, id="appends-after-the-pending"
            ),
            pytest.param(("passed-in",), "multiply", (2,), {"games_left": 3, "factor": 4}, id="multiplies-the-rounds"),
            pytest.param(("passed-in",), "ignore", (2,), {"games_left": 1, "factor": 2}, id="ignores-inside-a-round"),
            pytest.param(EVERY_TRIGGER_BUT_PASSED_IN, "append", (), NO_ROUND, id="no-other-trigger-starts-one"),
            pytest.param(
                EVERY_TRIGGER_BUT_PASSED_IN,
                "append",
                (2,),
                {"games_left": 1, "factor": 2},
                id="no-other-trigger-uses-the-game-up-only",
            ),
        ],
    )
    def test_passed_in_starts_a_round_at_the_hand_end_by_the_overlap_and_no_other_trigger_does(
        self, skat, triggers, overlap, pending, expected
    ):
        table = played_ramsch(ramsch_table(skat, *triggers, overlap=overlap, pending=pending))

        assert bock_of(table) == expected

    @pytest.mark.parametrize(
        ("deal", "hand"),
        [
            pytest.param(SWEEP_DEAL, SWEEP_HAND, id="a-sweep"),
            pytest.param(JUNGFRAU_DEAL, JUNGFRAU_HAND, id="a-jungfrau"),
        ],
    )
    def test_a_sweep_and_a_jungfrau_are_no_schneider_and_no_schwarz(self, skat, deal, hand):
        table = played_ramsch(ramsch_table(skat, "schneider", "schwarz", deal=deal), hand)

        assert bock_of(table) == NO_ROUND

    @pytest.mark.parametrize(
        ("triggers", "totals", "expected"),
        [
            pytest.param(("total-ending-in-00",), (0, 186, 0), A_ROUND_STARTS, id="a-total-moved-to-100"),
            pytest.param(("total-ending-in-00",), (0, -14, 0), A_ROUND_STARTS, id="moved-to-minus-100"),
            pytest.param(("total-ending-in-00",), (0, 0, 0), NO_ROUND, id="a-total-moved-to-minus-86"),
            pytest.param(("total-ending-in-00",), (100, 0, 0), NO_ROUND, id="a-seat-the-ramsch-left-at-100"),
            pytest.param(("passed-in", "total-ending-in-00"), (0, 186, 0), A_ROUND_STARTS, id="both-start-one-round"),
        ],
    )
    def test_the_total_rule_reads_what_the_ramsch_changed_and_two_triggers_start_one_round(
        self, skat, triggers, totals, expected
    ):
        table = played_ramsch(ramsch_table(skat, *triggers, totals=totals))

        assert bock_of(table) == expected

    def test_three_ramsch_hands_in_a_row_each_fire_and_append_after_the_pending_rounds(self, skat):
        table = ramsch_table(skat, "passed-in")
        played_ramsch(table)
        after_the_first = bock_of(table)
        next_hand(table)
        played_ramsch(table)
        after_the_second = bock_of(table)
        next_hand(table)
        played_ramsch(table)

        assert (after_the_first, after_the_second, bock_of(table)) == (
            {"games_left": 3, "factor": 2},
            {"games_left": 5, "factor": 2},
            {"games_left": 7, "factor": 2},
        )
        assert table.record.bock == BockRounds((1, 3, 3))


class TestARamschEndingTheSeriesOrNearIt:
    def test_the_last_game_stores_its_factor_and_lets_every_round_lapse(self, skat):
        table = played_ramsch(ramsch_table(skat, "passed-in", pending=(2,), series=Series(3, 3)))

        assert (read(table)["result"]["bock_factor"], bock_of(table), table.record.bock) == (
            2,
            NO_ROUND,
            BockRounds(()),
        )
        assert list_rows(table)[0]["bock_factor"] == 2

    def test_a_new_series_after_it_deals_with_no_pending_round(self, skat):
        table = played_ramsch(ramsch_table(skat, "passed-in", pending=(2,), series=Series(3, 3)))
        for number, headers in enumerate(headers_of(table), start=1):
            assert tap_new_series(skat, headers, table.table_id, f"new-series-{number}").status_code == 200

        assert deal_next(skat, table.table_id, [chair.occupant.account_id for chair in table.record.chairs])

        assert (bock_of(table), table.record.bock) == (NO_ROUND, BockRounds(()))

    def test_the_round_a_second_to_last_game_starts_is_capped_to_the_games_the_series_deals(self, skat):
        table = played_ramsch(ramsch_table(skat, "passed-in", series=Series(3, 2)))

        assert bock_of(table) == {"games_left": 1, "factor": 2}
