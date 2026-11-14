from dataclasses import replace

import pytest

from skat.engine.bock import BockRounds
from skat.table.records import Series
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.mcp import (
    AUCTION_PASS_TOOL,
    RAMSCH_DECLARE_GRAND_HAND_TOOL,
    RAMSCH_PUSH_SKAT_TOOL,
)
from skat.web.pushing import TABLE_PUSHING_PUSH_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import cards_in_text, with_known_deal
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
    bock_of,
    three_pass,
    with_pending,
    with_totals,
)
from tests.web.support.ramsch_stage import accepted, play_stage, stage_table
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


def options_of(*triggers, occasion="passed-in"):
    return {"ramsch": {**POINTS, "occasion": occasion}, "bock": {"triggers": list(triggers), "overlap": "append"}}


def seat_scores_of(result):
    return [seat["score"] for seat in result["seats"]]


def ramsch_table(
    skat, *triggers, occasion="passed-in", deal=PLAIN_DEAL, pending=(), ramsch_games=0, totals=None, series=None
):
    table = Table(skat, options_of(*triggers, occasion=occasion))
    if deal is not None:
        table.with_deal(deal)
    if pending or ramsch_games:
        with_pending(table, *pending, ramsch_games=ramsch_games)
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
            {**POINTS, "pushing": None},
            {"triggers": ["passed-in"], "overlap": "append"},
        )
        assert (same.json()["id"], other.status_code) == (first.json()["id"], 409)


class TestAnAgentOpeningATableWithRamschAndBock:
    def test_open_table_takes_both_and_answers_them(self, skat, agent):
        agent.admitted()

        opened = agent.open_table(options=options_of("re"))

        assert opened.json()["options"]["ramsch"] == {**POINTS, "pushing": None}
        assert opened.json()["options"]["bock"] == {"triggers": ["re"], "overlap": "append"}


class TestWhatARamschInABockGameScores:
    def test_the_result_the_row_and_the_totals_carry_the_multiplied_score_and_the_factor(self, skat):
        table = played_ramsch(ramsch_table(skat, "passed-in", pending=(2,)))

        for position in (FOREHAND, MIDDLEHAND, REARHAND, None):
            result = read(table, position)["result"]
            assert (seat_scores_of(result), result["bock_factor"]) == ([0, -172, 0], 2)
        row = list_rows(table)[0]
        assert ([seat["score"] for seat in row["seats"]], row["bock_factor"]) == ([0, -172, 0], 2)
        assert [chair["total"] for chair in read(table)["chairs"]] == [0, -172, 0]
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
        ("triggers", "pending", "expected"),
        [
            pytest.param(("passed-in",), (), A_ROUND_STARTS, id="passed-in-starts-a-round"),
            pytest.param(
                EVERY_TRIGGER_BUT_PASSED_IN,
                (2,),
                {"games_left": 1, "factor": 2},
                id="no-other-trigger-uses-a-game",
            ),
        ],
    )
    def test_passed_in_starts_a_round_at_the_hand_end_and_no_other_trigger_does(
        self, skat, triggers, pending, expected
    ):
        table = played_ramsch(ramsch_table(skat, *triggers, pending=pending))

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

    def test_the_total_rule_reads_the_totals_the_ramsch_itself_moved_to_100(self, skat):
        table = played_ramsch(ramsch_table(skat, "total-ending-in-00", totals=(0, 186, 0)))

        assert bock_of(table) == A_ROUND_STARTS

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


ROUND_OCCASIONS = ["bock-rounds", "passed-in-and-bock-rounds"]


def hand_of(table, position=MIDDLEHAND):
    return read(table, position)["hand"]


class TestOpeningATableWithRamschRounds:
    @pytest.mark.parametrize("occasion", ["passed-in", "bock-rounds", "passed-in-and-bock-rounds"])
    def test_the_answer_carries_the_occasion_and_a_retry_is_the_first_table(self, skat, occasion):
        headers, _ = skat.member()
        options = options_of("re", occasion=occasion)

        first = skat.create(headers, options=options)
        same = skat.create(headers, options=options)

        assert first.status_code == 200
        assert first.json()["options"]["ramsch"]["occasion"] == occasion
        assert same.json()["id"] == first.json()["id"]


class TestAHandDealtInARamschRound:
    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_is_a_ramsch_with_no_auction_while_a_ramsch_round_game_is_pending(self, skat, occasion):
        table = ramsch_table(skat, "re", occasion=occasion, ramsch_games=2)

        answer = hand_of(table)

        assert (answer["ramsch"], answer["auction"]["awaiting"], answer["auction"]["words"]) == (True, None, [])

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_takes_no_auction_step(self, skat, occasion):
        table = ramsch_table(skat, "re", occasion=occasion, ramsch_games=2)
        before = table.record

        answer = table.act(TABLE_AUCTION_PASS_SUFFIX, table.at[MIDDLEHAND])

        assert (answer.status_code, table.record) == (409, before)

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_plays_out_as_a_ramsch_that_uses_a_ramsch_round_game_up_and_carries_no_bock_factor(self, skat, occasion):
        table = ramsch_table(skat, "re", occasion=occasion, ramsch_games=3)

        table.played_out(PLAIN_HAND)

        result = read(table)["result"]
        assert (seat_scores_of(result), result["bock_factor"], bock_of(table), table.record.bock) == (
            [0, -86, 0],
            1,
            NO_ROUND,
            BockRounds((), 2),
        )

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_meets_no_passed_in_trigger_since_nobody_passed_so_the_rounds_do_not_chain(self, skat, occasion):
        table = ramsch_table(skat, "passed-in", occasion=occasion, ramsch_games=3)

        table.played_out(PLAIN_HAND)

        assert table.record.bock == BockRounds((), 2)

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_still_meets_the_total_trigger_and_its_bock_round_comes_before_the_ramsch_games_left(self, skat, occasion):
        table = ramsch_table(skat, "total-ending-in-00", occasion=occasion, ramsch_games=3, totals=(0, 186, 0))

        table.played_out(PLAIN_HAND)

        assert (table.record.bock, bock_of(table)) == (BockRounds((3,), 2), A_ROUND_STARTS)

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_the_series_last_game_lets_every_round_lapse(self, skat, occasion):
        table = ramsch_table(skat, "re", occasion=occasion, ramsch_games=3, series=Series(3, 3))

        table.played_out(PLAIN_HAND)

        assert (read(table)["result"]["bock_factor"], table.record.bock) == (1, BockRounds(()))

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_follows_game_after_game_until_the_ramsch_round_is_used_up_and_then_runs_an_auction(self, skat, occasion):
        table = ramsch_table(skat, "re", occasion=occasion, ramsch_games=2)
        table.played_out(PLAIN_HAND)
        next_hand(table)
        second = hand_of(table)["ramsch"]
        table.played_out(PLAIN_HAND)
        next_hand(table)

        after_the_round = hand_of(table)

        assert (second, after_the_round["ramsch"], after_the_round["auction"]["awaiting"]) == (True, False, "bid")
        assert table.record.bock == BockRounds(())

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_waits_for_the_bock_games_pending_which_are_dealt_with_their_auction(self, skat, occasion):
        table = ramsch_table(skat, "re", occasion=occasion, pending=(2,), ramsch_games=3)

        answer = hand_of(table)

        assert (answer["ramsch"], answer["auction"]["awaiting"]) == (False, "bid")


class TestABockRoundThatEnds:
    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    @pytest.mark.parametrize(
        ("pending", "ramsch_games", "expected"),
        [
            pytest.param((3,), 0, BockRounds((2,), 0), id="a-game-before-the-end-adds-none"),
            pytest.param((1,), 0, BockRounds((), 3), id="its-last-game-adds-three-ramsch-round-games"),
            pytest.param((1,), 2, BockRounds((), 5), id="and-three-to-those-still-pending"),
        ],
    )
    def test_its_bock_game_keeps_its_auction_and_the_round_adds_three_ramsch_games_after_its_last(
        self, skat, occasion, pending, ramsch_games, expected
    ):
        table = ramsch_table(skat, "re", occasion=occasion, deal=None, pending=pending, ramsch_games=ramsch_games)
        table.declared_hand_game()
        table.played_out(HERZ_GAME)

        assert (read(table)["result"]["bock_factor"], table.record.bock) == (2, expected)

    def test_the_third_pass_of_a_table_with_both_that_plays_the_last_bock_game_as_a_ramsch_adds_three_too(self, skat):
        table = ramsch_table(skat, "re", occasion="passed-in-and-bock-rounds", pending=(1,))

        played_ramsch(table)

        assert (read(table)["result"]["bock_factor"], table.record.bock) == (2, BockRounds((), 3))

    def test_a_table_with_the_third_pass_alone_adds_none(self, skat):
        table = ramsch_table(skat, "re", occasion="passed-in", deal=None, pending=(1,))
        table.declared_hand_game()
        table.played_out(HERZ_GAME)

        assert table.record.bock == BockRounds(())


class TestAHandOutsideARamschRound:
    @pytest.mark.parametrize(
        ("occasion", "pending", "ramsch_games"),
        [
            pytest.param("passed-in", (2,), 0, id="third-pass-only-with-a-round-pending"),
            pytest.param("bock-rounds", (), 0, id="rounds-only-with-no-round-pending"),
            pytest.param("passed-in-and-bock-rounds", (), 0, id="both-with-no-round-pending"),
        ],
    )
    def test_runs_an_auction(self, skat, occasion, pending, ramsch_games):
        table = ramsch_table(skat, "re", occasion=occasion, pending=pending, ramsch_games=ramsch_games)

        answer = hand_of(table)

        assert (answer["ramsch"], answer["auction"]["awaiting"]) == (False, "bid")

    def test_the_third_pass_of_a_ramsch_rounds_only_table_passes_the_hand_in(self, skat):
        table = ramsch_table(skat, "passed-in", occasion="bock-rounds")

        three_pass(table)

        assert (table.record.hand, bock_of(table)) == (None, A_ROUND_STARTS)

    def test_the_third_pass_of_a_table_with_both_starts_a_ramsch_that_meets_passed_in_as_under_the_third_pass_alone(
        self, skat
    ):
        table = ramsch_table(skat, "passed-in", occasion="passed-in-and-bock-rounds")

        three_pass(table)
        assert hand_of(table)["ramsch"] is True
        table.played_out(PLAIN_HAND)

        assert table.record.bock == BockRounds((3,))


def ramsch_round_stage_table(skat, *triggers, ramsch_games=2, deal=PLAIN_DEAL, grand_hand=None):
    """A table of Ramsch rounds whose stage of takes and pushes runs at once in a hand dealt as a Ramsch round."""
    pushing = {"rule": "jacks-stay", **({} if grand_hand is None else {"grand_hand": grand_hand})}
    options = options_of(*triggers, occasion="bock-rounds")
    options["ramsch"]["pushing"] = pushing
    table = Table(skat, options)
    table.with_deal(deal)
    with_pending(table, ramsch_games=ramsch_games)
    return table


class TestPushingAndAGrandHandInARamschRound:
    def test_the_stage_runs_and_the_game_is_reckoned_as_at_a_three_pass_ramsch_of_the_same_table(self, skat):
        plan = ("push", "back", "push")
        table = ramsch_round_stage_table(skat, "re")
        play_stage(table, *plan)
        table.played_out(PLAIN_HAND)
        same_after_the_third_pass = stage_table(skat, extra={"bock": options_of("re")["bock"]})
        play_stage(same_after_the_third_pass, *plan)
        same_after_the_third_pass.played_out(PLAIN_HAND)

        assert table.result() == same_after_the_third_pass.result()
        assert (table.result()["pushes"], table.record.bock) == (2, BockRounds((), 1))

    def test_a_grand_hand_instead_of_the_ramsch_wins_and_starts_its_bock_round_before_the_ramsch_games_left(self, skat):
        table = ramsch_round_stage_table(skat, "won-grand-hand", deal=JUNGFRAU_DEAL, grand_hand="allowed")
        play_stage(table, "push")
        accepted(table, MIDDLEHAND, "grand-hand")

        table.played_out(JUNGFRAU_HAND)

        result = table.result()
        assert (result["kind"], result["hand"], result["bock_factor"]) == ("declared", True, 1)
        assert (table.record.bock, bock_of(table)) == (BockRounds((3,), 1), A_ROUND_STARTS)

    def test_the_bock_round_a_grand_hand_started_is_dealt_with_auctions_before_the_ramsch_games_left(self, skat):
        table = ramsch_round_stage_table(skat, "won-grand-hand", deal=JUNGFRAU_DEAL, grand_hand="allowed")
        play_stage(table, "push")
        accepted(table, MIDDLEHAND, "grand-hand")
        table.played_out(JUNGFRAU_HAND)

        next_hand(table)

        assert (hand_of(table)["ramsch"], hand_of(table)["auction"]["awaiting"]) == (False, "bid")


class AgentRoundTable(Table):
    """The agent opens a table of Ramsch rounds and holds seat 1, the middlehand; two people sit at seats 2 and 3, and
    the hand is dealt as a Ramsch-round game with `ramsch_games` of them pending.
    """

    def __init__(self, skat, agent, occasion, *, pushing=None, ramsch_games=2):
        self.skat = skat
        self._commands = iter(range(1, 1000))
        agent_headers = agent.admitted()
        options = options_of("re", occasion=occasion)
        if pushing is not None:
            options["ramsch"]["pushing"] = pushing
        self.table_id = agent.open_table(options=options).json()["id"]
        people = [skat.member() for _ in range(3)]
        for seat, (headers, _) in zip((2, 3), people[:2], strict=True):
            skat.sit(headers, self.table_id, seat, command_id=f"command-sit-{seat}")
        with_known_deal(skat, self.table_id)
        self.with_deal(PLAIN_DEAL)
        with_pending(self, ramsch_games=ramsch_games)
        self.at = {MIDDLEHAND: agent_headers, REARHAND: people[0][0], FOREHAND: people[1][0]}
        self.watcher = people[2][0]


def agent_plays(agent, table, hand=PLAIN_HAND):
    for number, played in enumerate(hand, 1):
        if table.holder_of(played) is MIDDLEHAND:
            assert not agent.play(table, played, command_id=f"agent-card-{number:02d}").is_error
        else:
            table.accepted(played)


class TestAnAgentAtATableOfRamschRounds:
    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_the_tool_that_opens_a_table_takes_the_occasion_and_answers_it(self, skat, agent, occasion):
        agent.admitted()

        opened = agent.open_table(options=options_of("re", occasion=occasion))

        assert opened.json()["options"]["ramsch"]["occasion"] == occasion

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_the_tool_refuses_the_occasion_without_the_tables_bock_options(self, skat, agent, occasion):
        agent.admitted()

        refused = agent.open_table(options={"ramsch": {**POINTS, "occasion": occasion}})

        assert refused.is_error

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_plays_a_hand_dealt_as_a_ramsch_round_with_no_auction_and_uses_a_ramsch_round_game_up(
        self, skat, agent, occasion
    ):
        table = AgentRoundTable(skat, agent, occasion)
        hand = agent.read(table.table_id).json()["hand"]
        passed = agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-pass")

        agent_plays(agent, table)

        result = agent.read(table.table_id).json()["result"]
        assert (hand["ramsch"], hand["auction"]["awaiting"], passed.is_error) == (True, None, True)
        assert (result["kind"], result["bock_factor"], table.record.bock) == ("ramsch", 1, BockRounds((), 1))

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_pushes_the_skat_on_at_a_ramsch_round_hand_as_at_a_three_pass_ramsch(self, skat, agent, occasion):
        table = AgentRoundTable(skat, agent, occasion, pushing={"rule": "jacks-stay"})
        table.act(TABLE_PUSHING_PUSH_SUFFIX, table.at[FOREHAND])

        pushed = agent.take_step(RAMSCH_PUSH_SKAT_TOOL, table, command_id="agent-push")
        table.act(TABLE_PUSHING_PUSH_SUFFIX, table.at[REARHAND])
        agent_plays(agent, table)

        result = agent.read(table.table_id).json()["result"]
        assert not pushed.is_error, pushed.text
        assert (result["pushes"], result["push_factor"], table.record.bock) == (3, 8, BockRounds((), 1))

    @pytest.mark.parametrize("occasion", ROUND_OCCASIONS)
    def test_declares_a_grand_hand_instead_of_the_ramsch_at_a_ramsch_round_hand_and_it_uses_the_game_up(
        self, skat, agent, occasion
    ):
        table = AgentRoundTable(skat, agent, occasion, pushing={"rule": "jacks-stay", "grand_hand": "allowed"})
        table.act(TABLE_PUSHING_PUSH_SUFFIX, table.at[FOREHAND])

        declared = agent.take_step(RAMSCH_DECLARE_GRAND_HAND_TOOL, table, command_id="agent-grand-hand")
        agent_plays(agent, table)

        result = agent.read(table.table_id).json()["result"]
        assert not declared.is_error, declared.text
        assert (result["kind"], result["hand"], table.record.bock) == ("declared", True, BockRounds((), 1))
