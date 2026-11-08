import itertools

import pytest

from skat.engine.bidding import Bid, Declared, Hold, Pass, PassedIn
from skat.engine.deal import Position, positions_from
from skat.table.hand_state import auction_of
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, seated_three
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import FETCH, UNKNOWN_ID

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
BID, HOLD, PASS, PLAY = "bid", "hold", "pass", "play"
NOT_YOUR_TURN, OVER, STALE_VERSION = "not-your-turn", "over", "stale-version"


class Table:
    """A dealt table whose four people are told apart by position, with the watcher left over."""

    def __init__(self, skat):
        self.skat = skat
        self.table_id, people = seated_three(skat)
        by_seat = {seat: people[seat - 1][0] for seat in (1, 2, 3)}
        self.at = {position: by_seat[seat] for seat, position in positions_from(DEALER_SEAT).items()}
        self.watcher = people[3][0]
        self._commands = itertools.count(1)

    @property
    def record(self):
        return self.skat.store.tables[self.table_id]

    def send(self, headers, action, value=None, *, command_id=None, version=None, **extra):
        body = {
            "command_id": command_id or f"command-{next(self._commands):04d}",
            "version": self.record.version if version is None else version,
            "action": action,
            **({} if value is None else {"value": value}),
            **extra,
        }
        return self.skat.client.post(
            f"{TABLES_PATH}/{self.table_id}{TABLE_AUCTION_SUFFIX}",
            json=body,
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

    def accepted(self, position, action, value=None, **options):
        before = self.record
        answer = self.send(self.at[position], action, value, **options)
        assert answer.status_code == 200, answer.text
        assert self.record.version == before.version + 1
        assert len(self.record.progress.auction) == len(before.progress.auction) + 1
        return answer

    def play_out(self, script):
        for position, action, *value in script:
            self.accepted(position, action, *value)

    def refused(self, headers, action, value, reason, **options):
        before = self.record
        answer = self.send(headers, action, value, **options)
        assert answer.status_code == 409, answer.text
        assert answer.json()["reason"] == reason
        assert self.record == before
        return answer


@pytest.fixture
def table(skat):
    return Table(skat)


class TestAccepted:
    def test_bids_and_answers_are_stored_in_order(self, table):
        table.play_out([(MIDDLEHAND, BID, 18), (FOREHAND, HOLD), (MIDDLEHAND, BID, 20), (FOREHAND, PASS)])

        assert table.record.progress.auction == (
            Bid(MIDDLEHAND, 18),
            Hold(FOREHAND),
            Bid(MIDDLEHAND, 20),
            Pass(FOREHAND),
        )

    @pytest.mark.parametrize(
        ("script", "declarer", "value"),
        [
            pytest.param(
                [
                    (MIDDLEHAND, BID, 18),
                    (FOREHAND, HOLD),
                    (MIDDLEHAND, BID, 20),
                    (FOREHAND, PASS),
                    (REARHAND, BID, 22),
                    (MIDDLEHAND, PASS),
                ],
                REARHAND,
                22,
                id="rearhand-outbids-middlehand",
            ),
            pytest.param(
                [(MIDDLEHAND, PASS), (REARHAND, BID, 18), (FOREHAND, HOLD), (REARHAND, BID, 20), (FOREHAND, PASS)],
                REARHAND,
                20,
                id="rearhand-against-forehand",
            ),
            pytest.param([(MIDDLEHAND, PASS), (REARHAND, PASS), (FOREHAND, PLAY)], FOREHAND, 18, id="forehand-plays"),
        ],
    )
    def test_the_auction_ends_with_its_declarer_and_further_commands_are_over(self, table, script, declarer, value):
        table.play_out(script)

        assert auction_of(table.record).result == Declared(declarer, value)
        table.refused(table.at[REARHAND], PASS, None, OVER)

    def test_three_passes_pass_the_hand_in_and_the_hand_stays(self, table):
        table.play_out([(MIDDLEHAND, PASS), (REARHAND, PASS), (FOREHAND, PASS)])

        assert auction_of(table.record).result == PassedIn()
        assert table.record.hand is not None

    def test_a_bidder_may_skip_values(self, table):
        table.accepted(MIDDLEHAND, BID, 22)

        assert table.record.progress.auction == (Bid(MIDDLEHAND, 22),)

    def test_an_accepted_step_answers_with_the_viewers_table_and_no_cache(self, table):
        answer = table.accepted(MIDDLEHAND, BID, 18)

        assert answer.json()["version"] == table.record.version
        assert answer.headers["cache-control"] == "no-store"


class TestRefused:
    def test_forehand_cannot_open_the_auction(self, table):
        table.refused(table.at[FOREHAND], PASS, None, NOT_YOUR_TURN)

    @pytest.mark.parametrize("value", [17, 265, 19])
    def test_a_value_that_is_no_game_value_is_refused(self, table, value):
        table.refused(table.at[MIDDLEHAND], BID, value, "invalid-value")

    @pytest.mark.parametrize("value", [20, 18])
    def test_a_bid_not_above_the_standing_one_is_refused(self, table, value):
        table.play_out([(MIDDLEHAND, BID, 20), (FOREHAND, HOLD)])

        table.refused(table.at[MIDDLEHAND], BID, value, "not-above-standing")

    @pytest.mark.parametrize(
        ("action", "value"),
        [
            pytest.param(BID, 18, id="bid"),
            pytest.param(HOLD, None, id="hold"),
            pytest.param(PASS, None, id="pass"),
            pytest.param(PLAY, None, id="play"),
        ],
    )
    def test_a_passed_player_cannot_take_their_word_back(self, table, action, value):
        table.accepted(MIDDLEHAND, PASS)

        table.refused(table.at[MIDDLEHAND], action, value, "already-passed")

    def test_the_bidder_cannot_answer_their_own_bid(self, table):
        table.refused(table.at[MIDDLEHAND], HOLD, None, "wrong-action")

    def test_the_responder_cannot_bid_out_of_turn(self, table):
        table.refused(table.at[FOREHAND], BID, 18, NOT_YOUR_TURN)

    def test_a_member_without_a_chair_is_refused(self, table):
        table.refused(table.watcher, BID, 18, "not-seated")

    def test_a_table_without_a_hand_is_refused(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_SUFFIX}",
            json={"command_id": "command-0001", "version": 1, "action": PASS},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

        assert answer.status_code == 409
        assert answer.json()["reason"] == "no-hand"
        assert answer.headers["cache-control"] == "no-store"

    def test_an_unknown_table_answers_404(self, skat):
        headers, _ = skat.member()

        answer = skat.client.post(
            f"{TABLES_PATH}/{UNKNOWN_ID}{TABLE_AUCTION_SUFFIX}",
            json={"command_id": "command-0001", "version": 1, "action": PASS},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

        assert answer.status_code == 404

    def test_signed_out_is_refused_and_changes_nothing(self, table):
        before = table.record

        answer = table.send(FETCH, PASS)

        assert answer.status_code == 401
        assert table.record == before

    @pytest.mark.parametrize(
        ("action", "extra"),
        [
            pytest.param(BID, {"value": 18, "seat": 1}, id="names-a-seat"),
            pytest.param(BID, {"value": 18, "position": "forehand"}, id="names-a-position"),
            pytest.param(HOLD, {"value": 18}, id="hold-with-a-value"),
            pytest.param(PASS, {"value": 18}, id="pass-with-a-value"),
            pytest.param(PLAY, {"value": 18}, id="play-with-a-value"),
            pytest.param(BID, {}, id="bid-without-a-value"),
            pytest.param("raise", {}, id="unknown-action"),
        ],
    )
    def test_a_body_that_breaks_the_contract_is_refused_and_stores_nothing(self, table, action, extra):
        before = table.record

        answer = table.send(table.at[MIDDLEHAND], action, **extra)

        assert answer.status_code == 422
        assert table.record == before


class TestRetry:
    def test_a_repeated_acceptance_answers_the_same_and_changes_nothing(self, table):
        version = table.record.version
        first = table.send(table.at[MIDDLEHAND], BID, 18, command_id="command-same", version=version)
        after_first = table.record

        again = table.send(table.at[MIDDLEHAND], BID, 18, command_id="command-same", version=version)

        assert again.status_code == 200
        assert again.json() == first.json()
        assert table.record == after_first

    def test_a_repeated_refusal_answers_the_same_refusal(self, table):
        first = table.refused(table.at[FOREHAND], PASS, None, NOT_YOUR_TURN, command_id="command-same")

        again = table.refused(table.at[FOREHAND], PASS, None, NOT_YOUR_TURN, command_id="command-same")

        assert again.json() == first.json()

    @pytest.mark.parametrize(
        ("action", "value", "version_offset"),
        [
            pytest.param(BID, 20, 0, id="another-value"),
            pytest.param(PASS, None, 0, id="another-action"),
            pytest.param(BID, 18, 1, id="another-version"),
        ],
    )
    def test_the_same_id_with_another_body_is_refused_as_reused(self, table, action, value, version_offset):
        version = table.record.version
        table.accepted(MIDDLEHAND, BID, 18, command_id="command-same", version=version)
        after_first = table.record

        answer = table.send(
            table.at[MIDDLEHAND], action, value, command_id="command-same", version=version + version_offset
        )

        assert answer.status_code == 409
        assert "reused" in answer.json()["detail"]
        assert table.record == after_first

    def test_a_fresh_id_with_the_old_version_is_stale(self, table):
        old_version = table.record.version
        table.accepted(MIDDLEHAND, BID, 18)

        table.refused(table.at[FOREHAND], HOLD, None, STALE_VERSION, version=old_version)

    def test_a_retry_with_its_old_version_is_the_replay_not_stale(self, table):
        old_version = table.record.version
        table.accepted(MIDDLEHAND, BID, 18, command_id="command-same", version=old_version)
        after_first = table.record

        again = table.send(table.at[MIDDLEHAND], BID, 18, command_id="command-same", version=old_version)

        assert again.status_code == 200
        assert table.record == after_first


class TestOtherCommandsDuringAnAuction:
    def test_standing_up_while_an_auction_runs_is_refused(self, table):
        table.accepted(MIDDLEHAND, BID, 18)
        before = table.record

        answer = table.skat.stand(table.at[MIDDLEHAND], table.table_id)

        assert answer.json()["reason"] == "hand-running"
        assert table.record == before

    def test_a_fourth_member_sitting_while_an_auction_runs_is_refused(self, table):
        table.accepted(MIDDLEHAND, BID, 18)
        before = table.record

        answer = table.skat.sit(table.watcher, table.table_id, 2)

        assert answer.json()["reason"] == "seat-taken"
        assert table.record == before
