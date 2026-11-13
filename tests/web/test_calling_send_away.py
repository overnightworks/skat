"""A member sends a seated agent away from the page: the chair opens; a send-away that changes nothing says why."""

import json
import threading
from contextlib import nullcontext

import pytest
from agents.member import LEASE_SECONDS

from skat.table.records import Actor, SendAway, TableId
from skat.web.calling import CallRefusal
from tests.web.support.agent import Agent
from tests.web.support.calling import (
    CallingTable,
    call,
    invitations_of,
    listening,
    offer_of,
    only_row,
    person,
    read_control,
    refresh_grants,
    seat_of_nobody_but,
    send_away,
)
from tests.web.support.presence import view_of_version
from tests.web.support.skat import streams_of

NOVA = "agent-nova"
BACH = "agent-bach"
UNKNOWN_KEY = "a-key-no-roster-made"


def hand_with_nova_in_chair_two(skat, nova, table_id):
    """Felix in chair 1, a person in chair 3 and Nova in chair 2: a hand is dealt."""
    skat.sit(skat.member()[0], table_id, 3, command_id="command-sit-3")
    skat.client.cookies.clear()
    nova.sit_down(table_id, 2)
    assert skat.store.tables[table_id].hand is not None


def chair_two(skat, table_id):
    return skat.store.tables[table_id].chairs[1].occupant


@pytest.mark.usefixtures("watching")
class TestAMemberSendsASeatedAgentAway(CallingTable):
    def test_between_hands_the_chair_is_free_at_once_and_the_answer_is_the_control_with_the_row_available(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            key = only_row(skat, felix, table_id)["key"]

            answer = send_away(skat, felix, table_id, key)

        assert answer.status_code == 200
        assert chair_two(skat, table_id) is None
        (row,) = answer.json()["rows"]
        assert (row["key"], row["state"], row["ends_in_seconds"]) == (key, "available", None)

    def test_mid_hand_the_chair_opens_and_the_hand_waits(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            hand_with_nova_in_chair_two(skat, nova, table_id)
            hand = skat.store.tables[table_id].hand

            answer = send_away(skat, felix, table_id, only_row(skat, felix, table_id)["key"])

        assert answer.status_code == 200
        assert chair_two(skat, table_id) is None
        assert skat.store.tables[table_id].hand == hand

    def test_every_viewer_of_the_table_is_told_the_chair_is_free(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            key = only_row(skat, felix, table_id)["key"]
            version = skat.store.tables[table_id].version
            with streams_of(skat, table_id, [(felix.headers, None)]) as streams:
                send_away(skat, felix, table_id, key)

                (messages,) = streams
                assert view_of_version(messages, version + 1)["chairs"][1]["occupant_name"] is None

    def test_the_agent_reads_its_standing_without_the_table_and_its_next_tool_call_there_is_refused(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            before = [standing["place"]["id"] for standing in json.loads(nova.standing())["standings"]]

            send_away(skat, felix, table_id, only_row(skat, felix, table_id)["key"])

            after = json.loads(nova.standing())["standings"]
            stand = nova.stand_up(table_id, command_id="agent-stand-after")
        assert (before, after, stand.is_error) == ([table_id], [], True)

    def test_the_agent_can_be_called_again_at_once_and_its_accept_seats_it_in_its_own_open_chair_mid_hand(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            hand_with_nova_in_chair_two(skat, nova, table_id)
            key = only_row(skat, felix, table_id)["key"]
            send_away(skat, felix, table_id, key)

            called = call(skat, felix, table_id, key)
            accepted = nova.accept(table_id, offer_of(nova))

        assert (called.json()["rows"][0]["state"], accepted.is_error) == ("inviting", False)
        assert chair_two(skat, table_id).display_name == "Nova"

    def test_an_invitation_from_before_the_send_away_is_stale(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            call(skat, felix, table_id, key)
            old = offer_of(nova)
            nova.sit_down(table_id, 2)
            send_away(skat, felix, table_id, key)

            accepted = nova.accept(table_id, old)

        assert (accepted.is_error, chair_two(skat, table_id)) == (True, None)

    def test_a_person_who_sits_in_the_open_chair_first_takes_the_seat_and_the_agent_has_no_row(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            send_away(skat, felix, table_id, only_row(skat, felix, table_id)["key"])

            seat_of_nobody_but(skat, table_id, 2)

            assert read_control(skat, felix, table_id).json()["rows"] == []

    def test_a_seated_agent_that_stopped_listening_is_sent_away_mid_hand_from_its_here_row(
        self, skat, issuer, felix, table_id
    ):
        nova = Agent(skat, issuer, NOVA, agent_owner=felix.id, agent_name="Nova")
        hand_with_nova_in_chair_two(skat, nova, table_id)

        row = only_row(skat, felix, table_id)

        answer = send_away(skat, felix, table_id, row["key"])

        assert (row["name"], row["state"], answer.status_code, chair_two(skat, table_id)) == ("Nova", "here", 200, None)

    def test_the_same_tap_retried_for_a_seated_agent_that_does_not_listen_answers_as_the_first_tap_did(
        self, skat, issuer, felix, table_id
    ):
        nova = Agent(skat, issuer, NOVA, agent_owner=felix.id, agent_name="Nova")
        hand_with_nova_in_chair_two(skat, nova, table_id)
        key = only_row(skat, felix, table_id)["key"]

        answers = [send_away(skat, felix, table_id, key, "command-same-tap") for _ in range(2)]

        assert [answer.status_code for answer in answers] == [200, 200]
        assert answers[0].json() == answers[1].json()
        assert chair_two(skat, table_id) is None

    def test_a_member_who_holds_no_chair_sends_away_an_agent_whose_owner_is_not_at_the_table(
        self, skat, issuer, felix, table_id
    ):
        watcher, away = person(skat, issuer), person(skat, issuer)
        with (
            streams_of(skat, table_id, [(watcher.headers, None)]),
            listening(skat, issuer, away, "Nova", NOVA) as nova,
        ):
            nova.sit_down(table_id, 2)
            row = only_row(skat, watcher, table_id)

            answer = send_away(skat, watcher, table_id, row["key"])

        assert (row["state"], answer.status_code, chair_two(skat, table_id)) == ("here", 200, None)


@pytest.mark.usefixtures("watching")
class TestASendAwayThatChangesNothing(CallingTable):
    def test_a_person_outside_the_group_is_refused_not_allowed_and_the_chair_is_kept(
        self, skat, issuer, felix, table_id
    ):
        outsider = person(skat, issuer, groups=())
        with listening(skat, issuer, person(skat, issuer), "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            key = only_row(skat, felix, table_id)["key"]
            with streams_of(skat, table_id, [(outsider.headers, None)]):
                answer = send_away(skat, outsider, table_id, key)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.NOT_ALLOWED})
            assert chair_two(skat, table_id).display_name == "Nova"

    def test_a_member_removed_from_the_group_after_the_display_is_refused_and_then_sees_no_control(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, person(skat, issuer), "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            key = only_row(skat, felix, table_id)["key"]
            issuer.grant_groups(felix.id, ())

            answer = send_away(skat, felix, table_id, key)
            control = read_control(skat, felix, table_id).json()

        assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.NOT_ALLOWED})
        assert (control, chair_two(skat, table_id).display_name) == ({"shown": False, "rows": []}, "Nova")

    @pytest.mark.parametrize(
        "break_the_read",
        [
            pytest.param(lambda issuer: setattr(issuer, "refuses_refresh_grants", True), id="refused"),
            pytest.param(lambda issuer: setattr(issuer, "token_endpoint_is_down", True), id="unavailable"),
        ],
    )
    def test_an_issuer_that_refuses_the_fresh_read_means_try_again_and_keeps_the_chair_and_the_display(
        self, skat, issuer, felix, table_id, break_the_read
    ):
        with listening(skat, issuer, person(skat, issuer), "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            key = only_row(skat, felix, table_id)["key"]
            break_the_read(issuer)

            answer = send_away(skat, felix, table_id, key)
            shown = read_control(skat, felix, table_id).json()["shown"]

        assert (answer.status_code, answer.json(), shown) == (409, {"reason": CallRefusal.TRY_AGAIN}, True)
        assert chair_two(skat, table_id).display_name == "Nova"

    def test_a_person_without_a_stream_is_not_allowed_and_costs_no_grant(self, skat, issuer, felix, table_id):
        absent = person(skat, issuer)
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            key = only_row(skat, felix, table_id)["key"]
            before = refresh_grants(issuer)

            answer = send_away(skat, absent, table_id, key)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.NOT_ALLOWED})
            assert (refresh_grants(issuer), chair_two(skat, table_id).display_name) == (before, "Nova")

    def test_a_key_the_roster_does_not_know_is_agent_unavailable(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)

            answer = send_away(skat, felix, table_id, UNKNOWN_KEY)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.AGENT_UNAVAILABLE})
            assert chair_two(skat, table_id).display_name == "Nova"

    def test_a_listening_agent_that_is_not_seated_here_is_agent_unavailable_and_nothing_changes(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]

            answer = send_away(skat, felix, table_id, key)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.AGENT_UNAVAILABLE})
            assert (invitations_of(nova), only_row(skat, felix, table_id)["state"]) == ([], "available")
            assert call(skat, felix, table_id, key).status_code == 200
            assert offer_of(nova).epoch == 0

    def test_an_agent_that_holds_no_chair_while_the_table_is_full_is_agent_unavailable_and_writes_nothing(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            seat_of_nobody_but(skat, table_id, 2)
            before = skat.store.tables[table_id].version

            answer = send_away(skat, felix, table_id, key)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.AGENT_UNAVAILABLE})
            assert (skat.store.tables[table_id].version, invitations_of(nova)) == (before, [])

    def test_the_refusal_of_an_agent_that_is_not_seated_leaves_its_command_id_unused(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            refused = send_away(skat, felix, table_id, key, "command-unused")
            nova.sit_down(table_id, 2)

            answer = send_away(skat, felix, table_id, key, "command-unused")

            assert (refused.status_code, answer.status_code, chair_two(skat, table_id)) == (409, 200, None)

    def test_a_refusal_the_service_stored_for_a_lost_race_is_replayed_as_agent_unavailable(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            lost = SendAway("command-lost", table_id, skat.stores.accounts.get(NOVA).id)
            skat.tables.send_away(
                Actor(account_id=felix.id, display_name="Felix"), lost, frozenset({felix.id}), is_member=True
            )
            nova.sit_down(table_id, 2)

            answer = send_away(skat, felix, table_id, key, "command-lost")

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.AGENT_UNAVAILABLE})
            assert chair_two(skat, table_id).display_name == "Nova"

    def test_a_table_that_is_not_live_answers_404(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA):
            key = only_row(skat, felix, table_id)["key"]

            assert send_away(skat, felix, "0" * 32, key).status_code == 404
            assert send_away(skat, felix, "not-a-table", key).status_code == 404

    def test_a_table_that_ends_while_the_fresh_read_waits_answers_404(self, skat, issuer, felix, table_id, time):
        nova = Agent(skat, issuer, NOVA, agent_owner=felix.id, agent_name="Nova")
        nova.sit_down(table_id, 2)
        key = only_row(skat, felix, table_id)["key"]
        hold = issuer.hold("refresh_token")
        answers = []
        caller = threading.Thread(target=lambda: answers.append(send_away(skat, felix, table_id, key)))
        caller.start()
        hold.arrivals.get(timeout=10)
        skat.client.portal.call(time.advance, LEASE_SECONDS + 1)
        assert skat.tables.end_empty_table(TableId(table_id), nullcontext(frozenset()), 60)
        hold.release.set()
        caller.join(timeout=10)

        assert [answer.status_code for answer in answers] == [404]

    def test_a_table_that_ends_between_the_checks_and_the_act_answers_404(
        self, skat, issuer, felix, table_id, time, monkeypatch
    ):
        nova = Agent(skat, issuer, NOVA, agent_owner=felix.id, agent_name="Nova")
        nova.sit_down(table_id, 2)
        key = only_row(skat, felix, table_id)["key"]
        send_away_of_service = skat.tables.send_away

        def ends_the_table_first(actor, command, connected, is_member):
            skat.client.portal.call(time.advance, LEASE_SECONDS + 1)
            assert skat.tables.end_empty_table(TableId(table_id), nullcontext(frozenset()), 60)
            return send_away_of_service(actor, command, connected, is_member)

        monkeypatch.setattr(skat.tables, "send_away", ends_the_table_first)

        assert send_away(skat, felix, table_id, key).status_code == 404

    def test_the_same_tap_retried_sends_away_once_and_answers_alike(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            key = only_row(skat, felix, table_id)["key"]

            answers = [send_away(skat, felix, table_id, key, "command-same-tap") for _ in range(2)]
            call(skat, felix, table_id, key)

            assert [answer.status_code for answer in answers] == [200, 200]
            assert answers[0].json() == answers[1].json()
            assert offer_of(nova).epoch == 1

    def test_a_command_id_used_for_a_send_away_is_try_again_for_an_agent_that_is_not_here(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova, listening(skat, issuer, felix, "Bach", BACH):
            nova.sit_down(table_id, 2)
            rows = {row["name"]: row["key"] for row in read_control(skat, felix, table_id).json()["rows"]}
            send_away(skat, felix, table_id, rows["Nova"], "command-used")

            answer = send_away(skat, felix, table_id, rows["Bach"], "command-used")

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.TRY_AGAIN})

    def test_two_members_sending_the_same_agent_away_free_the_chair_once_and_raise_the_epoch_once(
        self, skat, issuer, felix, table_id
    ):
        other = person(skat, issuer)
        with streams_of(skat, table_id, [(other.headers, None)]), listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            key = only_row(skat, felix, table_id)["key"]

            first = send_away(skat, felix, table_id, key, "command-first")
            second = send_away(skat, other, table_id, key, "command-second")
            call(skat, felix, table_id, key)

            assert (first.status_code, second.status_code, second.json()) == (
                200,
                409,
                {"reason": CallRefusal.AGENT_UNAVAILABLE},
            )
            assert offer_of(nova).epoch == 1

    def test_a_used_command_id_with_another_agent_is_try_again_and_changes_nothing(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova, listening(skat, issuer, felix, "Bach", BACH) as bach:
            nova.sit_down(table_id, 2)
            bach.sit_down(table_id, 3)
            rows = {row["name"]: row["key"] for row in read_control(skat, felix, table_id).json()["rows"]}
            send_away(skat, felix, table_id, rows["Nova"], "command-used")

            answer = send_away(skat, felix, table_id, rows["Bach"], "command-used")

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.TRY_AGAIN})
            assert skat.store.tables[table_id].chairs[2].occupant.display_name == "Bach"
