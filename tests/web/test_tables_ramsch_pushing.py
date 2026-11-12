from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skat.engine.bock import BockRounds
from skat.table.records import Series
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.paused import PAUSED_TABLES_PATH
from skat.web.rule_sets import RULE_SETS_PATH
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import cards_in, cards_in_text, wire_cards
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
    Table,
    bock_of,
    card,
    cards,
    game_of,
    reason_of,
    three_pass,
    with_pending,
    with_totals,
)
from tests.web.support.ramsch_stage import (
    FOREHAND_SEAT,
    MIDDLEHAND_SEAT,
    POINTS,
    REARHAND_SEAT,
    SUFFIXES,
    VIEWERS,
    accepted,
    list_rows,
    play_stage,
    read,
    refused,
    stage_table,
    step,
    step_body,
)
from tests.web.support.series import deal_the_next_game, headers_of, tap_new_series, tap_weiter
from tests.web.support.skat import Skat, stored, streams_of

DEALT_AT = datetime(2026, 11, 1, 12, tzinfo=UTC)


def pushing_options(rule="jacks-stay", **grand_hand):
    return {"ramsch": {**POINTS, "pushing": {"rule": rule, **grand_hand}}}


class TestOpeningAPushingTable:
    @pytest.mark.parametrize("rule", ["jacks-stay", "jacks-may-go", "no-doubling"])
    def test_answers_the_rule_as_sent(self, skat, rule):
        headers, _ = skat.member()

        opened = skat.create(headers, options=pushing_options(rule))

        assert opened.json()["options"]["ramsch"] == {**POINTS, "pushing": {"rule": rule, "grand_hand": "off"}}

    @pytest.mark.parametrize(
        ("sent", "answered"),
        [
            pytest.param({"grand_hand": "allowed"}, "allowed", id="allowed"),
            pytest.param({"grand_hand": "off"}, "off", id="off"),
            pytest.param({}, "off", id="left-out-reads-off"),
        ],
    )
    def test_answers_the_grand_hand_as_sent_and_off_where_it_is_left_out(self, skat, sent, answered):
        headers, _ = skat.member()

        opened = skat.create(headers, options=pushing_options(**sent))

        assert opened.json()["options"]["ramsch"]["pushing"] == {"rule": "jacks-stay", "grand_hand": answered}

    def test_a_saved_set_keeps_the_grand_hand_and_a_retry_with_another_one_is_refused(self, skat):
        headers, _ = skat.member()
        saved = skat.client.post(
            RULE_SETS_PATH,
            json={"name": "Alleine", "options": pushing_options(grand_hand="allowed")},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )
        first = skat.create(headers, options=pushing_options(grand_hand="allowed"))

        same = skat.create(headers, options=pushing_options(grand_hand="allowed"))
        other = skat.create(headers, options=pushing_options(grand_hand="off"))

        assert saved.json()["options"]["ramsch"]["pushing"]["grand_hand"] == "allowed"
        assert same.json()["id"] == first.json()["id"]
        assert other.status_code == 409

    def test_a_table_without_the_rule_answers_null_for_it(self, skat):
        headers, _ = skat.member()

        opened = skat.create(headers, options={"ramsch": POINTS})

        assert opened.json()["options"]["ramsch"] == {**POINTS, "pushing": None}

    def test_a_saved_set_keeps_the_rule_and_a_table_opened_with_it_plays_it(self, skat):
        headers, _ = skat.member()

        saved = skat.client.post(
            RULE_SETS_PATH,
            json={"name": "Schieben", "options": pushing_options("jacks-may-go")},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

        expected = {**POINTS, "pushing": {"rule": "jacks-may-go", "grand_hand": "off"}}
        assert saved.json()["options"]["ramsch"] == expected
        assert skat.create(headers, options=pushing_options("jacks-may-go")).json()["options"]["ramsch"] == expected

    def test_a_retry_with_the_same_rule_is_the_first_table_and_with_another_rule_is_refused(self, skat):
        headers, _ = skat.member()
        first = skat.create(headers, options=pushing_options())

        same = skat.create(headers, options=pushing_options())
        other = skat.create(headers, options=pushing_options("no-doubling"))

        assert same.json()["id"] == first.json()["id"]
        assert other.status_code == 409

    @pytest.mark.parametrize(
        "options",
        [
            pytest.param({"ramsch": {**POINTS, "pushing": {"rule": "always"}}}, id="a-rule-outside-the-three"),
            pytest.param(
                {"ramsch": {**POINTS, "pushing": {"rule": "jacks-stay", "announce": "schwarz"}}}, id="an-extra-key"
            ),
            pytest.param(
                {"ramsch": {**POINTS, "pushing": {"rule": "jacks-stay", "grand_hand": "always"}}},
                id="a-grand-hand-outside-the-two",
            ),
            pytest.param(
                {"ramsch": {**POINTS, "pushing": {"grand_hand": "allowed"}}}, id="a-grand-hand-without-a-rule"
            ),
            pytest.param({"ramsch": {**POINTS, "grand_hand": "allowed"}}, id="a-grand-hand-without-pushing"),
            pytest.param({"ramsch": {**POINTS, "pushing": {}}}, id="an-empty-rule"),
            pytest.param({"ramsch": {**POINTS, "pushing": "jacks-stay"}}, id="a-bare-token"),
            pytest.param({"pushing": {"rule": "jacks-stay"}}, id="pushing-without-ramsch"),
        ],
    )
    def test_refuses_what_is_no_pushing_rule_with_422_and_opens_no_table(self, skat, options):
        headers, _ = skat.member()

        answer = skat.create(headers, options=options)

        assert answer.status_code == 422
        assert skat.store.tables == {}


def scores_of(result):
    return [seat["score"] for seat in sorted(result["seats"], key=lambda seat: seat["seat"])]


class TestTheThirdPass:
    def test_starts_the_stage_for_every_viewer_and_no_card_may_be_played(self, skat):
        table = stage_table(skat)

        for position in VIEWERS:
            hand = read(table, position)["hand"]
            assert (hand["ramsch"], hand["playing"], hand["pushes"], hand["skat_count"]) == (True, None, 0, 2)
            assert hand["pushing"] == {"turn_seat": FOREHAND_SEAT, "stage": "choosing", "moves": [], "factor": 1}
        card = table.send(table.at[FOREHAND], PLAIN_HAND[0])
        assert (card.status_code, reason_of(card), read(table)["result"]) == (409, "wrong-phase", None)

    @pytest.mark.parametrize("kind", ["take", "put-back", "push"])
    def test_a_table_without_pushing_plays_the_ramsch_at_once_and_refuses_every_step(self, skat, kind):
        table = stage_table(skat, rule=None)

        hand = read(table)["hand"]
        assert (hand["pushing"], hand["pushes"], hand["playing"]["turn_seat"]) == (None, 0, FOREHAND_SEAT)
        refused(table, FOREHAND, kind, "wrong-phase", put=cards("C7 C8") if kind == "put-back" else ())


class TestTheStage:
    def test_a_taker_holds_twelve_and_puts_two_back_and_the_next_seat_is_on_turn(self, skat):
        table = stage_table(skat)

        taken = accepted(table, FOREHAND, "take")["hand"]
        assert (len(taken["own_cards"]), taken["skat_count"]) == (12, 0)
        assert taken["pushing"] == {"turn_seat": FOREHAND_SEAT, "stage": "discarding", "moves": [], "factor": 1}
        assert [chair["hand"]["card_count"] for chair in read(table)["chairs"]] == [10, 10, 12]
        put = accepted(table, FOREHAND, "put-back", cards("C7 C8"))["hand"]
        assert (len(put["own_cards"]), put["skat_count"]) == (10, 2)
        assert put["pushing"] == {
            "turn_seat": MIDDLEHAND_SEAT,
            "stage": "choosing",
            "moves": [{"seat": FOREHAND_SEAT, "action": "took"}],
            "factor": 1,
        }

    def test_two_pushes_lead_into_the_ramsch_which_keeps_the_count_and_doubles_the_losers_score_twice(self, skat):
        table = stage_table(skat)
        play_stage(table, "back", "push", "push")

        hand = read(table, FOREHAND)["hand"]
        assert (hand["pushing"], hand["pushes"], hand["playing"]["turn_seat"]) == (None, 2, FOREHAND_SEAT)
        table.played_out(PLAIN_HAND[:17])
        assert read(table, MIDDLEHAND)["hand"]["pushes"] == 2
        table.played_out(PLAIN_HAND[17:])

        result = table.result()
        assert (result["pushes"], result["push_factor"], result["bock_factor"]) == (2, 4, 1)
        assert scores_of(result) == [0, -86 * 4, 0]
        assert read(table)["hand"] is None
        row = list_rows(table)[0]
        assert (row["kind"], row["pushes"], row["push_factor"], row["bock_factor"]) == ("ramsch", 2, 4, 1)

    def test_the_ramsch_starts_on_the_hands_the_stage_left_and_not_on_the_dealt_ones(self, skat):
        table = stage_table(skat)
        accepted(table, FOREHAND, "take")
        accepted(table, FOREHAND, "put-back", cards("C7 C8"))
        accepted(table, MIDDLEHAND, "push")
        accepted(table, REARHAND, "push")

        held = {
            position: cards_in(read(table, position)["hand"]["own_cards"])
            for position in (FOREHAND, MIDDLEHAND, REARHAND)
        }
        assert held == {
            FOREHAND: wire_cards(cards("C9 CT CJ CQ CK CA S7 S8 DK DA")),
            MIDDLEHAND: wire_cards(PLAIN_DEAL.middlehand),
            REARHAND: wire_cards(PLAIN_DEAL.rearhand),
        }
        table.refused(table.at[FOREHAND], card("C7"), "not-in-hand")
        assert table.send(table.at[FOREHAND], card("DK")).status_code == 200

    def test_the_moves_list_each_seat_that_finished_in_order_and_the_factor_follows_the_pushes(self, skat):
        table = stage_table(skat)
        accepted(table, FOREHAND, "push")
        accepted(table, MIDDLEHAND, "take")
        accepted(table, MIDDLEHAND, "put-back", cards("S9 ST"))

        assert read(table, REARHAND)["hand"]["pushing"] == {
            "turn_seat": REARHAND_SEAT,
            "stage": "choosing",
            "moves": [{"seat": FOREHAND_SEAT, "action": "pushed"}, {"seat": MIDDLEHAND_SEAT, "action": "took"}],
            "factor": 2,
        }

    @pytest.mark.parametrize(
        ("plan", "factor", "score"),
        [
            pytest.param(("push", "push", "push"), 8, -86 * 8, id="everyone-pushes-and-the-skat-is-the-dealt-one"),
            pytest.param(("back", "back", "back"), 1, -86, id="everyone-takes-and-the-skat-is-the-last-put-back"),
        ],
    )
    def test_three_pushes_count_three_and_three_takes_none(self, skat, plan, factor, score):
        table = stage_table(skat)

        play_stage(table, *plan)
        table.played_out(PLAIN_HAND)

        result = table.result()
        assert (result["push_factor"], result["pushes"]) == (factor, plan.count("push"))
        assert scores_of(result) == [0, score, 0]

    @pytest.mark.parametrize(
        ("rule", "lets_the_jack_go"),
        [("jacks-stay", False), ("no-doubling", False), ("jacks-may-go", True)],
    )
    def test_a_jack_among_the_two_put_back_is_refused_unless_the_rule_lets_jacks_go(self, skat, rule, lets_the_jack_go):
        table = stage_table(skat, rule)
        accepted(table, FOREHAND, "take")

        if lets_the_jack_go:
            accepted(table, FOREHAND, "put-back", cards("CJ C7"))
            assert read(table)["hand"]["pushing"]["turn_seat"] == MIDDLEHAND_SEAT
        else:
            refused(table, FOREHAND, "put-back", "jack-put-back", cards("CJ C7"))

    @pytest.mark.parametrize(
        ("before", "position", "kind", "put", "reason"),
        [
            pytest.param((), MIDDLEHAND, "push", (), "not-your-turn", id="a-push-out-of-turn"),
            pytest.param((), MIDDLEHAND, "take", (), "not-your-turn", id="a-take-out-of-turn"),
            pytest.param((), FOREHAND, "put-back", cards("C7 C8"), "out-of-order", id="a-put-back-before-a-take"),
            pytest.param(((FOREHAND, "take"),), FOREHAND, "take", (), "out-of-order", id="a-take-after-a-take"),
            pytest.param(((FOREHAND, "take"),), FOREHAND, "push", (), "out-of-order", id="a-push-after-a-take"),
            pytest.param(
                ((FOREHAND, "take"),),
                MIDDLEHAND,
                "put-back",
                cards("S9 ST"),
                "not-your-turn",
                id="another-seats-put-back",
            ),
            pytest.param(
                ((FOREHAND, "take"),), FOREHAND, "put-back", cards("C7 C7"), "not-two-of-the-twelve", id="a-card-twice"
            ),
            pytest.param(
                ((FOREHAND, "take"),),
                FOREHAND,
                "put-back",
                cards("S9 C7"),
                "not-two-of-the-twelve",
                id="a-card-not-held",
            ),
            pytest.param(
                ((FOREHAND, "take"),), FOREHAND, "put-back", cards("C7"), "not-two-of-the-twelve", id="a-single-card"
            ),
            pytest.param(
                ((FOREHAND, "take"),),
                FOREHAND,
                "put-back",
                cards("C7 C8 C9"),
                "not-two-of-the-twelve",
                id="three-cards",
            ),
        ],
    )
    def test_the_engines_refusals_come_back_and_leave_the_table_as_it_was(
        self, skat, before, position, kind, put, reason
    ):
        table = stage_table(skat)
        for earlier_position, earlier_kind in before:
            accepted(table, earlier_position, earlier_kind)

        refused(table, position, kind, reason, put)

    @pytest.mark.parametrize(
        "put",
        [
            pytest.param(cards("C7 C8 C9 CT CJ CQ CK CA S7 S8 S9 ST S7"), id="one-more-than-a-seat-can-hold"),
            pytest.param(cards("C7 C8 C9 CT CJ CQ CK CA S7 S8 S9 ST SJ SQ SK SA H7 H8 H9 HT HJ HQ HK HA"), id="a-deck"),
        ],
    )
    def test_refuses_more_cards_than_a_seat_can_hold_with_422_and_stores_nothing(self, skat, put):
        table = stage_table(skat)
        accepted(table, FOREHAND, "take")
        before = stored(skat)

        answer = step(table, FOREHAND, "put-back", put)

        assert answer.status_code == 422
        assert stored(skat) == before

    def test_refuses_what_the_table_refuses_before_the_engine(self, skat):
        table = stage_table(skat)
        before = table.record

        table.refused_act(SUFFIXES["take"], table.watcher, "not-seated")
        table.refused_act(SUFFIXES["take"], table.at[FOREHAND], "stale-version", body={"version": before.version - 1})
        skat.store.tables[table.table_id] = replace(before, hand=None)
        table.refused_act(SUFFIXES["take"], table.at[FOREHAND], "no-hand")

    def test_refuses_a_step_after_the_stage_and_at_a_declared_game_as_wrong_phase(self, skat):
        after_the_stage = stage_table(skat)
        play_stage(after_the_stage, "push", "push", "push")
        declared = Table(skat, {"ramsch": {**POINTS, "pushing": {"rule": "jacks-stay"}}})
        declared.declared_hand_game()

        refused(after_the_stage, FOREHAND, "take", "wrong-phase")
        refused(declared, FOREHAND, "take", "wrong-phase")

    def test_weiter_and_neue_serie_are_refused_as_in_any_running_hand(self, skat):
        table = stage_table(skat)
        people = headers_of(table)
        tap = tap_weiter(skat, people[0], table.table_id, "tap-0001")
        new_series = tap_new_series(skat, people[0], table.table_id, "new-series-0001")

        assert [reason_of(each) for each in (tap, new_series)] == ["no-result", "series-not-over"]

    def test_standing_up_in_the_push_stage_opens_the_chair_and_the_stage_waits_until_a_sitter_comes(self, skat):
        table = stage_table(skat)
        stage = table.record.progress.pushing

        stood = skat.stand(headers_of(table)[0], table.table_id)
        refused(table, FOREHAND, "take", "seat-open")
        sat = skat.sit(table.watcher, table.table_id, 1)

        assert (stood.status_code, stood.json()["hand"]["waiting_seat"]) == (200, 1)
        assert (sat.status_code, sat.json()["hand"]["waiting_seat"]) == (200, None)
        assert table.record.progress.pushing == stage
        accepted(table, FOREHAND, "take")


# Forehand put back C7 C8, middlehand pushed and rearhand took them and put DT and C7 back (keeping C8), so the Ramsch
# is played with these hands and the skat DT C7. Forehand takes tricks 1, 8, 9 and 10 (0, 6, 18, 13 points) and the
# skat's 10 as the last trick's taker: 47. Middlehand takes tricks 2, 3 and 7 (0, 11, 24): 35. Rearhand takes tricks 4,
# 5 and 6 (15, 15, 8): 38. Forehand loses 47 and one push doubles it.
RESHAPED_HANDS = {
    FOREHAND: cards("C9 CT CJ CQ CK CA S7 S8 DK DA"),
    MIDDLEHAND: cards("S9 ST SJ SQ SK SA H7 H8 H9 HT"),
    REARHAND: cards("HJ HQ HK HA D7 D8 D9 DJ DQ C8"),
}
RESHAPED_GAME = game_of(
    "C9 H7 C8 / S7 S9 D8 / SA D9 S8 / ST HJ CQ / HA CK H8", "HK DK H9 / HQ DA HT / SJ DJ CJ / CA SK DQ / CT SQ D7"
)


class TestARamschPlayedOnTheCardsTheStageMoved:
    def test_the_cards_kept_and_the_skat_rearhand_put_back_decide_the_points_and_the_score(self, skat):
        table = stage_table(skat)
        accepted(table, FOREHAND, "take")
        accepted(table, FOREHAND, "put-back", cards("C7 C8"))
        accepted(table, MIDDLEHAND, "push")
        accepted(table, REARHAND, "take")
        accepted(table, REARHAND, "put-back", cards("DT C7"))
        holders = {played: position for position, held in RESHAPED_HANDS.items() for played in held}

        for played in RESHAPED_GAME:
            assert table.send(table.at[holders[played]], played).status_code == 200

        result = table.result()
        assert {seat["seat"]: (seat["points"], seat["score"]) for seat in result["seats"]} == {
            FOREHAND_SEAT: (47, -94),
            MIDDLEHAND_SEAT: (35, 0),
            REARHAND_SEAT: (38, 0),
        }
        assert (result["pushes"], result["push_factor"], result["bock_factor"]) == (1, 2, 1)


class TestTheMultiplier:
    @pytest.mark.parametrize(
        ("deal", "hand", "rule", "changed", "pending", "plan", "scores", "factors"),
        [
            pytest.param(
                PLAIN_DEAL,
                PLAIN_HAND,
                "jacks-stay",
                {},
                (),
                ("back", "push", "push"),
                [0, -344, 0],
                (2, 4, 1),
                id="two-pushes",
            ),
            pytest.param(
                PLAIN_DEAL,
                PLAIN_HAND,
                "jacks-may-go",
                {},
                (),
                ("back", "push", "push"),
                [0, -344, 0],
                (2, 4, 1),
                id="two-pushes-with-jacks-allowed",
            ),
            pytest.param(
                PLAIN_DEAL,
                PLAIN_HAND,
                "no-doubling",
                {},
                (),
                ("back", "push", "push"),
                [0, -86, 0],
                (2, 1, 1),
                id="two-pushes-that-do-not-double",
            ),
            pytest.param(
                PLAIN_DEAL,
                PLAIN_HAND,
                "jacks-stay",
                {},
                (2,),
                ("back", "push", "push"),
                [0, -688, 0],
                (2, 4, 2),
                id="two-pushes-at-a-bock-game",
            ),
            pytest.param(
                PLAIN_DEAL,
                PLAIN_HAND,
                "jacks-stay",
                {"scoring": "points-by-ten"},
                (),
                ("back", "push", "push"),
                [0, -32, 0],
                (2, 4, 1),
                id="divided-by-ten-before-the-pushes",
            ),
            pytest.param(
                JUNGFRAU_DEAL,
                JUNGFRAU_HAND,
                "jacks-stay",
                {"scoring": "points-by-ten"},
                (),
                ("back", "push", "push"),
                [-80, 0, 0],
                (2, 4, 1),
                id="divided-doubled-then-multiplied",
            ),
            pytest.param(
                SWEEP_DEAL,
                SWEEP_HAND,
                "jacks-stay",
                {},
                (),
                ("push", "back", "back"),
                [0, 0, 240],
                (1, 2, 1),
                id="a-sweep-multiplied-by-the-push",
            ),
            pytest.param(
                SWEEP_DEAL,
                SWEEP_HAND,
                "jacks-stay",
                {"durchmarsch": "wins-120-flat"},
                (),
                ("push", "back", "back"),
                [0, 0, 120],
                (1, 2, 1),
                id="a-flat-sweep-not-multiplied",
            ),
            pytest.param(
                SWEEP_DEAL,
                SWEEP_HAND,
                "jacks-stay",
                {},
                (2,),
                ("push", "back", "back"),
                [0, 0, 480],
                (1, 2, 2),
                id="a-sweep-at-a-bock-game-multiplied-by-both",
            ),
            pytest.param(
                SWEEP_DEAL,
                SWEEP_HAND,
                "jacks-stay",
                {"durchmarsch": "wins-120-flat"},
                (2,),
                ("push", "back", "back"),
                [0, 0, 120],
                (1, 2, 2),
                id="a-flat-sweep-at-a-bock-game",
            ),
        ],
    )
    def test_the_scores_are_multiplied_by_the_pushes_and_the_bock_factor_after_the_division_and_the_doubling(
        self, skat, deal, hand, rule, changed, pending, plan, scores, factors
    ):
        extra = {"bock": {"triggers": ["re"], "overlap": "append"}} if pending else None
        table = stage_table(skat, rule, deal, extra, **changed)
        if pending:
            with_pending(table, *pending)
        play_stage(table, *plan)

        table.played_out(hand)

        result = table.result()
        assert scores_of(result) == scores
        result_factors = (result["pushes"], result["push_factor"], result["bock_factor"])
        assert result_factors == factors
        row = list_rows(table)[0]
        row_factors = (row["pushes"], row["push_factor"], row["bock_factor"])
        assert row_factors == factors

    def test_a_pushed_ramsch_uses_up_a_pending_bock_game_and_starts_a_round_for_passed_in(self, skat):
        extra = {"bock": {"triggers": ["passed-in"], "overlap": "append"}}
        table = stage_table(skat, extra=extra)
        with_pending(table, 2)
        play_stage(table, "back", "push", "push")

        table.played_out(PLAIN_HAND)

        assert bock_of(table) == {"games_left": 4, "factor": 2}

    def test_a_pushed_ramsch_reads_the_multiplied_score_for_the_total_trigger(self, skat):
        extra = {"bock": {"triggers": ["total-ending-in-00"], "overlap": "append"}}
        table = stage_table(skat, extra=extra)
        with_totals(table, 0, 444, 0)
        play_stage(table, "back", "push", "push")

        table.played_out(PLAIN_HAND)

        assert bock_of(table) == {"games_left": 3, "factor": 2}

    def test_the_last_game_of_the_series_stores_both_factors_and_lets_every_round_lapse(self, skat):
        extra = {"bock": {"triggers": ["re"], "overlap": "append"}}
        table = stage_table(skat, extra=extra)
        with_pending(table, 2)
        skat.store.tables[table.table_id] = replace(table.record, series=Series(3, 3))
        play_stage(table, "back", "push", "push")

        table.played_out(PLAIN_HAND)

        result = table.result()
        assert (result["pushes"], result["push_factor"], result["bock_factor"]) == (2, 4, 2)
        assert table.record.bock == BockRounds(())

    def test_the_result_the_list_and_every_view_name_no_card(self, skat):
        table = stage_table(skat)
        play_stage(table, "back", "push", "push")
        table.played_out(PLAIN_HAND)

        for position in VIEWERS:
            assert not cards_in_text(table.read_as(table.watcher if position is None else table.at[position]).text)
        table.skat.client.cookies.clear()
        listed = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher)
        assert not cards_in_text(listed.text)

    def test_weiter_after_a_pushed_ramsch_deals_a_hand_whose_stage_starts_with_no_step_and_no_push(self, skat):
        table = stage_table(skat)
        play_stage(table, "back", "push", "push")
        table.played_out(PLAIN_HAND)

        deal_the_next_game(skat, table, 1, 1)

        dealt = read(table, FOREHAND)["hand"]
        assert (dealt["ramsch"], dealt["pushing"], dealt["pushes"]) == (False, None, 0)
        assert table.record.progress.pushing == ()
        three_pass(table)
        stage = read(table, FOREHAND)["hand"]
        assert stage["pushing"] == {"turn_seat": FOREHAND_SEAT, "stage": "choosing", "moves": [], "factor": 1}
        assert stage["pushes"] == 0


class TestWhoLearnsTheSkat:
    @staticmethod
    def named(table):
        return {
            position: cards_in_text(table.read_as(table.watcher if position is None else table.at[position]).text)
            for position in VIEWERS
        }

    def test_only_the_seat_holding_the_skat_names_it_and_nobody_names_the_cards_put_back_until_the_next_taker(
        self, skat
    ):
        table = stage_table(skat)
        forehand, middlehand, rearhand = (
            set(wire_cards(getattr(PLAIN_DEAL, name))) for name in ("forehand", "middlehand", "rearhand")
        )
        skat_cards = set(wire_cards(PLAIN_DEAL.skat))
        put_back = set(wire_cards(cards("C7 C8")))

        assert self.named(table) == {FOREHAND: forehand, MIDDLEHAND: middlehand, REARHAND: rearhand, None: set()}
        accepted(table, FOREHAND, "take")
        assert self.named(table) == {
            FOREHAND: forehand | skat_cards,
            MIDDLEHAND: middlehand,
            REARHAND: rearhand,
            None: set(),
        }
        accepted(table, FOREHAND, "put-back", cards("C7 C8"))
        assert self.named(table) == {
            FOREHAND: (forehand | skat_cards) - put_back,
            MIDDLEHAND: middlehand,
            REARHAND: rearhand,
            None: set(),
        }
        accepted(table, MIDDLEHAND, "take")
        assert self.named(table) == {
            FOREHAND: (forehand | skat_cards) - put_back,
            MIDDLEHAND: middlehand | put_back,
            REARHAND: rearhand,
            None: set(),
        }
        accepted(table, MIDDLEHAND, "put-back", cards("S9 ST"))
        assert not (put_back & (self.named(table)[REARHAND] | self.named(table)[None]))

    def test_the_event_stream_of_every_viewer_names_only_what_the_viewer_holds(self, server):
        table = stage_table(server)
        members = [(table.at[position], None) for position in (FOREHAND, MIDDLEHAND, REARHAND)] + [
            (table.watcher, None)
        ]
        taken = set(wire_cards(PLAIN_DEAL.skat))

        with streams_of(server, table.table_id, members) as streams:
            version = table.record.version + 1
            accepted(table, FOREHAND, "take")
            messages = [next(view for view in stream if view["version"] == version) for stream in streams]

        named = [cards_in(message) for message in messages]
        assert [bool(taken & each) for each in named] == [True, False, False, False]


class TestARetriedStep:
    @pytest.mark.parametrize("kind", ["take", "push", "put-back"])
    def test_the_same_id_and_version_answers_the_same_and_stores_one_step(self, skat, kind):
        table = stage_table(skat)
        if kind == "put-back":
            accepted(table, FOREHAND, "take")
        stored = len(table.record.progress.pushing)
        version = table.record.version
        retry = {
            "command_id": "retry-0001",
            "version": version,
            **(step_body(cards("C7 C8")) if kind == "put-back" else {}),
        }

        first = table.act(SUFFIXES[kind], table.at[FOREHAND], body=retry)
        again = table.act(SUFFIXES[kind], table.at[FOREHAND], body=retry)

        assert (again.status_code, again.json()) == (first.status_code, first.json())
        assert (len(table.record.progress.pushing), table.record.version) == (stored + 1, version + 1)

    def test_the_same_id_with_other_cards_is_refused_and_the_first_put_back_stays(self, skat):
        table = stage_table(skat)
        accepted(table, FOREHAND, "take")
        retry = {"command_id": "retry-0001", "version": table.record.version}
        table.act(SUFFIXES["put-back"], table.at[FOREHAND], body={**retry, **step_body(cards("C7 C8"))})
        stored = table.record

        other = table.act(SUFFIXES["put-back"], table.at[FOREHAND], body={**retry, **step_body(cards("S7 S8"))})

        assert other.status_code == 409
        assert table.record == stored
        assert cards_in(read(table, FOREHAND)["hand"]["own_cards"]) >= wire_cards(cards("S7 S8"))
        assert not cards_in(read(table, FOREHAND)["hand"]["own_cards"]) & wire_cards(cards("C7 C8"))

    def test_the_same_id_for_another_step_is_refused_and_a_refused_step_keeps_its_refusal(self, skat):
        table = stage_table(skat)
        version = table.record.version
        retry = {"command_id": "retry-0001", "version": version}
        table.act(SUFFIXES["take"], table.at[FOREHAND], body=retry)

        other = table.act(SUFFIXES["push"], table.at[FOREHAND], body=retry)
        refused_first = table.act(SUFFIXES["push"], table.at[MIDDLEHAND], body={**retry, "command_id": "retry-0002"})
        refused_again = table.act(SUFFIXES["push"], table.at[MIDDLEHAND], body={**retry, "command_id": "retry-0002"})

        assert other.status_code == 409
        assert (refused_first.status_code, refused_again.status_code) == (409, 409)
        assert reason_of(refused_first) == reason_of(refused_again) == "stale-version"
        assert len(table.record.progress.pushing) == 1


class TestThePausedList:
    @pytest.fixture
    def clock(self):
        return [DEALT_AT]

    @pytest.fixture
    def skat(self, hold, issuer, clock):
        skat = Skat(lambda: hold, issuer_transports=issuer.transports, now=lambda: clock[0])
        with skat.client:
            yield skat

    @staticmethod
    def entry_of(table):
        table.skat.client.cookies.clear()
        answer = table.skat.client.get(PAUSED_TABLES_PATH, headers=table.at[FOREHAND])
        (entry,) = answer.json()["tables"]
        return entry["turn_seat"], entry["ends_at"]

    def test_names_the_seat_on_turn_through_the_stage_and_only_a_played_card_moves_the_end(self, skat, clock):
        table = stage_table(skat)
        _, dealt_end = self.entry_of(table)
        clock[0] += timedelta(hours=1)

        accepted(table, FOREHAND, "take")
        assert self.entry_of(table) == (FOREHAND_SEAT, dealt_end)
        accepted(table, FOREHAND, "put-back", cards("C7 C8"))
        assert self.entry_of(table) == (MIDDLEHAND_SEAT, dealt_end)
        accepted(table, MIDDLEHAND, "push")
        accepted(table, REARHAND, "push")
        assert self.entry_of(table) == (FOREHAND_SEAT, dealt_end)
        table.accepted(cards("C9")[0])
        turn_seat, played_end = self.entry_of(table)
        assert played_end != dealt_end
        assert turn_seat == MIDDLEHAND_SEAT
