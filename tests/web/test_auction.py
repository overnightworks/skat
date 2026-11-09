import itertools

import pytest

from skat.engine.bidding import VALID_BIDS, Bid, BidRefusal, Declared, Hold, Pass
from skat.engine.deal import Position, next_dealer, positions_from
from skat.table.auction import AuctionAction
from skat.table.hand_state import auction_of
from skat.table.records import Refusal
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, cards_in_text, seated_three
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import FETCH, UNKNOWN_ID

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
BID, HOLD, PASS, PLAY = AuctionAction.BID, AuctionAction.HOLD, AuctionAction.PASS, AuctionAction.PLAY
NOT_YOUR_TURN, OVER, STALE_VERSION = BidRefusal.NOT_YOUR_TURN, BidRefusal.OVER, Refusal.STALE_VERSION
SAME_COMMAND = "command-same"
PASSES = [(MIDDLEHAND, PASS), (REARHAND, PASS), (FOREHAND, PASS)]
VALUE_FIELD = "value"


def post_step(skat, headers, table_id, *, command_id, version, action, **fields):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_SUFFIX}",
        json={"command_id": command_id, "version": version, "action": action, **fields},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def reason_of(answer):
    return answer.json()["reason"]


class Table:
    """A dealt table whose four people are told apart by position, with the watcher left over."""

    def __init__(self, skat):
        self.skat = skat
        self.table_id, people = seated_three(skat)
        by_seat = {seat: people[seat - 1][0] for seat in (1, 2, 3)}
        self.seats = by_seat
        self.at = {position: by_seat[seat] for seat, position in positions_from(DEALER_SEAT).items()}
        self.watcher = people[3][0]
        self._commands = itertools.count(1)

    @property
    def record(self):
        return self.skat.store.tables[self.table_id]

    def send(self, headers, action, value=None, *, command_id=None, version=None, **extra):
        return post_step(
            self.skat,
            headers,
            self.table_id,
            command_id=command_id or f"step-{next(self._commands):04d}",
            version=self.record.version if version is None else version,
            action=action,
            **({} if value is None else {VALUE_FIELD: value}),
            **extra,
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
        assert reason_of(answer) == reason
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
        table.refused(table.at[MIDDLEHAND], BID, value, BidRefusal.INVALID_VALUE)

    @pytest.mark.parametrize("value", [20, 18])
    def test_a_bid_not_above_the_standing_one_is_refused(self, table, value):
        table.play_out([(MIDDLEHAND, BID, 20), (FOREHAND, HOLD)])

        table.refused(table.at[MIDDLEHAND], BID, value, BidRefusal.NOT_ABOVE_STANDING)

    @pytest.mark.parametrize(
        "step",
        [
            pytest.param((BID, 18), id="bid"),
            pytest.param((HOLD, None), id="hold"),
            pytest.param((PASS, None), id="pass"),
            pytest.param((PLAY, None), id="play"),
        ],
    )
    def test_a_passed_player_cannot_take_their_word_back(self, table, step):
        table.accepted(MIDDLEHAND, PASS)

        table.refused(table.at[MIDDLEHAND], *step, BidRefusal.ALREADY_PASSED)

    def test_the_bidder_cannot_answer_their_own_bid(self, table):
        table.refused(table.at[MIDDLEHAND], HOLD, None, BidRefusal.WRONG_ACTION)

    def test_the_responder_cannot_bid_out_of_turn(self, table):
        table.refused(table.at[FOREHAND], BID, 18, NOT_YOUR_TURN)

    def test_a_member_without_a_chair_is_refused(self, table):
        table.refused(table.watcher, BID, 18, Refusal.NOT_SEATED)

    def test_a_table_without_a_hand_is_refused(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = post_step(skat, headers, table_id, command_id="step-0001", version=1, action=PASS)

        assert answer.status_code == 409
        assert reason_of(answer) == "no-hand"
        assert answer.headers["cache-control"] == "no-store"

    def test_an_unknown_table_answers_404(self, skat):
        headers, _ = skat.member()

        answer = post_step(skat, headers, UNKNOWN_ID, command_id="step-0001", version=1, action=PASS)

        assert answer.status_code == 404

    def test_signed_out_is_refused_and_changes_nothing(self, table):
        before = table.record

        answer = table.send(FETCH, PASS)

        assert answer.status_code == 401
        assert table.record == before

    @pytest.mark.parametrize(
        ("action", "extra"),
        [
            pytest.param(BID, {VALUE_FIELD: 18, "seat": 1}, id="names-a-seat"),
            pytest.param(BID, {VALUE_FIELD: 18, "position": "forehand"}, id="names-a-position"),
            pytest.param(HOLD, {VALUE_FIELD: 18}, id="hold-with-a-value"),
            pytest.param(PASS, {VALUE_FIELD: 18}, id="pass-with-a-value"),
            pytest.param(PLAY, {VALUE_FIELD: 18}, id="play-with-a-value"),
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
        first = table.send(table.at[MIDDLEHAND], BID, 18, command_id=SAME_COMMAND, version=version)
        after_first = table.record

        again = table.send(table.at[MIDDLEHAND], BID, 18, command_id=SAME_COMMAND, version=version)

        assert again.status_code == 200
        assert again.json() == first.json()
        assert table.record == after_first

    def test_a_repeated_refusal_answers_the_same_refusal(self, table):
        first = table.refused(table.at[FOREHAND], PASS, None, NOT_YOUR_TURN, command_id=SAME_COMMAND)

        again = table.refused(table.at[FOREHAND], PASS, None, NOT_YOUR_TURN, command_id=SAME_COMMAND)

        assert again.json() == first.json()

    @pytest.mark.parametrize(
        ("step", "version_offset"),
        [
            pytest.param((BID, 20), 0, id="another-value"),
            pytest.param((PASS, None), 0, id="another-action"),
            pytest.param((BID, 18), 1, id="another-version"),
        ],
    )
    def test_the_same_id_with_another_body_is_refused_as_reused(self, table, step, version_offset):
        version = table.record.version
        table.accepted(MIDDLEHAND, BID, 18, command_id=SAME_COMMAND, version=version)
        after_first = table.record

        answer = table.send(table.at[MIDDLEHAND], *step, command_id=SAME_COMMAND, version=version + version_offset)

        assert answer.status_code == 409
        assert "reused" in answer.json()["detail"]
        assert table.record == after_first

    def test_a_fresh_id_with_the_old_version_is_stale(self, table):
        old_version = table.record.version
        table.accepted(MIDDLEHAND, BID, 18)

        table.refused(table.at[FOREHAND], HOLD, None, STALE_VERSION, version=old_version)

    def test_a_retry_with_its_old_version_is_the_replay_not_stale(self, table):
        old_version = table.record.version
        table.accepted(MIDDLEHAND, BID, 18, command_id=SAME_COMMAND, version=old_version)
        after_first = table.record

        again = table.send(table.at[MIDDLEHAND], BID, 18, command_id=SAME_COMMAND, version=old_version)

        assert again.status_code == 200
        assert table.record == after_first


class TestOtherCommandsDuringAnAuction:
    def test_standing_up_while_an_auction_runs_is_refused(self, table):
        table.accepted(MIDDLEHAND, BID, 18)
        before = table.record

        answer = table.skat.stand(table.at[MIDDLEHAND], table.table_id)

        assert reason_of(answer) == "hand-running"
        assert table.record == before

    def test_a_fourth_member_sitting_while_an_auction_runs_is_refused(self, table):
        table.accepted(MIDDLEHAND, BID, 18)
        before = table.record

        answer = table.skat.sit(table.watcher, table.table_id, 2)

        assert reason_of(answer) == "seat-taken"
        assert table.record == before


class TestPassedIn:
    def test_the_third_pass_ends_the_hand_and_says_passed_in_with_the_next_dealer(self, table):
        table.play_out(PASSES[:2])
        version = table.record.version

        answer = table.accepted(*PASSES[2])

        body = answer.json()
        assert body["hand"] is None
        assert body["passed_in"] == {"next_dealer_seat": next_dealer(DEALER_SEAT)}
        assert table.record.hand is None
        assert table.record.version == version + 1
        assert cards_in_text(answer.text) == set()

    def test_a_reload_says_passed_in_with_the_next_dealer(self, table):
        table.play_out(PASSES)

        answer = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}", headers=table.watcher)

        assert answer.json()["passed_in"] == {"next_dealer_seat": next_dealer(DEALER_SEAT)}

    def test_a_table_that_never_dealt_says_no_passed_in(self, skat):
        headers, _ = skat.member()

        assert skat.create(headers).json()["passed_in"] is None

    def test_any_step_after_the_hand_ended_is_refused_as_no_hand(self, table):
        table.play_out(PASSES)

        table.refused(table.at[MIDDLEHAND], BID, 18, Refusal.NO_HAND)

    def test_the_same_third_pass_again_is_the_same_answer_without_a_bump(self, table):
        table.play_out(PASSES[:2])
        version = table.record.version
        first = table.send(table.at[FOREHAND], PASS, command_id=SAME_COMMAND, version=version)
        record = table.record

        again = table.send(table.at[FOREHAND], PASS, command_id=SAME_COMMAND, version=version)

        assert (first.status_code, again.status_code) == (200, 200)
        assert again.json() == first.json()
        assert table.record == record

    def test_standing_up_works_again_and_no_next_dealer_is_named(self, table):
        table.play_out(PASSES)

        answer = table.skat.stand(table.at[FOREHAND], table.table_id)

        assert answer.status_code == 200
        assert answer.json()["passed_in"] == {"next_dealer_seat": None}

    def test_the_sit_that_fills_the_third_chair_deals_for_the_next_dealer_and_clears_the_auction(self, table):
        table.play_out(PASSES)
        seat = next(seat for seat, position in positions_from(DEALER_SEAT).items() if position is FOREHAND)
        table.skat.stand(table.at[FOREHAND], table.table_id)
        version = table.record.version

        answer = table.skat.sit(table.watcher, table.table_id, seat, command_id="command-fills")

        assert answer.status_code == 200
        body = answer.json()
        assert body["passed_in"] is None
        assert body["hand"]["dealer_seat"] == next_dealer(DEALER_SEAT)
        assert table.record.progress.auction == ()
        assert table.record.version == version + 1

    def test_the_new_hand_takes_a_bid_because_its_auction_starts_empty(self, table):
        table.play_out(PASSES)
        seat = next(seat for seat, position in positions_from(DEALER_SEAT).items() if position is FOREHAND)
        table.skat.stand(table.at[FOREHAND], table.table_id)
        table.skat.sit(table.watcher, table.table_id, seat, command_id="command-fills")
        table.seats[seat] = table.watcher
        middle = next(s for s, position in positions_from(table.record.dealer).items() if position is MIDDLEHAND)

        answer = table.send(table.seats[middle], BID, 18)

        assert answer.status_code == 200, answer.text
        assert table.record.progress.auction == (Bid(MIDDLEHAND, 18),)


class TestAuctionOnTheWire:
    def auction_read_by(self, table, headers):
        answer = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}", headers=headers)
        return answer.json()["hand"]["auction"]

    def test_every_viewer_reads_the_auction_of_a_dealt_hand_and_only_the_middlehand_reads_values(self, table):
        middlehand_seat = positions_from(DEALER_SEAT)
        seat_of_middlehand = next(seat for seat, position in middlehand_seat.items() if position is MIDDLEHAND)
        seat_of_forehand = next(seat for seat, position in middlehand_seat.items() if position is FOREHAND)

        auctions = {
            name: self.auction_read_by(table, headers)
            for name, headers in [
                ("forehand", table.at[FOREHAND]),
                ("middlehand", table.at[MIDDLEHAND]),
                ("rearhand", table.at[REARHAND]),
                ("watcher", table.watcher),
            ]
        }

        assert auctions["middlehand"] == {
            "turn_seat": seat_of_middlehand,
            "facing_seat": seat_of_forehand,
            "awaiting": "bid",
            "standing": None,
            "values": list(VALID_BIDS),
            "words": [],
            "declared": None,
        }
        for name in ("forehand", "rearhand", "watcher"):
            assert auctions[name] == {**auctions["middlehand"], "values": []}

    def test_a_played_auction_answers_each_chairs_word_and_who_declared(self, table):
        table.play_out([(MIDDLEHAND, PASS), (REARHAND, PASS), (FOREHAND, PLAY)])
        seats = {position: seat for seat, position in positions_from(DEALER_SEAT).items()}

        auction = self.auction_read_by(table, table.watcher)

        assert auction["turn_seat"] is None
        assert auction["facing_seat"] is None
        assert auction["awaiting"] is None
        assert auction["declared"] == {"seat": seats[FOREHAND], "value": 18}
        assert sorted(auction["words"], key=lambda word: word["seat"]) == sorted(
            [
                {"seat": seats[MIDDLEHAND], "action": "pass", "value": None},
                {"seat": seats[REARHAND], "action": "pass", "value": None},
                {"seat": seats[FOREHAND], "action": "play", "value": 18},
            ],
            key=lambda word: word["seat"],
        )
