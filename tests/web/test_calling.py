"""A person at a table calls a listening agent from the page: the control's rows, the call and what it writes."""

import threading
from contextlib import nullcontext
from datetime import datetime, timedelta

import pytest
from agents.member import INVITATION_SECONDS

from skat.table.member_place import ENDED_CALL_KEPT
from skat.table.records import OccupantKind, TableId
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
from tests.web.support.skat import streams_of

NOVA = "agent-nova"
BACH = "agent-bach"
UNKNOWN_KEY = "a-key-no-roster-made"


def agent_standing(skat, issuer, owner, subject=NOVA, name="Nova"):
    return Agent(skat, issuer, subject, agent_owner=owner.id, agent_name=name)


@pytest.mark.usefixtures("watching")
class TestTheControlListsTheAgentsASessionsPersonMayCall(CallingTable):
    def test_a_member_at_the_table_sees_a_row_for_a_listening_agent_whose_owner_is_there(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA):
            answer = read_control(skat, felix, table_id)

        assert answer.status_code == 200
        assert answer.json()["shown"] is True
        (row,) = answer.json()["rows"]
        assert (row["name"], row["state"], row["ends_in_seconds"]) == ("Nova", "available", None)

    def test_the_control_stays_with_no_row_when_no_agent_listens(self, skat, felix, table_id):
        assert read_control(skat, felix, table_id).json() == {"shown": True, "rows": []}

    def test_a_person_outside_the_group_sees_no_control(self, skat, issuer, felix, table_id):
        outsider = person(skat, issuer, groups=())
        with listening(skat, issuer, felix, "Nova", NOVA), streams_of(skat, table_id, [(outsider.headers, None)]):
            answer = read_control(skat, outsider, table_id)

        assert answer.json() == {"shown": False, "rows": []}

    def test_a_person_without_a_stream_on_the_table_sees_no_control_and_costs_no_grant(
        self, skat, issuer, felix, table_id
    ):
        absent = person(skat, issuer)

        with listening(skat, issuer, felix, "Nova", NOVA):
            answer = read_control(skat, absent, table_id)

        assert (answer.json(), refresh_grants(issuer)) == ({"shown": False, "rows": []}, 0)

    def test_an_agent_whose_owner_is_away_is_not_listed(self, skat, issuer, felix, table_id):
        away = person(skat, issuer)

        with listening(skat, issuer, away, "Nova", NOVA):
            answer = read_control(skat, felix, table_id)

        assert answer.json()["rows"] == []

    def test_an_agent_that_calls_tools_without_listening_is_not_listed(self, skat, issuer, felix, table_id):
        Agent(skat, issuer, NOVA, agent_owner=felix.id, agent_name="Nova").listed_resources()

        assert read_control(skat, felix, table_id).json()["rows"] == []

    def test_agents_of_two_owners_are_listed_alike(self, skat, issuer, felix, table_id):
        other = person(skat, issuer)
        with (
            streams_of(skat, table_id, [(other.headers, None)]),
            listening(skat, issuer, felix, "Nova", NOVA),
            listening(skat, issuer, other, "Bach", BACH),
        ):
            rows = read_control(skat, felix, table_id).json()["rows"]

        assert sorted(row["name"] for row in rows) == ["Bach", "Nova"]

    def test_an_agent_seated_at_another_table_is_listed_here(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.open_table()
            rows = read_control(skat, felix, table_id).json()["rows"]

        assert [row["name"] for row in rows] == ["Nova"]

    def test_an_agent_seated_at_the_table_is_a_here_row_with_no_end(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            nova.sit_down(table_id, 2)
            answer = read_control(skat, felix, table_id)

        (row,) = answer.json()["rows"]
        assert (row["name"], row["state"], row["ends_in_seconds"]) == ("Nova", "here", None)

    def test_a_person_outside_the_group_sees_no_row_for_a_seated_agent(self, skat, issuer, felix, table_id):
        outsider = person(skat, issuer, groups=())
        with (
            streams_of(skat, table_id, [(outsider.headers, None)]),
            listening(skat, issuer, felix, "Nova", NOVA) as nova,
        ):
            nova.sit_down(table_id, 2)

            answer = read_control(skat, outsider, table_id)

        assert answer.json() == {"shown": False, "rows": []}

    def test_the_rows_name_no_account_and_keep_their_key_from_state_to_state(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            available = only_row(skat, felix, table_id)
            call(skat, felix, table_id, available["key"])
            inviting = only_row(skat, felix, table_id)
            nova.accept(table_id, offer_of(nova))
            here = only_row(skat, felix, table_id)
            send_away(skat, felix, table_id, here["key"])
            again = only_row(skat, felix, table_id)

        assert (available["key"], available["state"]) == (inviting["key"], "available")
        assert [inviting["state"], here["state"], again["state"]] == ["inviting", "here", "available"]
        assert here["key"] == again["key"] == available["key"]
        assert felix.id not in str(inviting)
        assert NOVA not in available["key"]
        assert set(inviting) == {"key", "name", "state", "outcome", "ends_in_seconds"}
        assert nova.subject not in str(inviting)

    def test_a_table_that_is_not_a_table_answers_404(self, skat, felix):
        assert read_control(skat, felix, "not-a-table").status_code == 404
        assert read_control(skat, felix, "0" * 32).status_code == 404


@pytest.mark.usefixtures("watching")
class TestACallInvitesTheAgent(CallingTable):
    def test_the_agent_sees_an_invitation_that_runs_out_after_the_duration_on_the_services_clock(
        self, skat, issuer, time, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]

            answer = call(skat, felix, table_id, key)

            (invited,) = invitations_of(nova)
        assert answer.status_code == 200
        assert invited["place"]["id"] == table_id
        expires_at = datetime.fromisoformat(invited["invitation"]["expires_at"])
        assert expires_at == time.moment() + timedelta(seconds=INVITATION_SECONDS)

    def test_the_answer_is_the_callers_control_with_the_row_inviting_for_the_rest_of_the_invitation(
        self, skat, issuer, time, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA):
            key = only_row(skat, felix, table_id)["key"]
            answer = call(skat, felix, table_id, key)
            time.now += 20
            later = only_row(skat, felix, table_id)

        (row,) = answer.json()["rows"]
        assert (row["state"], row["ends_in_seconds"]) == ("inviting", INVITATION_SECONDS)
        assert (later["state"], later["ends_in_seconds"]) == ("inviting", INVITATION_SECONDS - 20)

    def test_the_agent_that_accepts_sits_at_the_lowest_free_chair_and_the_row_is_here(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            call(skat, felix, table_id, only_row(skat, felix, table_id)["key"])

            accepted = nova.accept(table_id, offer_of(nova))
            rows = read_control(skat, felix, table_id).json()["rows"]

        assert accepted.is_error is False
        chair = skat.store.tables[table_id].chairs[1].occupant
        assert (chair.display_name, chair.kind) == ("Nova", OccupantKind.AGENT)
        assert [row["state"] for row in rows] == ["here"]

    def test_another_member_at_the_table_sees_the_row_of_the_agent_that_accepted_as_here(
        self, skat, issuer, felix, table_id
    ):
        other = person(skat, issuer)
        with streams_of(skat, table_id, [(other.headers, None)]), listening(skat, issuer, felix, "Nova", NOVA) as nova:
            call(skat, felix, table_id, only_row(skat, felix, table_id)["key"])
            nova.accept(table_id, offer_of(nova))

            assert only_row(skat, other, table_id)["state"] == "here"

    def test_two_agents_of_one_owner_are_called_one_after_the_other_and_both_sit(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova, listening(skat, issuer, felix, "Bach", BACH) as bach:
            for agent, name in ((nova, "Nova"), (bach, "Bach")):
                row = next(row for row in read_control(skat, felix, table_id).json()["rows"] if row["name"] == name)
                call(skat, felix, table_id, row["key"])
                agent.accept(table_id, offer_of(agent))

        occupants = [chair.occupant.display_name for chair in skat.store.tables[table_id].chairs]
        assert occupants[1:] == ["Nova", "Bach"]

    def test_a_repeated_call_writes_one_invitation_and_reads_the_issuer_once(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            before = refresh_grants(issuer)

            answers = [call(skat, felix, table_id, key) for _ in range(3)]

            assert [answer.status_code for answer in answers] == [200] * 3
            assert [row["state"] for answer in answers for row in answer.json()["rows"]] == ["inviting"] * 3
            assert len(invitations_of(nova)) == 1
            assert refresh_grants(issuer) == before + 1

    def test_only_the_caller_sees_the_row_inviting(self, skat, issuer, felix, table_id):
        other = person(skat, issuer)
        with streams_of(skat, table_id, [(other.headers, None)]), listening(skat, issuer, felix, "Nova", NOVA):
            call(skat, felix, table_id, only_row(skat, felix, table_id)["key"])

            others_control = read_control(skat, other, table_id).json()

        assert others_control == {"shown": True, "rows": []}

    def test_an_invitation_that_ran_out_shows_the_caller_the_row_ended_with_no_answer_and_no_refusal(
        self, skat, issuer, time, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA):
            key = only_row(skat, felix, table_id)["key"]
            call(skat, felix, table_id, key)
            time.now += INVITATION_SECONDS

            row = only_row(skat, felix, table_id)

        assert row == {"key": key, "name": "Nova", "state": "ended", "outcome": "no-answer", "ends_in_seconds": None}

    def test_the_outcome_is_gone_once_it_was_kept_long_enough_and_the_row_is_available_again(
        self, skat, issuer, time, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA):
            key = only_row(skat, felix, table_id)["key"]
            call(skat, felix, table_id, key)
            time.now += INVITATION_SECONDS + ENDED_CALL_KEPT.total_seconds()

            row = only_row(skat, felix, table_id)

        assert (row["key"], row["state"], row["outcome"]) == (key, "available", None)

    def test_only_the_caller_sees_that_the_invitation_ran_out(self, skat, issuer, time, felix, table_id):
        other = person(skat, issuer)
        with streams_of(skat, table_id, [(other.headers, None)]), listening(skat, issuer, felix, "Nova", NOVA):
            call(skat, felix, table_id, only_row(skat, felix, table_id)["key"])
            time.now += INVITATION_SECONDS

            row = only_row(skat, other, table_id)

        assert (row["state"], row["outcome"]) == ("available", None)

    def test_an_accept_that_finds_no_free_chair_shows_the_caller_the_row_ended_busy(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            call(skat, felix, table_id, key)
            offer = offer_of(nova)
            seat_of_nobody_but(skat, table_id, 2)

            nova.accept(table_id, offer)
            row = only_row(skat, felix, table_id)

        assert (row["key"], row["state"], row["outcome"]) == (key, "ended", "busy")

    def test_an_accept_that_finds_the_owner_away_shows_the_caller_the_row_ended_owner_absent(
        self, skat, issuer, felix, table_id
    ):
        owner = person(skat, issuer)
        with listening(skat, issuer, owner, "Nova", NOVA) as nova:
            with streams_of(skat, table_id, [(owner.headers, None)]):
                key = only_row(skat, felix, table_id)["key"]
                call(skat, felix, table_id, key)
                offer = offer_of(nova)
            nova.accept(table_id, offer)

            row = only_row(skat, felix, table_id)

        assert (row["key"], row["state"], row["outcome"]) == (key, "ended", "owner-absent")

    def test_a_new_call_after_the_outcome_makes_the_row_inviting_again(self, skat, issuer, time, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA):
            key = only_row(skat, felix, table_id)["key"]
            call(skat, felix, table_id, key)
            time.now += INVITATION_SECONDS

            answer = call(skat, felix, table_id, key)

        (row,) = answer.json()["rows"]
        assert (row["state"], row["outcome"]) == ("inviting", None)


@pytest.mark.usefixtures("watching")
class TestACallThatChangesNothing(CallingTable):
    def test_a_person_outside_the_group_is_refused_not_allowed_when_every_cheap_check_passes(
        self, skat, issuer, felix, table_id
    ):
        outsider = person(skat, issuer, groups=())
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            with streams_of(skat, table_id, [(outsider.headers, None)]):
                answer = call(skat, outsider, table_id, key)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.NOT_ALLOWED})
            assert invitations_of(nova) == []

    def test_a_person_without_a_stream_is_not_allowed_and_costs_no_grant(self, skat, issuer, felix, table_id):
        absent = person(skat, issuer)
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            before = refresh_grants(issuer)

            answer = call(skat, absent, table_id, key)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.NOT_ALLOWED})
            assert (invitations_of(nova), refresh_grants(issuer)) == ([], before)

    @pytest.mark.parametrize(
        ("break_the_read", "name"),
        [
            pytest.param(lambda issuer: setattr(issuer, "refuses_refresh_grants", True), "invalid-grant", id="refused"),
            pytest.param(
                lambda issuer: setattr(issuer, "token_endpoint_is_down", True), "issuer-unavailable", id="unavailable"
            ),
        ],
    )
    def test_an_issuer_that_refuses_the_fresh_read_means_try_again_and_writes_nothing(
        self, skat, issuer, felix, table_id, break_the_read, name
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            break_the_read(issuer)

            answer = call(skat, felix, table_id, key)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.TRY_AGAIN}), name
            assert invitations_of(nova) == []

    def test_a_session_without_a_refresh_token_means_try_again_and_makes_no_grant(self, skat, issuer, felix, table_id):
        no_token = person(skat, issuer, refresh_token=False)
        with (
            listening(skat, issuer, felix, "Nova", NOVA) as nova,
            streams_of(skat, table_id, [(no_token.headers, None)]),
        ):
            key = only_row(skat, felix, table_id)["key"]
            before = refresh_grants(issuer)

            answer = call(skat, no_token, table_id, key)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.TRY_AGAIN})
            assert (invitations_of(nova), refresh_grants(issuer)) == ([], before)

    def test_a_refused_fresh_read_leaves_the_held_display_answer_as_it_is(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA):
            key = only_row(skat, felix, table_id)["key"]
            issuer.refuses_refresh_grants = True
            call(skat, felix, table_id, key)

            shown = read_control(skat, felix, table_id).json()["shown"]

        assert shown is True

    def test_a_member_removed_from_the_group_after_the_display_is_refused_and_then_sees_no_control(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            issuer.grant_groups(felix.id, ())

            answer = call(skat, felix, table_id, key)
            control = read_control(skat, felix, table_id).json()

        assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.NOT_ALLOWED})
        assert (control, invitations_of(nova)) == ({"shown": False, "rows": []}, [])

    def test_a_person_added_to_the_group_after_the_display_sees_the_control_at_the_next_call(
        self, skat, issuer, felix, table_id
    ):
        latecomer = person(skat, issuer, groups=())
        with (
            listening(skat, issuer, felix, "Nova", NOVA) as nova,
            streams_of(skat, table_id, [(latecomer.headers, None)]),
        ):
            key = only_row(skat, felix, table_id)["key"]
            hidden = read_control(skat, latecomer, table_id).json()["shown"]
            issuer.grant_groups(latecomer.id, ("/agent-adders",))

            answer = call(skat, latecomer, table_id, key)

            assert (hidden, answer.status_code) == (False, 200)
            assert len(invitations_of(nova)) == 1

    def test_a_key_the_roster_does_not_know_is_agent_unavailable(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            answer = call(skat, felix, table_id, UNKNOWN_KEY)

            assert (answer.status_code, answer.json()) == (409, {"reason": CallRefusal.AGENT_UNAVAILABLE})
            assert invitations_of(nova) == []

    def test_a_table_that_is_not_live_answers_404(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA):
            key = only_row(skat, felix, table_id)["key"]

            assert call(skat, felix, "0" * 32, key).status_code == 404
            assert call(skat, felix, "not-a-table", key).status_code == 404

    def test_a_table_that_ends_while_the_fresh_read_waits_answers_404_and_writes_nothing(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            hold = issuer.hold("refresh_token")
            answers = []
            caller = threading.Thread(target=lambda: answers.append(call(skat, felix, table_id, key)))
            caller.start()
            hold.arrivals.get(timeout=10)
            assert skat.tables.end_empty_table(TableId(table_id), nullcontext(frozenset()), 60)
            hold.release.set()
            caller.join(timeout=10)

            assert [answer.status_code for answer in answers] == [404]
            assert invitations_of(nova) == []

    @pytest.mark.parametrize(
        ("arrange", "reason"),
        [
            pytest.param("full", CallRefusal.PLACE_FULL, id="no-chair-is-free"),
            pytest.param("seated", CallRefusal.AGENT_UNAVAILABLE, id="the-agent-sits-here-as-a-here-row"),
            pytest.param("invited-by-someone", CallRefusal.AGENT_UNAVAILABLE, id="someone-else-invited-it"),
        ],
    )
    def test_each_cheap_reason_is_answered_without_a_grant_and_writes_nothing(
        self, skat, issuer, felix, table_id, arrange, reason
    ):
        other = person(skat, issuer)
        with streams_of(skat, table_id, [(other.headers, None)]), listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]
            before = refresh_grants(issuer)
            if arrange == "full":
                seat_of_nobody_but(skat, table_id, 2)
            elif arrange == "seated":
                nova.sit_down(table_id, 2)
            else:
                call(skat, other, table_id, key)
                before = refresh_grants(issuer)

            answer = call(skat, felix, table_id, key)

            assert (answer.status_code, answer.json()) == (409, {"reason": reason})
            assert refresh_grants(issuer) == before
            assert len(invitations_of(nova)) == (1 if arrange == "invited-by-someone" else 0)

    def test_an_owner_who_left_the_table_means_owner_absent_without_a_grant(self, skat, issuer, felix, table_id):
        owner = person(skat, issuer)
        with listening(skat, issuer, owner, "Nova", NOVA) as nova:
            with streams_of(skat, table_id, [(owner.headers, None)]):
                key = only_row(skat, felix, table_id)["key"]
            gone = read_control(skat, felix, table_id).json()["rows"]
            before = refresh_grants(issuer)

            answer = call(skat, felix, table_id, key)

            assert (gone, answer.status_code, answer.json()) == ([], 409, {"reason": CallRefusal.OWNER_ABSENT})
            assert (invitations_of(nova), refresh_grants(issuer)) == ([], before)


@pytest.mark.usefixtures("watching")
class TestTwoOverlappingCallsOfOneSession(CallingTable):
    def overlap(self, skat, issuer, felix, table_id, key):
        """Two calls of Felix's session that both stand at the issuer's grant before either is answered."""
        hold = issuer.hold("refresh_token")
        answers = []
        threads = [threading.Thread(target=lambda: answers.append(call(skat, felix, table_id, key))) for _ in range(2)]
        for thread in threads:
            thread.start()
        for _ in threads:
            hold.arrivals.get(timeout=10)
        hold.release.set()
        for thread in threads:
            thread.join(timeout=10)
        return answers

    def test_where_the_issuer_lets_a_refresh_token_be_used_again_both_succeed_and_one_invitation_stands(
        self, skat, issuer, felix, table_id
    ):
        issuer.reuses_refresh_tokens = True
        with listening(skat, issuer, felix, "Nova", NOVA) as nova:
            key = only_row(skat, felix, table_id)["key"]

            answers = self.overlap(skat, issuer, felix, table_id, key)

            assert sorted(answer.status_code for answer in answers) == [200, 200]
            assert len(invitations_of(nova)) == 1

    def test_where_the_issuer_refuses_the_second_use_one_invitation_stands_and_the_next_call_works(
        self, skat, issuer, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA) as nova, listening(skat, issuer, felix, "Bach", BACH) as bach:
            rows = {row["name"]: row["key"] for row in read_control(skat, felix, table_id).json()["rows"]}

            answers = self.overlap(skat, issuer, felix, table_id, rows["Nova"])
            issuer.hold("refresh_token").release.set()
            next_call = call(skat, felix, table_id, rows["Bach"])

            assert sorted(answer.status_code for answer in answers) == [200, 409]
            assert [answer.json() for answer in answers if answer.status_code == 409] == [
                {"reason": CallRefusal.TRY_AGAIN}
            ]
            assert len(invitations_of(nova)) == 1
            assert (next_call.status_code, len(invitations_of(bach))) == (200, 1)


class TestAnAgentTokenReachesNoRoute(CallingTable):
    def test_every_route_refuses_it_and_the_front_lists_no_tool_for_them(self, skat, issuer, felix, table_id):
        agent = Agent(skat, issuer, NOVA, agent_owner=felix.id, agent_name="Nova")
        token = issuer.agent_token(NOVA, agent_owner=felix.id)
        headers = {"authorization": f"Bearer {token}", "origin": "https://skat.test"}

        refused = [
            skat.client.get(f"/api/tables/{table_id}/agents", headers=headers),
            skat.client.post(f"/api/tables/{table_id}/agents/{UNKNOWN_KEY}/call", headers=headers),
            skat.client.post(
                f"/api/tables/{table_id}/agents/{UNKNOWN_KEY}/send-away",
                json={"command_id": "command-send-away"},
                headers=headers,
            ),
        ]
        listed = agent.request("tools/list").json()["result"]["tools"]

        assert [answer.status_code in {401, 403} for answer in refused] == [True, True, True]
        assert not [
            tool for tool in listed if "agents" in tool["name"] or {"call", "away"} & set(tool["name"].split("_"))
        ]
