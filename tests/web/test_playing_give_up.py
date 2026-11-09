import json
from functools import partial

import pytest

from skat.engine.deal import Position, next_dealer
from skat.engine.tricks import ALL_POINTS, PlayRefusal
from skat.table.records import SERIES_LENGTH_MIN, Refusal
from skat.web.declaring import GameToken
from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLES_PATH, AnnouncementToken
from tests.support.payload_cards import DEALER_SEAT, cards_in_text
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import Table, card, cards, game_of, reason_of
from tests.web.support.presence import OvertakenStore, occupied_seats, pass_hand_in
from tests.web.support.skat import UNKNOWN_ID, Skat, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# Middlehand declares; the known deal's first trick is S7 S9 D7, which he takes with S9 and leads the next.
FIRST_TRICK = cards("S7 S9 D7")
HERZ_GAME = game_of(
    "S7 S9 D7 / H7 DJ CJ / S8 ST D8 / SQ D9 C7 / SK DT C8",
    "SA DQ C9 / SJ HJ CT / H8 HQ CQ / HK CK H9 / HA CA HT",
)
FIRST_RESULT = 1
HERZ_HAND_LOST_AT_30 = {"won": False, "game_value": 30, "settled_value": 30, "score": -60}


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


def give_up(table, headers=None, *, body=None):
    table.skat.client.cookies.clear()
    return table.skat.client.post(
        f"{TABLES_PATH}/{table.table_id}{TABLE_GIVE_UP_SUFFIX}",
        json={"command_id": table.fresh_id(), "version": table.record.version} | (body or {}),
        headers={"origin": TEST_PUBLIC_ORIGIN, **(headers or table.at[MIDDLEHAND])},
    )


def refused(table, headers, reason, **kwargs):
    before = table.record
    answer = give_up(table, headers, **kwargs)
    assert answer.status_code == 409, answer.text
    assert reason_of(answer) == reason
    assert table.record == before


def ready(table, position):
    table.skat.client.cookies.clear()
    answer = table.skat.client.post(
        f"{TABLES_PATH}/{table.table_id}{TABLE_READY_SUFFIX}",
        json={"command_id": table.fresh_id(), "ordinal": FIRST_RESULT},
        headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[position]},
    )
    assert answer.status_code == 200, answer.text


def everyone_connected(table):
    return streams_of(table.skat, table.table_id, [(headers, None) for headers in table.at.values()])


def people_in_turn(table):
    return [(table.at[position], None) for position in (MIDDLEHAND, REARHAND, FOREHAND)]


def given_up(table):
    table.declared_hand_game()
    give_up(table)


def played_out(table):
    table.declared_hand_game()
    table.played_out(HERZ_GAME)


def null_ended_early(table):
    table.declared_hand_game(GameToken.NULL)
    table.played_out(cards("S7 SJ D7"))


def schwarz_announced_ended_early(table):
    # The declarer takes the first trick and loses the second, which ends a Schwarz-announced game.
    table.declared_grand_ouvert()
    table.played_out(cards("S7 S9 D7 H7 HQ C7"))


def points_of_cards(played):
    return sum(each.points for each in played)


class TestTheDeclarerGivesUp:
    def test_with_ten_cards_the_game_is_lost_at_once_and_the_hand_ends(self, herz_hand):
        answer = give_up(herz_hand)

        assert answer.status_code == 200, answer.text
        assert herz_hand.record.hand is None
        assert len(herz_hand.record.game_list) == 1
        result = answer.json()["result"]
        assert {key: result[key] for key in HERZ_HAND_LOST_AT_30} == HERZ_HAND_LOST_AT_30

    def test_with_nine_cards_after_a_trick_the_game_is_given_up_without_consent(self, herz_hand):
        herz_hand.played_out(FIRST_TRICK)

        assert give_up(herz_hand).status_code == 200

    def test_the_declarers_points_are_those_of_his_completed_tricks_and_the_opponents_hold_the_rest(self, herz_hand):
        herz_hand.played_out(FIRST_TRICK)

        result = give_up(herz_hand).json()["result"]

        assert result["declarer_points"] == points_of_cards(FIRST_TRICK)
        assert result["opponents_points"] == ALL_POINTS - points_of_cards(FIRST_TRICK)

    def test_off_turn_mid_trick_the_open_trick_counts_nothing_for_the_declarer(self, table):
        table.declared_hand_game()
        table.accepted(card("CA"))
        table.accepted(card("SA"))

        answer = give_up(table)

        assert answer.status_code == 200, answer.text
        result = answer.json()["result"]
        assert result["declarer_points"] == 0
        assert result["opponents_points"] == ALL_POINTS

    def test_the_skat_never_shows_in_the_points(self, herz_hand):
        result = give_up(herz_hand).json()["result"]

        assert result["declarer_points"] == 0

    def test_the_entry_is_stored_lost_and_the_gains_follow(self, herz_hand):
        result = give_up(herz_hand).json()["result"]

        assert herz_hand.result() == result
        assert result["won"] is False
        assert [gain["won"] for gain in result["gains"]] == [False, True, True]
        assert result["gains"][0]["gain"] < 0 < result["gains"][1]["gain"]

    @pytest.mark.parametrize(
        ("changes", "levels"),
        [
            pytest.param({"announcement": AnnouncementToken.NONE}, ["spiel", "hand"], id="not-announced"),
            pytest.param(
                {"announcement": AnnouncementToken.SCHNEIDER},
                ["spiel", "hand", "schneider", "schneider_announced"],
                id="schneider-announced",
            ),
        ],
    )
    def test_only_the_levels_announced_are_suffered(self, table, changes, levels):
        table.declared_hand_game(**changes)

        assert give_up(table).json()["result"]["levels"] == levels

    def test_a_bid_over_the_value_is_overbid_and_settled_at_the_next_multiple(self, table):
        table.declared_hand_game(bid=33)

        result = give_up(table).json()["result"]

        assert {key: result[key] for key in ("overbid", "game_value", "settled_value", "score")} == {
            "overbid": True,
            "game_value": 30,
            "settled_value": 40,
            "score": -80,
        }

    @pytest.mark.parametrize(
        ("ouvert", "value", "score"),
        [pytest.param(False, 35, -70, id="null-hand"), pytest.param(True, 59, -118, id="null-hand-ouvert")],
    )
    def test_a_null_is_lost_at_its_fixed_value_without_matadors(self, table, ouvert, value, score):
        table.declared_hand_game(GameToken.NULL, ouvert=ouvert)

        result = give_up(table).json()["result"]

        assert (result["won"], result["matadors"], result["game_value"], result["score"]) == (
            False,
            None,
            value,
            score,
        )

    def test_an_ouvert_declarers_open_cards_go_with_the_hand(self, table):
        table.declared_grand_ouvert()
        table.accepted(card("S7"))

        give_up(table)

        for headers in (table.watcher, *table.at.values()):
            assert cards_in_text(table.read_as(headers).text) == set()


class TestRefusals:
    def test_with_eight_cards_the_opponents_must_agree_and_nothing_changes(self, herz_hand):
        herz_hand.played_out(FIRST_TRICK)
        herz_hand.accepted(card("H7"))

        refused(herz_hand, herz_hand.at[MIDDLEHAND], PlayRefusal.NEEDS_CONSENT)

    @pytest.mark.parametrize("position", [FOREHAND, REARHAND], ids=lambda position: position.name)
    def test_an_opponent_is_not_the_declarer(self, herz_hand, position):
        refused(herz_hand, herz_hand.at[position], Refusal.NOT_DECLARER)

    def test_a_watcher_is_not_seated(self, herz_hand):
        refused(herz_hand, herz_hand.watcher, Refusal.NOT_SEATED)

    def test_the_auction_is_the_wrong_phase(self, table):
        refused(table, table.at[MIDDLEHAND], Refusal.WRONG_PHASE)

    def test_the_declaring_is_the_wrong_phase(self, table):
        table.middlehand_wins()

        refused(table, table.at[MIDDLEHAND], Refusal.WRONG_PHASE)

    def test_without_a_hand_there_is_nothing_to_give_up(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_GIVE_UP_SUFFIX}",
            json={"command_id": "command-give-up", "version": 1},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

        assert (answer.status_code, reason_of(answer)) == (409, Refusal.NO_HAND)

    @pytest.mark.parametrize(
        "hand_ended",
        [given_up, played_out, null_ended_early, schwarz_announced_ended_early],
        ids=lambda scene: scene.__name__,
    )
    def test_after_the_hand_ended_there_is_no_hand(self, table, hand_ended):
        hand_ended(table)
        assert table.record.hand is None

        refused(table, table.at[MIDDLEHAND], Refusal.NO_HAND)

    def test_after_a_hand_passed_in_there_is_no_hand(self, table):
        pass_hand_in(table.skat, table.table_id, people_in_turn(table))
        assert table.record.hand is None

        refused(table, table.at[MIDDLEHAND], Refusal.NO_HAND)

    def test_a_stale_version_is_refused(self, herz_hand):
        refused(herz_hand, herz_hand.at[MIDDLEHAND], Refusal.STALE_VERSION, body={"version": 0})

    def test_an_unknown_table_is_not_found(self, herz_hand, skat):
        answer = skat.client.post(
            f"{TABLES_PATH}/{UNKNOWN_ID}{TABLE_GIVE_UP_SUFFIX}",
            json={"command_id": "command-give-up", "version": 1},
            headers={"origin": TEST_PUBLIC_ORIGIN, **herz_hand.at[MIDDLEHAND]},
        )

        assert answer.status_code == 404

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"consented": True}, id="consent-sent"),
            pytest.param({"series_length": SERIES_LENGTH_MIN}, id="series-length-sent"),
            pytest.param({"version": "3"}, id="version-as-text"),
            pytest.param({"version": None}, id="version-missing"),
        ],
    )
    def test_a_body_outside_the_contract_is_refused_and_stores_nothing(self, herz_hand, body):
        before = herz_hand.record
        payload = {"command_id": "command-give-up", "version": before.version} | body
        payload = {key: value for key, value in payload.items() if value is not None}

        answer = herz_hand.skat.client.post(
            f"{TABLES_PATH}/{herz_hand.table_id}{TABLE_GIVE_UP_SUFFIX}",
            content=json.dumps(payload),
            headers={
                "origin": TEST_PUBLIC_ORIGIN,
                "content-type": "application/json",
                **herz_hand.at[MIDDLEHAND],
            },
        )

        assert answer.status_code == 422
        assert herz_hand.record == before


class TestRetries:
    def test_the_same_id_and_version_answer_the_same_and_write_one_entry(self, herz_hand):
        body = {"command_id": "command-give-up", "version": herz_hand.record.version}
        first = give_up(herz_hand, body=body)

        again = give_up(herz_hand, body=body)

        assert again.status_code == 200
        assert again.json() == first.json()
        assert len(herz_hand.record.game_list) == 1

    def test_a_refused_retry_returns_the_same_refusal(self, herz_hand):
        body = {"command_id": "command-give-up"}
        first = give_up(herz_hand, herz_hand.at[FOREHAND], body=body)

        again = give_up(herz_hand, herz_hand.at[FOREHAND], body=body)

        assert (again.status_code, again.json()) == (first.status_code, first.json())

    def test_the_same_id_with_another_version_is_reused(self, herz_hand):
        version = herz_hand.record.version
        give_up(herz_hand, body={"command_id": "command-give-up", "version": version})

        again = give_up(herz_hand, body={"command_id": "command-give-up", "version": version - 1})

        assert again.status_code == 409
        assert "reused" in again.json()["detail"]

    def test_the_same_id_on_a_card_is_reused(self, herz_hand):
        herz_hand.accepted(card("S7"), command_id="command-shared")

        again = give_up(herz_hand, herz_hand.at[FOREHAND], body={"command_id": "command-shared"})

        assert again.status_code == 409
        assert "reused" in again.json()["detail"]


class TestAfterTheGiveUp:
    def test_all_three_readies_deal_the_next_hand_with_the_dealer_moved(self, server):
        table = Table(server)
        table.declared_hand_game()
        give_up(table)

        with everyone_connected(table):
            for position in table.at:
                ready(table, position)

        assert table.record.hand is not None
        assert table.record.dealer == next_dealer(DEALER_SEAT)
        assert len(table.record.game_list) == 1

    def test_a_give_up_retried_after_the_next_deal_is_replayed_and_the_new_hand_runs_on(self, server):
        table = Table(server)
        table.declared_hand_game()
        body = {"command_id": "command-give-up", "version": table.record.version}
        first = give_up(table, body=body)
        with everyone_connected(table):
            for position in table.at:
                ready(table, position)
        dealt = table.record

        again = give_up(table, body=body)

        assert again.status_code == 200
        assert (first.status_code, again.json()["version"]) == (200, dealt.version)
        assert table.record == dealt
        assert len(table.record.game_list) == 1

    def test_an_old_expiry_reaching_the_table_right_after_the_give_up_committed_leaves_the_fresh_hold_alone(
        self, hold, time
    ):
        store = OvertakenStore()
        server = Skat(lambda: hold, store=store, chair_clock=time.clock, chair_scheduler=time)
        with server.client:
            table = Table(server)
            with streams_of(server, table.table_id, [(table.at[FOREHAND], None)]):
                pass
            table.declared_hand_game()
            server.client.portal.call(time.advance, hold.settings.chair_hold_seconds - 1)
            store.after_commit = partial(server.client.portal.call, time.advance, 1)

            give_up(table)

            assert occupied_seats(server, table.table_id) == {1, 2, 3}
            server.client.portal.call(time.advance, hold.settings.chair_hold_seconds - 1)
            assert occupied_seats(server, table.table_id) == {1, 2, 3}
            server.client.portal.call(time.advance, 2)
            assert occupied_seats(server, table.table_id) == set()
