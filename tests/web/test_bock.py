from dataclasses import replace
from functools import partial

import pytest

from skat.engine.bock import BockRounds
from skat.engine.deal import Position
from skat.table.records import Series
from skat.web.declaring import GameToken
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import with_known_deal
from tests.support.played_game import an_entry
from tests.web.support.playing import HERZ_GAME, Table, cards
from tests.web.support.series import deal_next, headers_of, pass_the_hand_in, tap_weiter

FOREHAND, MIDDLEHAND = Position.FOREHAND, Position.MIDDLEHAND
# Played by the middlehand's Herz Hand game or Grand Hand game against the known deal, found by a seeded search.
SIXTY_SIXTY = cards("S8 SA D9 SK DQ S7 H7 HK CJ CK SQ DT CT SJ HJ S9 HA C9 DJ CA H8 D8 C8 ST HQ C7 H9 D7 CQ HT")
OPPONENTS_SCHNEIDER = cards("C7 H9 DJ D8 S7 S9 HA CJ H7 S8 ST DQ H8 HQ C8 HJ C9 SJ HT HK CK SQ D9 CT SK DT CA SA D7 CQ")
DECLARER_WITHOUT_A_TRICK = cards(
    "CJ SJ HK CQ H7 HQ HJ CT H9 HA CA H8 DT S8 SK DJ S7 HT D8 CK SA D7 C8 ST DQ C7 S9 D9 C9 SQ"
)
GRAND_HAND_WON = cards("S8 S9 DT SK D9 S7 SQ D8 CQ ST HA CK H9 HQ C8 DQ CJ H7 CA SJ DJ SA HK CT HT HJ C7 D7 C9 H8")
GRAND_HAND_LOST = cards("S8 ST D8 SJ DJ CJ CQ H9 DT CT HT HQ C8 SQ HJ HA CK H7 D9 CA S9 DQ C7 SK HK S7 H8 D7 C9 SA")
AFTER_THE_BOCK_ROUND = {"games_left": 0, "factor": 1}
A_ROUND_BEGINS = {"games_left": 3, "factor": 2}


def bock_options(*triggers, overlap="append"):
    return {"bock": {"triggers": list(triggers), "overlap": overlap}}


@pytest.fixture
def open_table(server, monkeypatch):
    """A table for the three people and a watcher, opened through the API with the options a test names."""

    def open_with(*triggers, overlap="append", series_length=36, **options):
        monkeypatch.setattr(
            server,
            "create",
            partial(
                server.create, series_length=series_length, options=bock_options(*triggers, overlap=overlap) | options
            ),
        )
        return Table(server)

    return open_with


def bock_of(table):
    return table.read_as(table.watcher).json()["bock"]


def with_pending(table, *rounds):
    table.skat.store.tables[table.table_id] = replace(table.record, bock=BockRounds(rounds))


def say(table, position, word):
    answer = table.act(TABLE_KONTRA_SUFFIX, table.at[position], body={"word": word})
    assert answer.status_code == 200, answer.text


def played_with_words(table, *steps):
    """The Herz Hand game's cards, in order, and words between them: a number plays that many cards."""
    game = iter(HERZ_GAME)
    for step in steps:
        if isinstance(step, int):
            for _ in range(step):
                table.accepted(next(game))
        else:
            say(table, *step)


def gains_of(result):
    return [each["gain"] for each in result["gains"]]


def next_hand(table, *, after_a_pass_in=False):
    """Everyone taps „Weiter“ after a played game, then the next hand is dealt."""
    skat, people = table.skat, headers_of(table)
    games = len(table.record.game_list)
    for chair in table.record.chairs if not after_a_pass_in else ():
        if not chair.ready:
            answer = tap_weiter(skat, people[chair.seat - 1], table.table_id, f"weiter-{games}-{chair.seat}", games)
            assert answer.status_code == 200, answer.text
    assert deal_next(skat, table.table_id, [chair.occupant.account_id for chair in table.record.chairs])
    with_known_deal(skat, table.table_id)


class TestWhatStartsABockRound:
    @pytest.mark.parametrize(
        ("trigger", "game", "starts"),
        [
            pytest.param("sixty-sixty", SIXTY_SIXTY, True, id="1-sixty-sixty"),
            pytest.param("sixty-sixty", HERZ_GAME, False, id="2-sixty-one"),
            pytest.param("schwarz", DECLARER_WITHOUT_A_TRICK, True, id="8-schwarz-for-the-declarer-s-side"),
            pytest.param("schneider", OPPONENTS_SCHNEIDER, True, id="33-schneider-for-the-opponents"),
            pytest.param("re", SIXTY_SIXTY, False, id="26-re-at-a-table-without-kontra"),
        ],
    )
    def test_a_played_game_asks_the_triggers_with_the_last_card(self, open_table, trigger, game, starts):
        table = open_table(trigger)
        table.declared_hand_game()

        table.played_out(game)

        assert bock_of(table) == (A_ROUND_BEGINS if starts else AFTER_THE_BOCK_ROUND)

    def test_a_won_grand_hand_triggers_and_a_lost_one_does_not(self, open_table):
        won = open_table("won-grand-hand")
        won.declared_hand_game(GameToken.GRAND)
        won.played_out(GRAND_HAND_WON)

        lost = open_table("won-grand-hand")
        lost.declared_hand_game(GameToken.GRAND)
        lost.played_out(GRAND_HAND_LOST)

        assert (bock_of(won), bock_of(lost)) == (A_ROUND_BEGINS, AFTER_THE_BOCK_ROUND)

    def test_a_schneider_announced_and_missed_triggers(self, open_table):
        table = open_table("schneider")
        table.declared_hand_game(announcement="schneider")

        table.played_out(HERZ_GAME)

        assert bock_of(table) == A_ROUND_BEGINS

    def test_a_hand_all_three_pass_triggers(self, open_table, server):
        table = open_table("passed-in")

        pass_the_hand_in(server, table)

        assert bock_of(table) == A_ROUND_BEGINS

    def test_a_game_given_up_after_kontra_triggers_lost_after_kontra(self, open_table):
        table = open_table(
            "lost-after-kontra", kontra={"sayer": "any-opponent", "reach": "kontra-re", "deadline": "own-card"}
        )
        table.declared_hand_game()
        say(table, FOREHAND, "kontra")

        assert table.act(TABLE_GIVE_UP_SUFFIX).status_code == 200

        assert bock_of(table) == A_ROUND_BEGINS

    def test_a_won_game_after_kontra_does_not_trigger_lost_after_kontra(self, open_table):
        table = open_table(
            "lost-after-kontra", kontra={"sayer": "any-opponent", "reach": "kontra-re", "deadline": "own-card"}
        )
        table.declared_hand_game()

        played_with_words(table, (FOREHAND, "kontra"), 30)

        assert bock_of(table) == AFTER_THE_BOCK_ROUND

    @pytest.mark.parametrize(
        "triggers", [("re",), ("re", "lost-after-kontra")], ids=["re-alone", "re-and-lost-after-kontra"]
    )
    def test_re_triggers_whether_the_game_is_won_or_lost_and_one_game_starts_one_round(self, open_table, triggers):
        table = open_table(*triggers, kontra={"sayer": "any-opponent", "reach": "kontra-re", "deadline": "own-card"})
        table.declared_hand_game()
        played_with_words(table, (FOREHAND, "kontra"), 1, (MIDDLEHAND, "re"))

        assert table.act(TABLE_GIVE_UP_SUFFIX).status_code == 200

        assert bock_of(table) == A_ROUND_BEGINS

    def test_a_total_that_the_game_moved_to_200_triggers(self, open_table):
        table = open_table("total-ending-in-00")
        table.declared_hand_game()
        # The seat of the declarer was an opponent of three lost games: 3 times 40 make 120, and this game adds 80.
        accounts = tuple(chair.occupant.account_id for chair in table.record.chairs)
        lost_by_the_second_seat = replace(an_entry(accounts), declarer_seat=2, won=False, score=-30)
        table.skat.store.tables[table.table_id] = replace(table.record, game_list=(lost_by_the_second_seat,) * 3)

        table.played_out(HERZ_GAME)

        assert table.read_as(table.watcher).json()["chairs"][0]["total"] == 200
        assert bock_of(table) == A_ROUND_BEGINS

    def test_a_table_without_bock_has_no_bock_and_no_factor(self, server):
        table = Table(server)
        table.declared_hand_game()
        table.played_out(HERZ_GAME)

        answer = table.read_as(table.watcher).json()

        assert (answer["bock"], answer["options"]["bock"], answer["result"]["bock_factor"]) == (None, None, 1)


class TestWhatABockGameScores:
    def test_the_list_score_is_doubled_and_the_value_the_50_and_the_overbid_check_stay(self, open_table):
        table = open_table("passed-in")
        table.declared_hand_game()
        with_pending(table, 3)

        table.played_out(HERZ_GAME)

        result = table.result()
        assert (result["settled_value"], result["score"], result["list_bonus"], result["bock_factor"]) == (
            30,
            60,
            50,
            2,
        )
        assert gains_of(result) == [110, 0, 0]

    def test_a_game_given_up_in_a_bock_game_loses_the_doubled_score(self, open_table):
        table = open_table("passed-in")
        table.declared_hand_game()
        with_pending(table, 3)

        answer = table.act(TABLE_GIVE_UP_SUFFIX)

        result = answer.json()["result"]
        assert (result["score"], result["bock_factor"], gains_of(result)) == (-120, 2, [-170, 40, 40])

    @pytest.mark.parametrize(
        ("reach", "score", "list_bonus", "gains"),
        [
            pytest.param("kontra-re", 120, 50, [170, 0, 0], id="17-kontra-at-a-table-that-doubles-the-list-score"),
            pytest.param(
                "kontra-re-standings", 120, 100, [220, 0, 0], id="18-kontra-at-a-table-that-doubles-the-50-too"
            ),
        ],
    )
    def test_bock_and_kontra_multiply_and_only_the_standings_reach_doubles_the_50(
        self, open_table, reach, score, list_bonus, gains
    ):
        table = open_table("passed-in", kontra={"sayer": "any-opponent", "reach": reach, "deadline": "own-card"})
        table.declared_hand_game()
        with_pending(table, 3)

        played_with_words(table, (FOREHAND, "kontra"), 30)

        result = table.result()
        assert (result["score"], result["list_bonus"], gains_of(result)) == (score, list_bonus, gains)

    def test_a_game_in_two_pending_rounds_scores_four_times_at_a_multiply_table(self, open_table):
        table = open_table("passed-in", overlap="multiply")
        table.declared_hand_game()
        with_pending(table, 3, 3)

        table.played_out(HERZ_GAME)

        result = table.result()
        assert (result["bock_factor"], result["score"], gains_of(result)) == (4, 120, [170, 0, 0])

    def test_the_list_row_names_the_factor_of_each_game(self, open_table, server):
        table = open_table("passed-in")
        table.declared_hand_game()
        with_pending(table, 3)
        table.played_out(HERZ_GAME)
        next_hand(table)
        table.declared_hand_game()
        table.played_out(HERZ_GAME)

        server.client.cookies.clear()
        rows = server.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher).json()[
            "entries"
        ]

        assert [(row["number"], row["bock_factor"], row["score"]) for row in rows] == [(1, 2, 60), (2, 2, 60)]


class TestHowTheRoundsOverlap:
    @pytest.mark.parametrize(
        ("overlap", "after_two_passed_in_hands"),
        [
            pytest.param("append", {"games_left": 5, "factor": 2}, id="11-append"),
            pytest.param("multiply", {"games_left": 3, "factor": 4}, id="12-multiply"),
            pytest.param("ignore", {"games_left": 2, "factor": 2}, id="13-ignore"),
        ],
    )
    def test_a_trigger_inside_a_round_acts_as_the_overlap_says(
        self, open_table, server, overlap, after_two_passed_in_hands
    ):
        table = open_table("passed-in", overlap=overlap)
        pass_the_hand_in(server, table)
        next_hand(table, after_a_pass_in=True)

        pass_the_hand_in(server, table)

        assert bock_of(table) == after_two_passed_in_hands


class TestWhatEveryoneSeesOfThePendingGames:
    def test_the_games_to_come_include_the_running_one_during_auction_and_play_and_count_down_after_it(
        self, open_table
    ):
        table = open_table("passed-in")
        with_pending(table, 3)
        during_the_auction = (bock_of(table), table.read_as(table.at[MIDDLEHAND]).json()["bock"])
        table.declared_hand_game()
        table.accepted(HERZ_GAME[0])
        during_the_play = bock_of(table)

        for each in HERZ_GAME[1:30]:
            table.accepted(each)

        assert during_the_auction == (A_ROUND_BEGINS, A_ROUND_BEGINS)
        assert during_the_play == A_ROUND_BEGINS
        assert bock_of(table) == {"games_left": 2, "factor": 2}


class TestTheSeriesLimitsTheRounds:
    def test_the_games_left_never_promise_a_game_the_series_will_not_deal(self, open_table, server):
        table = open_table("passed-in", series_length=6)
        server.store.tables[table.table_id] = replace(table.record, series=Series(6, 5))

        pass_the_hand_in(server, table)

        assert bock_of(table) == {"games_left": 1, "factor": 2}

    def test_the_last_game_scores_double_and_then_nothing_stays_pending(self, open_table, server):
        table = open_table("passed-in", series_length=6)
        server.store.tables[table.table_id] = replace(table.record, series=Series(6, 5))
        pass_the_hand_in(server, table)
        next_hand(table, after_a_pass_in=True)
        table.declared_hand_game()

        table.played_out(HERZ_GAME)

        assert (table.result()["bock_factor"], bock_of(table), table.record.bock) == (
            2,
            AFTER_THE_BOCK_ROUND,
            BockRounds(()),
        )

    def test_a_trigger_in_the_last_game_leaves_no_pending_game(self, open_table, server):
        table = open_table("passed-in", series_length=3)
        server.store.tables[table.table_id] = replace(table.record, series=Series(3, 3))

        pass_the_hand_in(server, table)

        assert (bock_of(table), table.record.bock) == (AFTER_THE_BOCK_ROUND, BockRounds(()))


class TestOpeningATable:
    def test_the_answer_carries_the_options_with_the_triggers_sorted_by_their_token(self, server):
        opener, _ = server.member()

        answer = server.create(opener, options=bock_options("schwarz", "re", overlap="multiply"))

        assert answer.json()["options"]["bock"] == {"triggers": ["re", "schwarz"], "overlap": "multiply"}
        assert answer.json()["bock"] == AFTER_THE_BOCK_ROUND

    def test_a_retry_with_the_same_triggers_in_any_order_is_the_first_table_and_other_triggers_a_reused_id(
        self, server
    ):
        opener, _ = server.member()
        first = server.create(opener, options=bock_options("schwarz", "re"))

        same = server.create(opener, options=bock_options("re", "schwarz"))
        other = server.create(opener, options=bock_options("re"))

        assert same.json()["id"] == first.json()["id"]
        assert other.status_code == 409

    @pytest.mark.parametrize(
        "bock",
        [
            pytest.param({"triggers": [], "overlap": "append"}, id="no-trigger"),
            pytest.param({"triggers": ["double-kontra"], "overlap": "append"}, id="unknown-trigger"),
            pytest.param({"triggers": ["re", "re"], "overlap": "append"}, id="repeated-trigger"),
            pytest.param({"triggers": ["re"]}, id="no-overlap"),
            pytest.param({"triggers": ["re"], "overlap": "append", "extra": 1}, id="extra-key"),
        ],
    )
    def test_a_request_that_is_no_valid_bock_option_opens_no_table(self, server, bock):
        opener, _ = server.member()

        answer = server.create(opener, options={"bock": bock})

        assert answer.status_code == 422
        assert server.store.tables == {}

    def test_a_table_opened_without_bock_keeps_the_receipt_text_older_receipts_have(self, server):
        opener, account = server.member()
        first = server.create(opener, series_length=36)

        again = server.create(opener, series_length=36)

        assert again.json()["id"] == first.json()["id"]
        assert server.store.receipts[(account.id, "command-0001")].payload == '{"series_length":36}'
