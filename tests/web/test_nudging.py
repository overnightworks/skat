"""A seated player nudges the seat the table has waited for for a minute: the state on every answer, the command, its
refusals and its cap. A nudge changes nothing stored and moves no version.
"""

import pytest

from skat.table.asking import ASK_AGAIN_AFTER
from skat.table.nudging import NUDGES_PER_VERSION
from skat.table.records import EndedTable, EndReason, TableId
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX
from skat.web.nudging import TABLE_NUDGE_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.open_chairs import sent_away
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import FOREHAND, MIDDLEHAND, REARHAND, Table
from tests.web.support.skat import UNKNOWN_ID, stored, streams_of

# Seats 1, 2 and 3 hold middlehand, rearhand and forehand; the middlehand is on turn.
ON_TURN, SECOND, THIRD = 1, 2, 3


class Seated:
    """The known hand at a table of three people and a watcher; `streams` holds one open stream of each when the
    test opened them, and no chair is away while they are open.
    """

    def __init__(self, skat, time, table, streams=None):
        self.skat = skat
        self.time = time
        self.table = table
        self.streams = streams
        self.headers = {"anna": table.at[MIDDLEHAND], "ben": table.at[REARHAND], "cleo": table.at[FOREHAND]}
        self.headers["watcher"] = table.watcher

    @property
    def version(self):
        return self.table.record.version

    def read(self, who):
        answer = self.table.read_as(self.headers[who])
        assert answer.status_code == 200, answer.text
        return answer.json()

    def nudge(self, who, seat=ON_TURN, *, version=None, nudges=0, headers=None):
        self.skat.client.cookies.clear()
        return self.skat.client.post(
            f"{TABLES_PATH}/{self.table.table_id}{TABLE_NUDGE_SUFFIX}",
            json={"version": self.version if version is None else version, "seat": seat, "nudges": nudges},
            headers={"origin": TEST_PUBLIC_ORIGIN, **(headers or self.headers[who])},
        )

    def nudged(self, who, seat=ON_TURN, **body):
        answer = self.nudge(who, seat, **body)
        assert answer.status_code == 200, answer.text
        return answer.json()

    def wait(self, seconds):
        self.skat.client.portal.call(self.time.advance, seconds)


@pytest.fixture
def seated(server, time):
    table = Table(server)
    people = [(table.at[position], None) for position in (MIDDLEHAND, REARHAND, FOREHAND)]
    with streams_of(server, table.table_id, [*people, (table.watcher, None)]) as streams:
        yield Seated(server, time, table, dict(zip(("anna", "ben", "cleo", "watcher"), streams, strict=True)))


def nudge_of(answer, seat=ON_TURN):
    return answer["chairs"][seat - 1]["nudge"]


def offered(**changes):
    return {"nudges": 0, "may_nudge": True, "by_name": None, **changes}


class TestBeforeAndAfterTheMinute:
    def test_a_seated_viewer_sees_the_chair_open_to_a_nudge_and_the_awaited_seat_and_a_watcher_see_nothing(
        self, seated
    ):
        seen = {who: nudge_of(seated.read(who)) for who in ("anna", "ben", "cleo", "watcher")}

        assert seen == {"anna": None, "ben": offered(), "cleo": offered(), "watcher": None}

    def test_the_minute_passing_changes_no_byte_of_any_answer(self, seated):
        before = {who: seated.table.read_as(seated.headers[who]).text for who in seated.headers}

        seated.wait(10 * ASK_AGAIN_AFTER)

        assert {who: seated.table.read_as(seated.headers[who]).text for who in seated.headers} == before

    def test_the_chairs_the_table_does_not_wait_for_carry_none(self, seated):
        assert [nudge_of(seated.read("ben"), seat) for seat in (SECOND, THIRD)] == [None, None]


class TestANudge:
    def test_is_refused_before_the_table_has_waited_the_minute_and_changes_nothing(self, seated):
        seated.wait(ASK_AGAIN_AFTER - 1)
        before = stored(seated.skat)

        answer = seated.nudge("ben")

        assert (answer.status_code, answer.json()["reason"]) == (409, "too-early")
        assert stored(seated.skat) == before

    def test_after_the_minute_raises_the_nudges_for_everyone_and_names_the_nudger_to_the_nudged_seat(self, seated):
        seated.wait(ASK_AGAIN_AFTER)
        before = stored(seated.skat)
        version = seated.version

        answer = seated.nudged("ben")

        ben_name = seated.read("ben")["chairs"][SECOND - 1]["occupant_name"]
        assert nudge_of(answer) == offered(nudges=1)
        assert {who: nudge_of(seated.read(who)) for who in ("anna", "cleo", "watcher")} == {
            "anna": {"nudges": 1, "may_nudge": False, "by_name": ben_name},
            "cleo": offered(nudges=1),
            "watcher": {"nudges": 1, "may_nudge": False, "by_name": None},
        }
        assert (seated.version, stored(seated.skat)) == (version, before)

    def test_reaches_the_open_streams_of_every_viewer(self, seated):
        seated.wait(ASK_AGAIN_AFTER)

        seated.nudged("ben")

        def reaching(stream):
            return next(message for message in stream if (nudge_of(message) or {}).get("nudges") == 1)

        assert [nudge_of(reaching(seated.streams[who]))["nudges"] for who in ("anna", "cleo", "watcher")] == [1] * 3

    def test_every_answer_path_carries_the_same_state_for_one_viewer(self, seated):
        seated.wait(ASK_AGAIN_AFTER)

        nudged = seated.nudged("ben")
        read = seated.read("ben")
        streamed = next(message for message in seated.streams["ben"] if nudge_of(message)["nudges"] == 1)

        assert [nudge_of(answer) for answer in (nudged, read, streamed)] == [offered(nudges=1)] * 3

    def test_sent_again_with_the_count_it_saw_is_answered_as_the_first_time(self, seated):
        seated.wait(ASK_AGAIN_AFTER)
        first = seated.nudged("ben")

        assert seated.nudged("ben") == first
        assert nudge_of(seated.read("cleo")) == offered(nudges=1)

    def test_a_count_the_seat_never_had_is_refused_each_time_and_spends_no_nudge(self, seated):
        seated.wait(ASK_AGAIN_AFTER)
        first = seated.nudge("ben", nudges=1)
        seated.wait(ASK_AGAIN_AFTER)
        again = seated.nudge("ben", nudges=1)

        assert [(answer.status_code, answer.json()["reason"]) for answer in (first, again)] == [
            (409, "already-nudged")
        ] * 2
        assert nudge_of(seated.read("cleo")) == offered()

    def test_each_of_both_nudges_sent_again_after_the_second_was_made_is_accepted_and_spends_no_third(self, seated):
        seated.wait(ASK_AGAIN_AFTER)
        seated.nudged("ben")
        seated.wait(ASK_AGAIN_AFTER)
        seated.nudged("cleo", nudges=1)

        again = [seated.nudged("ben"), seated.nudged("cleo", nudges=1)]

        assert [nudge_of(answer) for answer in again] == [offered(nudges=NUDGES_PER_VERSION, may_nudge=False)] * 2

    def test_a_second_one_is_offered_a_minute_after_the_first_and_no_third_ever(self, seated):
        seated.wait(ASK_AGAIN_AFTER)
        seated.nudged("ben")

        early = seated.nudge("cleo", nudges=1)
        seated.wait(ASK_AGAIN_AFTER)
        second = seated.nudged("cleo", nudges=1)
        third = seated.nudge("ben", nudges=NUDGES_PER_VERSION)

        assert [(early.status_code, early.json()["reason"]), (third.status_code, third.json()["reason"])] == [
            (409, "already-nudged"),
            (409, "already-nudged"),
        ]
        assert nudge_of(second) == offered(nudges=2, may_nudge=False)
        assert {who: nudge_of(seated.read(who))["may_nudge"] for who in ("ben", "cleo")} == {
            "ben": False,
            "cleo": False,
        }

    def test_is_refused_for_a_watcher_and_for_an_account_not_at_the_table(self, seated):
        seated.wait(ASK_AGAIN_AFTER)
        stranger, _ = seated.skat.member()

        reasons = [seated.nudge("watcher").json()["reason"], seated.nudge("x", headers=stranger).json()["reason"]]

        assert reasons == ["not-seated", "not-seated"]

    @pytest.mark.parametrize(
        ("who", "seat", "reason"),
        [("cleo", SECOND, "not-waiting"), ("cleo", THIRD, "own-seat")],
    )
    def test_is_refused_for_a_seat_the_table_does_not_wait_for_and_for_the_own_seat(self, seated, who, seat, reason):
        seated.wait(ASK_AGAIN_AFTER)
        before = stored(seated.skat)

        answer = seated.nudge(who, seat)

        assert (answer.status_code, answer.json()["reason"]) == (409, reason)
        assert stored(seated.skat) == before

    def test_is_refused_for_an_older_version(self, seated):
        seated.wait(ASK_AGAIN_AFTER)

        answer = seated.nudge("ben", version=seated.version - 1)

        assert (answer.status_code, answer.json()["reason"]) == (409, "stale-version")

    def test_is_refused_while_a_chair_of_the_hand_is_open_and_no_answer_shows_a_state(self, seated):
        seated.skat.store.tables[seated.table.table_id] = sent_away(seated.table.record, THIRD)
        seated.wait(ASK_AGAIN_AFTER)

        answer = seated.nudge("ben")

        assert (answer.status_code, answer.json()["reason"]) == (409, "seat-open")
        assert {nudge_of(seated.read(who)) for who in ("anna", "ben", "watcher")} == {None}

    def test_is_refused_for_a_table_that_ended(self, seated):
        record = seated.table.record
        seated.skat.store.tables[seated.table.table_id] = EndedTable(
            TableId(seated.table.table_id), record.version + 1, EndReason.EMPTY, 3600
        )

        answer = seated.nudge("ben", version=record.version + 1)

        assert (answer.status_code, answer.json()["reason"]) == (409, "stale-version")

    def test_is_refused_for_an_unknown_table_and_a_malformed_body(self, seated):
        unknown = seated.skat.client.post(
            f"{TABLES_PATH}/{UNKNOWN_ID}{TABLE_NUDGE_SUFFIX}",
            json={"version": 1, "seat": 1, "nudges": 0},
            headers={"origin": TEST_PUBLIC_ORIGIN, **seated.headers["ben"]},
        )
        malformed = [seated.nudge("ben", seat=seat).status_code for seat in ("one", 4)]

        assert (unknown.status_code, malformed) == (404, [422, 422])


class TestTheTableMovesOn:
    def test_the_new_version_offers_the_next_awaited_chair_and_starts_the_minute_at_the_committing_answer(self, seated):
        seated.wait(ASK_AGAIN_AFTER)
        seated.nudged("ben")

        seated.table.middlehand_bids()
        moved = seated.read("ben")

        assert [nudge_of(moved, seat) for seat in (ON_TURN, SECOND, THIRD)] == [None, None, offered()]
        assert nudge_of(seated.read("anna"), THIRD) == offered()
        seated.wait(ASK_AGAIN_AFTER - 1)
        assert seated.nudge("ben", THIRD).json()["reason"] == "too-early"
        seated.wait(1)
        assert seated.nudge("ben", THIRD).status_code == 200

    def test_the_answer_to_a_table_opened_again_with_the_same_command_id_carries_the_chairs_nudge(self, seated):
        seated.wait(ASK_AGAIN_AFTER)
        seated.nudged("ben")

        replay = seated.skat.create(seated.headers["anna"])

        ben_name = seated.read("ben")["chairs"][SECOND - 1]["occupant_name"]
        assert replay.status_code == 200, replay.text
        assert nudge_of(replay.json()) == {"nudges": 1, "may_nudge": False, "by_name": ben_name}

    def test_a_commands_answer_carries_the_state_as_a_read_does(self, seated):
        seated.skat.client.cookies.clear()
        bid = seated.skat.client.post(
            f"{TABLES_PATH}/{seated.table.table_id}{TABLE_AUCTION_BID_SUFFIX}",
            json={"command_id": "anna-bid-0001", "version": seated.version, "value": 18},
            headers={"origin": TEST_PUBLIC_ORIGIN, **seated.headers["anna"]},
        )

        assert bid.status_code == 200, bid.text
        assert nudge_of(bid.json(), THIRD) == nudge_of(seated.read("anna"), THIRD) == offered()


class TestAChairThatIsAway:
    def test_is_not_nudged_and_shows_no_state(self, server, time):
        table = Table(server)
        people = [(table.at[position], None) for position in (REARHAND, FOREHAND)]

        with streams_of(server, table.table_id, people):
            seated = Seated(server, time, table)
            seated.wait(ASK_AGAIN_AFTER)

            answer = seated.nudge("ben")

            assert (answer.status_code, answer.json()["reason"]) == (409, "away")
            assert nudge_of(seated.read("ben")) is None
