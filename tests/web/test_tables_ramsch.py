from dataclasses import replace

import pytest

from skat.engine.deal import next_dealer, positions_from
from skat.table.records import Refusal, Series
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import TABLE_DECLARING_DECLARE_SUFFIX
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from skat.web.playing import (
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_THROW_DOWN_SUFFIX,
)
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, cards_in_text, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import (
    FOREHAND,
    JUNGFRAU_DEAL,
    JUNGFRAU_HAND,
    MIDDLEHAND,
    PLAIN_DEAL,
    PLAIN_HAND,
    REARHAND,
    SWEEP_DEAL,
    SWEEP_HAND,
    TIE_DEAL,
    TIE_HAND,
    Table,
    cards,
    reason_of,
    three_pass,
)
from tests.web.support.series import deal_next, headers_of, play_the_dealt_series, tap_new_series, tap_weiter
from tests.web.support.skat import streams_of

SEATS = {position: seat for seat, position in positions_from(DEALER_SEAT).items()}
FOREHAND_SEAT, MIDDLEHAND_SEAT, REARHAND_SEAT = SEATS[FOREHAND], SEATS[MIDDLEHAND], SEATS[REARHAND]
POINTS = {"occasion": "passed-in", "scoring": "points", "jungfrau": "doubles-loser", "durchmarsch": "wins-120"}
RAMSCH = {"ramsch": POINTS}
KONTRA = {"kontra": {"sayer": "any-opponent", "reach": "kontra-re", "deadline": "own-card"}}


def options_of(**changed):
    return {"ramsch": {**POINTS, **changed}}


def seat_results(*points_and_scores):
    """A Ramsch result's seats by seat number from the (points, score) of seats 1, 2 and 3."""
    return [{"seat": seat, "points": p, "score": s} for seat, (p, s) in enumerate(points_and_scores, 1)]


def ramsch_result(seats, *, durchmarsch_seat=None, jungfrau=False):
    return {
        "kind": "ramsch",
        "ordinal": 1,
        "seats": seats,
        "durchmarsch_seat": durchmarsch_seat,
        "jungfrau": jungfrau,
        "bock_factor": 1,
        "pushes": 0,
        "push_factor": 1,
    }


def ramsch_table(skat, deal, options=RAMSCH):
    table = Table(skat, options)
    table.with_deal(deal)
    three_pass(table)
    return table


def read(table, position=None):
    headers = table.watcher if position is None else table.at[position]
    return table.read_as(headers).json()


class TestTheThirdPass:
    def test_keeps_the_hand_and_starts_a_ramsch_forehand_leads_for_every_viewer(self, skat):
        table = ramsch_table(skat, PLAIN_DEAL)

        for position in (FOREHAND, MIDDLEHAND, REARHAND, None):
            hand = read(table, position)["hand"]
            assert (hand["ramsch"], hand["declaring"], hand["skat_count"]) == (True, None, 2)
            assert hand["playing"]["turn_seat"] == FOREHAND_SEAT
            assert hand["playing"]["running_points"] is None
            assert len(hand["auction"]["words"]) == 3
            assert (hand["playing"]["legal_cards"] != []) == (position is FOREHAND)
        assert read(table)["passed_in"] is None

    @pytest.mark.parametrize("options", [None, RAMSCH], ids=["a-table-without-ramsch", "a-table-with-ramsch"])
    def test_a_declared_game_is_no_ramsch_whatever_the_table_plays(self, skat, options):
        table = Table(skat, options)
        table.declared_hand_game()

        assert read(table)["hand"]["ramsch"] is False

    def test_passes_the_hand_in_at_a_table_without_ramsch(self, skat):
        table = Table(skat)
        three_pass(table)

        answer = read(table)

        assert answer["hand"] is None
        assert answer["passed_in"] == {"next_dealer_seat": next_dealer(DEALER_SEAT)}

    def test_a_viewer_never_reads_the_skat_while_the_ramsch_runs_or_after_it(self, skat):
        table = ramsch_table(skat, PLAIN_DEAL, options={"ramsch": POINTS, "show_running_points": True})
        seen = {*wire_cards(PLAIN_DEAL.skat)}
        for played in PLAIN_HAND:
            for position in (FOREHAND, MIDDLEHAND, REARHAND, None):
                headers = table.watcher if position is None else table.at[position]
                assert not seen & cards_in_text(table.read_as(headers).text)
            table.accepted(played)
        assert not seen & cards_in_text(table.read_as(table.watcher).text)

    @pytest.mark.parametrize("show_running_points", [False, True])
    def test_shows_no_running_points_whatever_the_table_switch_says(self, skat, show_running_points):
        table = ramsch_table(skat, PLAIN_DEAL, options={**RAMSCH, "show_running_points": show_running_points})
        table.played_out(PLAIN_HAND[:9])

        assert read(table, MIDDLEHAND)["hand"]["playing"]["running_points"] is None


class TestPlayingARamsch:
    def test_a_jack_led_must_be_followed_with_a_jack_by_a_seat_holding_one(self, skat):
        table = ramsch_table(skat, PLAIN_DEAL)
        table.accepted(cards("CJ")[0])

        table.refused(table.at[MIDDLEHAND], cards("S9")[0], "must-follow")

    def test_a_retried_card_stores_one_card(self, skat):
        table = ramsch_table(skat, PLAIN_DEAL)
        first = table.send(table.at[FOREHAND], PLAIN_HAND[0], command_id="card-0001")
        version = table.record.version

        again = table.send(table.at[FOREHAND], PLAIN_HAND[0], command_id="card-0001", version=version - 1)

        assert (again.status_code, again.json()) == (first.status_code, first.json())
        assert len(table.plays) == 1

    @pytest.mark.parametrize(
        ("suffix", "body"),
        [
            (TABLE_DECLARING_DECLARE_SUFFIX, {"game": "herz", "hand": True, "ouvert": False, "announcement": "none"}),
            (TABLE_GIVE_UP_SUFFIX, None),
            (TABLE_GIVE_UP_AGREE_SUFFIX, None),
            (TABLE_GIVE_UP_DECLINE_SUFFIX, None),
            (TABLE_THROW_DOWN_SUFFIX, None),
            (TABLE_KONTRA_SUFFIX, {"word": "kontra"}),
        ],
        ids=[
            "a-declaring-step",
            "a-give-up",
            "a-give-up-consent",
            "a-give-up-refusal",
            "a-throw-down",
            "a-kontra-word",
        ],
    )
    @pytest.mark.parametrize("position", [FOREHAND, MIDDLEHAND, REARHAND])
    def test_refuses_a_declared_games_steps_as_wrong_phase(self, skat, suffix, body, position):
        table = ramsch_table(skat, PLAIN_DEAL, {**RAMSCH, **KONTRA})

        table.refused_act(suffix, table.at[position], "wrong-phase", body=body)

    def test_refuses_an_auction_step_as_over(self, skat):
        table = ramsch_table(skat, PLAIN_DEAL)
        before = table.record

        answer = table.act(TABLE_AUCTION_PASS_SUFFIX, table.at[FOREHAND])

        assert (answer.status_code, reason_of(answer), table.record) == (409, "over", before)


# Seats 1, 2 and 3 are middlehand, rearhand and forehand.
ENDED = [
    pytest.param(
        PLAIN_DEAL,
        PLAIN_HAND,
        {},
        ramsch_result(seat_results((22, 0), (86, -86), (12, 0))),
        id="the-loser-holds-the-skat-as-the-last-tricks-taker",
    ),
    pytest.param(
        PLAIN_DEAL,
        PLAIN_HAND,
        {"scoring": "points-by-ten"},
        ramsch_result(seat_results((22, 0), (86, -8), (12, 0))),
        id="points-divided-by-ten",
    ),
    pytest.param(
        PLAIN_DEAL,
        PLAIN_HAND,
        {"scoring": "skat-to-loser"},
        ramsch_result(seat_results((22, 0), (86, -86), (12, 0))),
        id="skat-to-the-seat-with-the-most-trick-points",
    ),
    pytest.param(
        TIE_DEAL,
        TIE_HAND,
        {},
        ramsch_result(seat_results((41, -41), (41, -41), (38, 0))),
        id="tied-seats-both-lose",
    ),
    pytest.param(
        TIE_DEAL,
        TIE_HAND,
        {"scoring": "skat-to-loser"},
        ramsch_result(seat_results((45, -45), (45, -45), (34, 0))),
        id="each-tied-seat-adds-the-skat-under-skat-to-loser",
    ),
    pytest.param(
        JUNGFRAU_DEAL,
        JUNGFRAU_HAND,
        {},
        ramsch_result(seat_results((101, -202), (19, 0), (0, 0)), jungfrau=True),
        id="a-seat-with-no-trick-doubles-the-loss",
    ),
    pytest.param(
        JUNGFRAU_DEAL,
        JUNGFRAU_HAND,
        {"scoring": "points-by-ten"},
        ramsch_result(seat_results((101, -20), (19, 0), (0, 0)), jungfrau=True),
        id="points-divided-by-ten-before-the-doubling",
    ),
    pytest.param(
        JUNGFRAU_DEAL,
        JUNGFRAU_HAND,
        {"jungfrau": "off"},
        ramsch_result(seat_results((101, -101), (19, 0), (0, 0))),
        id="no-doubling-with-jungfrau-off",
    ),
    pytest.param(
        SWEEP_DEAL,
        SWEEP_HAND,
        {},
        ramsch_result(seat_results((0, 0), (0, 0), (120, 120)), durchmarsch_seat=FOREHAND_SEAT),
        id="a-sweep-wins-120",
    ),
    *[
        pytest.param(
            SWEEP_DEAL,
            SWEEP_HAND,
            changed,
            ramsch_result(seat_results((0, 0), (0, 0), (120, 120)), durchmarsch_seat=FOREHAND_SEAT),
            id=f"a-sweep-wins-120-at-{next(iter(changed.values()))}",
        )
        for changed in ({"scoring": "points-by-ten"}, {"scoring": "skat-to-loser"}, {"durchmarsch": "wins-120-flat"})
    ],
    pytest.param(
        SWEEP_DEAL,
        SWEEP_HAND,
        {"durchmarsch": "off"},
        ramsch_result(seat_results((0, 0), (0, 0), (120, -240)), jungfrau=True),
        id="a-sweep-loses-doubled-with-durchmarsch-off",
    ),
    pytest.param(
        SWEEP_DEAL,
        SWEEP_HAND,
        {"durchmarsch": "off", "jungfrau": "off"},
        ramsch_result(seat_results((0, 0), (0, 0), (120, -120))),
        id="a-sweep-loses-single-with-durchmarsch-and-jungfrau-off",
    ),
]


class TestTheEndOfARamsch:
    @pytest.mark.parametrize(("deal", "hand", "changed", "result"), ENDED)
    def test_the_thirtieth_card_ends_it_with_the_result_for_every_viewer_and_the_list_row(
        self, skat, deal, hand, changed, result
    ):
        table = ramsch_table(skat, deal, options_of(**changed))
        table.played_out(hand)

        for position in (FOREHAND, MIDDLEHAND, REARHAND, None):
            answer = read(table, position)
            assert (answer["result"], answer["hand"], answer["passed_in"]) == (result, None, None)
        scores = {seat["seat"]: seat["score"] for seat in result["seats"]}
        totals = {chair["seat"]: chair["total"] for chair in read(table)["chairs"]}
        assert totals == scores
        row = read_list(table)[0]
        assert (row["kind"], row["number"], row["jungfrau"], row["durchmarsch"]) == (
            "ramsch",
            1,
            result["jungfrau"],
            result["durchmarsch_seat"] is not None,
        )
        assert [seat["score"] for seat in row["seats"]] == [scores[1], scores[2], scores[3]]
        assert not cards_in_text(table.read_as(table.watcher).text)

    def test_all_three_taps_of_weiter_deal_the_next_hand(self, server):
        table = ramsch_table(server, PLAIN_DEAL)
        table.played_out(PLAIN_HAND)
        members = [(table.at[position], None) for position in (FOREHAND, MIDDLEHAND, REARHAND)]

        with streams_of(server, table.table_id, members):
            for position in (FOREHAND, MIDDLEHAND, REARHAND):
                assert tap(table, position, 1).status_code == 200

        assert (table.record.hand is not None, table.record.dealer) == (True, next_dealer(DEALER_SEAT))
        assert read(table)["result"] is None

    def test_a_tap_with_another_number_is_stale(self, skat):
        table = ramsch_table(skat, PLAIN_DEAL)
        table.played_out(PLAIN_HAND)

        assert reason_of(tap(table, FOREHAND, 2)) == "stale-result"

    def test_a_tap_while_the_ramsch_runs_has_no_result(self, skat):
        table = ramsch_table(skat, PLAIN_DEAL)

        assert reason_of(tap(table, FOREHAND, 1)) == "no-result"


def tap(table, position, ordinal):
    table.skat.client.cookies.clear()
    return table.skat.client.post(
        f"{TABLES_PATH}/{table.table_id}{TABLE_READY_SUFFIX}",
        json={"command_id": table.fresh_id(), "ordinal": ordinal},
        headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[position]},
    )


def read_list(table):
    table.skat.client.cookies.clear()
    answer = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher)
    assert answer.status_code == 200, answer.text
    return answer.json()["entries"]


class TestOpeningARamschTable:
    def test_answers_the_options_as_sent_and_a_table_without_ramsch_answers_none(self, skat):
        headers, _ = skat.member()

        with_ramsch = skat.create(headers, options=options_of(scoring="skat-to-loser", durchmarsch="off"))
        without = skat.create(headers, command_id="command-0002")

        assert with_ramsch.json()["options"]["ramsch"] == {
            **POINTS,
            "scoring": "skat-to-loser",
            "durchmarsch": "off",
            "pushing": None,
        }
        assert without.json()["options"]["ramsch"] is None

    def test_a_retry_with_the_same_options_is_the_first_table_and_with_other_options_is_refused(self, skat):
        headers, _ = skat.member()
        first = skat.create(headers, options=RAMSCH)

        same = skat.create(headers, options=RAMSCH)
        other = skat.create(headers, options=options_of(jungfrau="off"))

        assert same.json()["id"] == first.json()["id"]
        assert other.status_code == 409

    @pytest.mark.parametrize(
        "ramsch",
        [
            pytest.param({**POINTS, "occasion": "ramsch-rounds"}, id="another-occasion"),
            pytest.param({**POINTS, "scoring": "tens"}, id="an-unknown-scoring"),
            pytest.param({k: v for k, v in POINTS.items() if k != "jungfrau"}, id="a-missing-field"),
            pytest.param({**POINTS, "pushing": True}, id="an-extra-key"),
            pytest.param({}, id="an-empty-record"),
        ],
    )
    def test_refuses_an_option_that_is_no_ramsch_with_422_and_opens_no_table(self, skat, ramsch):
        headers, _ = skat.member()

        answer = skat.create(headers, options={"ramsch": ramsch})

        assert answer.status_code == 422
        assert skat.store.tables == {}


class TestARamschEndingASeries:
    @pytest.fixture
    def ended(self, skat):
        """A series of three whose first two games were declared and whose third, the last, was a Ramsch played out.

        Returns the table and the seats' totals before the Ramsch.
        """
        table = Table(skat, RAMSCH)
        skat.store.tables[table.table_id] = replace(table.record, series=Series(3, 1))
        play_the_dealt_series(skat, table, 2, deal_after_last=True)
        table.with_deal(PLAIN_DEAL)
        before = {chair["seat"]: chair["total"] for chair in read(table)["chairs"]}
        three_pass(table)
        table.played_out(PLAIN_HAND)
        return table, before

    def test_the_series_is_over_and_the_standings_count_the_ramsch_in_the_totals_only(self, ended):
        table, before = ended
        scores = {1: 0, 2: -86, 3: 0}

        series = read(table)["series"]

        assert (series["game_number"], series["over"]) == (3, True)
        assert sorted(each["total"] for each in series["standings"]) == sorted(
            before[seat] + scores[seat] for seat in scores
        )
        assert sum(each["won"] + each["lost"] for each in series["standings"]) == 2
        assert read(table)["passed_in"] is None

    def test_weiter_is_refused_as_series_over(self, skat, ended):
        table, _ = ended

        skat.client.cookies.clear()
        answer = tap_weiter(skat, headers_of(table)[0], table.table_id, "weiter-after-ramsch", ordinal=3)

        assert (answer.status_code, reason_of(answer)) == (409, Refusal.SERIES_OVER)

    def test_three_taps_of_neue_serie_deal_the_next_series_with_an_empty_list(self, skat, ended):
        table, _ = ended
        for number, headers in enumerate(headers_of(table), start=1):
            skat.client.cookies.clear()
            assert tap_new_series(skat, headers, table.table_id, f"tap-new-{number}").status_code == 200
        accounts = [chair.occupant.account_id for chair in table.record.chairs]

        assert deal_next(skat, table.table_id, accounts)

        series = read(table)["series"]
        assert (series["game_number"], series["over"], series["standings"]) == (1, False, None)
        assert read_list(table) == []
        assert [chair["total"] for chair in read(table)["chairs"]] == [0, 0, 0]
