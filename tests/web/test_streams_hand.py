"""What a stream sends the viewer: the hand, the viewer's own cards, and the snapshots that follow each step."""

import json

import pytest

from skat.engine.deal import next_dealer
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import TABLE_DECLARING_TAKE_SUFFIX
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.payload_cards import CARDS_BY_SEAT, DEALER_SEAT, SKAT_CARDS, cards_in_text, seated_three, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, seed_member
from tests.web.support.skat import FETCH, Skat, unnamed_lines
from tests.web.support.streams import SHORT_HEARTBEAT_SECONDS

BID_VALUE = 18


class TestHandOnTheStream:
    def events(self, table_id):
        return f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}"

    def first_message(self, skat, headers, table_id):
        with skat.client.stream("GET", self.events(table_id), headers=headers) as answer:
            first = next(unnamed_lines(answer.iter_lines()))
            answer.close()
        return first

    @pytest.mark.parametrize(
        ("who", "own"),
        [
            pytest.param(0, CARDS_BY_SEAT[1], id="anna"),
            pytest.param(1, CARDS_BY_SEAT[2], id="ben"),
            pytest.param(2, CARDS_BY_SEAT[3], id="cleo"),
            pytest.param(3, (), id="dora-without-a-chair"),
        ],
    )
    def test_the_first_message_and_the_one_a_watcher_wakes_carry_exactly_the_viewers_own_cards(self, skat, who, own):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table_id), headers=people[who][0]) as answer:
            lines = unnamed_lines(answer.iter_lines())
            first = next(lines)
            next(lines)
            arriving_headers, _ = skat.member()
            skat.client.cookies.clear()
            with skat.client.stream("GET", self.events(table_id), headers=arriving_headers) as arriving:
                arriving_lines = unnamed_lines(arriving.iter_lines())
                next(arriving_lines)
                woken = next(lines)

        assert cards_in_text(first) == wire_cards(own)
        assert cards_in_text(woken) == wire_cards(own)

    def test_one_account_on_two_devices_gets_its_own_cards_on_both(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        anna_headers, anna = people[0]
        laptop_session = seed_member(skat.stores, skat.config, account=anna)
        laptop_headers = {"cookie": cookie_header(laptop_session.set_cookie_headers), **FETCH}

        with (
            skat.client.stream("GET", self.events(table_id), headers=anna_headers) as phone,
            skat.client.stream("GET", self.events(table_id), headers=laptop_headers) as laptop,
        ):
            firsts = [next(unnamed_lines(phone.iter_lines())), next(unnamed_lines(laptop.iter_lines()))]

        assert [cards_in_text(first) for first in firsts] == [wire_cards(CARDS_BY_SEAT[1])] * 2

    def test_an_accepted_step_sends_each_open_stream_a_fresh_snapshot_with_the_new_version_and_only_its_own_cards(
        self, skat
    ):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        middlehand_headers, rearhand_headers = people[0][0], people[1][0]

        with skat.client.stream("GET", self.events(table_id), headers=middlehand_headers) as first_stream:
            first_lines = unnamed_lines(first_stream.iter_lines())
            opened = json.loads(next(first_lines).removeprefix("data: "))
            next(first_lines)
            with skat.client.stream("GET", self.events(table_id), headers=rearhand_headers) as second_stream:
                second_lines = unnamed_lines(second_stream.iter_lines())
                next(second_lines)
                next(second_lines)
                # The second stream joining is a change the first stream hears about before the step.
                next(first_lines)
                next(first_lines)
                skat.client.cookies.clear()
                answer = skat.client.post(
                    f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_BID_SUFFIX}",
                    json={"command_id": "step-0001", "version": opened["version"], "value": BID_VALUE},
                    headers={"origin": TEST_PUBLIC_ORIGIN, **middlehand_headers},
                )
                first_fresh, second_fresh = next(first_lines), next(second_lines)

        assert answer.status_code == 200
        fresh = json.loads(first_fresh.removeprefix("data: "))
        assert fresh["version"] == opened["version"] + 1
        assert set(fresh) == {
            "id",
            "version",
            "chairs",
            "watchers",
            "hand",
            "passed_in",
            "aborted",
            "result",
            "series",
            "options",
            "style",
            "bock",
            "ended",
            "opened_by_me",
            "reactions",
        }
        assert json.loads(second_fresh.removeprefix("data: "))["version"] == opened["version"] + 1
        assert cards_in_text(first_fresh) == wire_cards(CARDS_BY_SEAT[1])
        assert cards_in_text(second_fresh) == wire_cards(CARDS_BY_SEAT[2])
        for message in (first_fresh, second_fresh):
            auction = json.loads(message.removeprefix("data: "))["hand"]["auction"]
            assert auction["standing"] == BID_VALUE
            assert auction["awaiting"] == "answer"
            assert [word["value"] for word in auction["words"]] == [BID_VALUE]

    def test_a_stream_opened_mid_auction_starts_from_the_full_auction(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        middlehand_headers, rearhand_headers = people[0][0], people[1][0]
        version = json.loads(self.first_message(skat, middlehand_headers, table_id).removeprefix("data: "))["version"]
        skat.client.cookies.clear()
        skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_BID_SUFFIX}",
            json={"command_id": "step-0001", "version": version, "value": BID_VALUE},
            headers={"origin": TEST_PUBLIC_ORIGIN, **middlehand_headers},
        )
        skat.client.cookies.clear()

        opened = json.loads(self.first_message(skat, rearhand_headers, table_id).removeprefix("data: "))

        assert opened["hand"]["auction"]["standing"] == BID_VALUE
        assert [word["action"] for word in opened["hand"]["auction"]["words"]] == ["bid"]

    def test_the_third_pass_sends_every_stream_a_fresh_snapshot_that_says_passed_in_and_names_no_card(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        middlehand, rearhand, forehand, watcher = (person[0] for person in people)

        with skat.client.stream("GET", self.events(table_id), headers=watcher) as stream:
            lines = unnamed_lines(stream.iter_lines())
            messages = (line for line in lines if line.startswith("data: "))
            opened = json.loads(next(messages).removeprefix("data: "))
            skat.client.cookies.clear()
            for offset, headers in enumerate((middlehand, rearhand, forehand)):
                answer = skat.client.post(
                    f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_PASS_SUFFIX}",
                    json={"command_id": f"step-{offset:04d}", "version": opened["version"] + offset},
                    headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
                )
                assert answer.status_code == 200, answer.text
            final = next(
                line for line in messages if json.loads(line.removeprefix("data: "))["version"] == opened["version"] + 3
            )

        payload = json.loads(final.removeprefix("data: "))
        assert payload["hand"] is None
        assert payload["passed_in"] == {"next_dealer_seat": next_dealer(DEALER_SEAT)}
        assert cards_in_text(final) == set()

    def test_a_stream_opened_after_the_hand_ended_says_passed_in_and_names_no_card(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        for offset, (headers, _) in enumerate(people[:3]):
            record = skat.store.tables[table_id]
            skat.client.post(
                f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_PASS_SUFFIX}",
                json={"command_id": f"step-{offset:04d}", "version": record.version},
                headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
            )
        skat.client.cookies.clear()

        first = self.first_message(skat, people[0][0], table_id)

        assert json.loads(first.removeprefix("data: "))["passed_in"] == {"next_dealer_seat": next_dealer(DEALER_SEAT)}
        assert cards_in_text(first) == set()

    def test_an_accepted_declaring_step_sends_the_declarer_a_fresh_snapshot_with_the_twelve_cards(self, skat):
        table_id, people = seated_three(skat)
        declarer_headers, rearhand_headers, forehand_headers = people[0][0], people[1][0], people[2][0]
        for command_id, headers, suffix, fields in [
            ("auction-1", declarer_headers, TABLE_AUCTION_BID_SUFFIX, {"value": 18}),
            ("auction-2", forehand_headers, TABLE_AUCTION_PASS_SUFFIX, {}),
            ("auction-3", rearhand_headers, TABLE_AUCTION_PASS_SUFFIX, {}),
        ]:
            version = skat.store.tables[table_id].version
            bid = skat.client.post(
                f"{TABLES_PATH}/{table_id}{suffix}",
                json={"command_id": command_id, "version": version, **fields},
                headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
            )
            assert bid.status_code == 200, bid.text
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table_id), headers=declarer_headers) as stream:
            lines = unnamed_lines(stream.iter_lines())
            opened = json.loads(next(lines).removeprefix("data: "))
            next(lines)
            skat.client.cookies.clear()
            answer = skat.client.post(
                f"{TABLES_PATH}/{table_id}{TABLE_DECLARING_TAKE_SUFFIX}",
                json={"command_id": "step-0001", "version": opened["version"]},
                headers={"origin": TEST_PUBLIC_ORIGIN, **declarer_headers},
            )
            fresh_line = next(lines)

        assert answer.status_code == 200
        fresh = json.loads(fresh_line.removeprefix("data: "))
        assert fresh["version"] == opened["version"] + 1
        assert set(fresh) == set(opened)
        assert cards_in_text(fresh_line) == wire_cards((*CARDS_BY_SEAT[1], *SKAT_CARDS))
        assert fresh["hand"]["skat_count"] == 0

    def test_a_stream_opened_after_the_last_one_dropped_starts_from_the_full_current_hand(self, skat):
        table_id, people = seated_three(skat)
        skat.client.cookies.clear()
        anna_headers, _ = people[0]
        self.first_message(skat, anna_headers, table_id)

        again = self.first_message(skat, anna_headers, table_id)

        assert cards_in_text(again) == wire_cards(CARDS_BY_SEAT[1])

    def test_a_revoked_session_gets_no_card_after_the_revocation_and_a_401_on_its_next_read(self, sign_in_settings):
        skat = Skat(sign_in_settings, heartbeat_seconds=SHORT_HEARTBEAT_SECONDS)
        table_id, people = seated_three(skat)
        anna_headers, anna = people[0]
        skat.client.cookies.clear()

        with skat.client.stream("GET", self.events(table_id), headers=anna_headers) as answer:
            lines = unnamed_lines(answer.iter_lines())
            first = next(lines)
            skat.stores.sessions.delete_for_user(anna.id)
            rest = list(lines)
        next_read = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=anna_headers)

        assert cards_in_text(first) == wire_cards(CARDS_BY_SEAT[1])
        assert rest == [""]
        assert next_read.status_code == 401
        assert cards_in_text(next_read.text) == set()
