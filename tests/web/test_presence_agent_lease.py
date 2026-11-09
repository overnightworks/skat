"""An agent's calls at /mcp are its presence: the chair of a seated agent follows its lease, like a person's follows
a stream, and „Weiter“ is a tool.
"""

import pytest
from agent_runtime_client.member import LEASE_SECONDS
from structlog.testing import capture_logs
from webauth.admission import AppRole
from webauth.ports import AccountKind

from skat.engine.deal import Position, seats_from
from skat.table.records import EndedTable, Refusal
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.mcp import AUCTION_PASS_TOOL, CONTINUE_AFTER_RESULT_TOOL, MCP_GROUP
from skat.web.presence import CHAIR_RELEASE_RETRY_SECONDS, NEXT_DEAL_PAUSE_SECONDS
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import SUBJECT, Agent
from tests.web.support.presence import (
    FAILURE_NAMING_AN_ACCOUNT,
    NAMED_FAILURE,
    end_the_first_game,
    occupied_seats,
)
from tests.web.support.skat import FETCH, UNKNOWN_ID, AgentTable, FakeTime, Skat, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
SEAT_OF = seats_from(DEALER_SEAT)
AGENT_SEAT = SEAT_OF[MIDDLEHAND]
FIRST_RESULT = 1
# Often enough that the lease never runs out between two calls.
CALL_EVERY_SECONDS = LEASE_SECONDS // 2
PERSON_SUBJECT = "person-subject"
PERSON_AT_THE_AGENTS_PATH = {"groups": [MCP_GROUP], "agent_owner": None, "agent_name": None}


@pytest.fixture
def skat(hold, issuer, time):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports, chair_clock=time.clock, chair_scheduler=time)
    with skat.client:
        yield skat


@pytest.fixture
def hand_table(skat, agent):
    """A dealt table, no step taken, where the agent holds the middlehand chair."""
    table = AgentTable(skat, agent.admitted(), MIDDLEHAND)
    skat.client.cookies.clear()
    return table


@pytest.fixture
def result_table(skat, hand_table):
    """The table after its first game, no chair ready."""
    end_the_first_game(skat.store, hand_table.table_id)
    return hand_table


@pytest.fixture
def undealt_table(skat, agent):
    """No hand was dealt: a person holds seat 1 and the agent seat 2; returns the person's headers and the table id."""
    agent_headers = agent.admitted()
    account = skat.stores.accounts.create_for_subject(
        PERSON_SUBJECT, "person", role=AppRole.USER, kind=AccountKind.PERSON
    )
    owner, _ = skat.member(account)
    table_id = skat.create(owner).json()["id"]
    skat.sit(agent_headers, table_id, 2)
    skat.client.cookies.clear()
    return owner, table_id


def advance(skat, time, seconds):
    skat.client.portal.call(time.advance, seconds)


def stay_connected(skat, time, agent, seconds, *, table_id=UNKNOWN_ID):
    """Advance by `seconds` with a call of the agent, about `table_id`, in between that renews its lease."""
    elapsed = 0
    while elapsed < seconds:
        step = min(CALL_EVERY_SECONDS, seconds - elapsed)
        advance(skat, time, step)
        agent.read(table_id)
        elapsed += step


def chairs_of(table):
    answer = table.read_as(table.watcher)
    return {chair["seat"]: chair for chair in answer.json()["chairs"]}


def is_away(table, seat):
    return chairs_of(table)[seat]["is_away"]


def persons_streams(table):
    return streams_of(table.skat, table.table_id, [(table.at[position], None) for position in (FOREHAND, REARHAND)])


def mark_ready(table, *positions):
    end_the_first_game(table.skat.store, table.table_id, *(SEAT_OF[position] for position in positions))


def hand_of(table):
    return table.skat.store.tables[table.table_id].hand


def person_passes(table, position):
    answer = table.skat.client.post(
        f"{TABLES_PATH}/{table.table_id}{TABLE_AUCTION_PASS_SUFFIX}",
        json={"command_id": table.fresh_id(), "version": table.record.version},
        headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[position]},
    )
    assert answer.status_code == 200, answer.text
    table.skat.client.cookies.clear()


def pass_the_hand_in(table, agent):
    agent.take_step(AUCTION_PASS_TOOL, table, command_id="agent-pass")
    person_passes(table, REARHAND)
    person_passes(table, FOREHAND)


def person_taps_weiter(table, position, *, ordinal=FIRST_RESULT):
    answer = table.skat.client.post(
        f"{TABLES_PATH}/{table.table_id}{TABLE_READY_SUFFIX}",
        json={"command_id": table.fresh_id(), "ordinal": ordinal},
        headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[position]},
    )
    assert answer.status_code == 200, answer.text
    table.skat.client.cookies.clear()


def continues(agent, table, *, command_id="agent-weiter", ordinal=FIRST_RESULT):
    return agent.call(CONTINUE_AFTER_RESULT_TOOL, table_id=table.table_id, command_id=command_id, ordinal=ordinal)


@pytest.fixture
def hold_seconds(hold):
    return hold.settings.chair_hold_seconds


@pytest.fixture
def empty_seconds(hold):
    return hold.settings.empty_table_seconds


class TestWhileTheLeaseRuns:
    def test_a_seated_agent_that_called_within_the_lease_is_not_away(self, skat, time, result_table):
        advance(skat, time, LEASE_SECONDS - 1)

        assert not is_away(result_table, AGENT_SEAT)

    def test_a_lease_kept_alive_starts_no_hold_and_frees_no_chair(self, skat, time, agent, result_table, hold_seconds):
        stay_connected(skat, time, agent, hold_seconds * 2)

        assert AGENT_SEAT in occupied_seats(skat, result_table.table_id)
        assert not is_away(result_table, AGENT_SEAT)

    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda agent: agent.request("tools/list"), id="a listing of the tools"),
            pytest.param(lambda agent: agent.read(UNKNOWN_ID), id="a tool about another table"),
        ],
    )
    def test_any_admitted_call_renews_the_lease(self, skat, time, agent, result_table, call):
        advance(skat, time, LEASE_SECONDS - 10)
        call(agent)
        advance(skat, time, LEASE_SECONDS - 10)

        assert not is_away(result_table, AGENT_SEAT)

    def test_a_call_the_front_refuses_after_the_gate_admitted_it_renews_too(self, skat, time, agent, result_table):
        advance(skat, time, LEASE_SECONDS - 10)
        refused = agent.request("tools/list", extra_headers={"origin": "https://elsewhere.test.invalid"})
        advance(skat, time, LEASE_SECONDS - 10)

        assert refused.status_code == 403
        assert not is_away(result_table, AGENT_SEAT)

    def test_a_call_made_straight_at_a_marked_route_does_not_renew(self, skat, time, issuer, result_table):
        advance(skat, time, LEASE_SECONDS - 10)
        direct = skat.client.post(
            f"{TABLES_PATH}/{UNKNOWN_ID}{TABLE_READY_SUFFIX}",
            json={"command_id": "agent-direct", "ordinal": FIRST_RESULT},
            headers={"authorization": f"Bearer {issuer.agent_token(SUBJECT)}", **FETCH},
        )
        advance(skat, time, 20)

        assert direct.status_code == 404
        assert is_away(result_table, AGENT_SEAT)

    @pytest.mark.parametrize(
        "token_changes",
        [pytest.param({"aud": "https://elsewhere.test.invalid/mcp"}, id="the audience of another resource")],
    )
    def test_a_refused_token_renews_nothing_and_the_agent_is_away_within_a_lease(
        self, skat, time, agent, result_table, token_changes
    ):
        advance(skat, time, CALL_EVERY_SECONDS)
        refused = agent.request("tools/list", token_changes=token_changes)
        advance(skat, time, CALL_EVERY_SECONDS)
        agent.request("tools/list", token_changes=token_changes)
        advance(skat, time, 1)

        assert refused.status_code == 401
        assert is_away(result_table, AGENT_SEAT)

    def test_the_calls_of_an_agent_never_keep_its_owners_chair_alive(self, skat, time, issuer, undealt_table):
        _, table_id = undealt_table
        agent = Agent(skat, issuer)
        agent.request("tools/list", token_changes={"agent_owner": PERSON_SUBJECT})
        advance(skat, time, CALL_EVERY_SECONDS)
        agent.request("tools/list", token_changes={"agent_owner": PERSON_SUBJECT})

        chairs = agent.read(table_id).json()["chairs"]
        assert {chair["seat"]: chair["is_away"] for chair in chairs}[1] is True

    def test_a_person_s_token_at_the_mcp_path_renews_no_lease_for_the_person(self, skat, time, issuer, undealt_table):
        _, table_id = undealt_table
        person = Agent(skat, issuer, subject=PERSON_SUBJECT)
        advance(skat, time, CALL_EVERY_SECONDS)
        admitted = person.request("tools/list", token_changes=PERSON_AT_THE_AGENTS_PATH)
        advance(skat, time, LEASE_SECONDS - 1)

        chairs = Agent(skat, issuer).read(table_id).json()["chairs"]
        assert admitted.status_code == 200
        assert {chair["seat"]: chair["is_away"] for chair in chairs}[1] is True

    def test_an_agent_token_is_admitted_at_the_ready_route_as_a_marked_route(self, skat, issuer):
        answer = skat.client.post(
            f"{TABLES_PATH}/{UNKNOWN_ID}{TABLE_READY_SUFFIX}",
            json={"command_id": "agent-direct", "ordinal": FIRST_RESULT},
            headers={"authorization": f"Bearer {issuer.agent_token(SUBJECT)}", **FETCH},
        )

        assert answer.status_code == 404


class TestWhenTheLeaseLapses:
    def test_the_streams_are_woken_and_show_the_agent_away(self, skat, time, result_table):
        with streams_of(skat, result_table.table_id, [(result_table.watcher, None)]) as (messages,):
            advance(skat, time, LEASE_SECONDS + 1)

            views = (message for message in messages if message["chairs"][AGENT_SEAT - 1]["is_away"])
            assert next(views)["chairs"][AGENT_SEAT - 1]["is_away"] is True

    def test_between_hands_the_hold_then_frees_the_chair_as_it_does_a_persons(
        self, skat, time, result_table, hold_seconds
    ):
        advance(skat, time, LEASE_SECONDS + hold_seconds - 1)
        before = occupied_seats(skat, result_table.table_id)
        advance(skat, time, 2)

        assert AGENT_SEAT in before
        assert AGENT_SEAT not in occupied_seats(skat, result_table.table_id)

    def test_during_a_hand_nothing_frees_the_chair_and_the_hand_waits(self, skat, time, hand_table, hold_seconds):
        before = hand_table.record
        advance(skat, time, LEASE_SECONDS + hold_seconds * 2)

        assert hand_table.record == before
        assert is_away(hand_table, AGENT_SEAT)

    def test_a_hand_that_ends_after_the_lapse_starts_a_fresh_hold(self, skat, time, agent, hand_table, hold_seconds):
        agent.take_step(AUCTION_PASS_TOOL, hand_table, command_id="agent-pass")
        advance(skat, time, LEASE_SECONDS + hold_seconds + 10)
        person_passes(hand_table, REARHAND)
        person_passes(hand_table, FOREHAND)

        advance(skat, time, hold_seconds - 1)
        before = occupied_seats(skat, hand_table.table_id)
        advance(skat, time, 2)

        assert AGENT_SEAT in before
        assert AGENT_SEAT not in occupied_seats(skat, hand_table.table_id)

    def test_a_return_before_the_hold_ends_clears_the_mark_and_keeps_the_chair(
        self, skat, time, agent, result_table, hold_seconds
    ):
        advance(skat, time, LEASE_SECONDS + 1)
        away = is_away(result_table, AGENT_SEAT)
        advance(skat, time, hold_seconds - 10)
        agent.read(UNKNOWN_ID)

        stay_connected(skat, time, agent, hold_seconds)

        assert away
        assert not is_away(result_table, AGENT_SEAT)
        assert AGENT_SEAT in occupied_seats(skat, result_table.table_id)

    def test_a_return_after_the_hold_finds_no_chair_and_reads_a_watchers_view(
        self, skat, time, agent, result_table, hold_seconds
    ):
        advance(skat, time, LEASE_SECONDS + hold_seconds + 1)

        view = agent.read(result_table.table_id).json()

        assert not any(chair["is_mine"] for chair in view["chairs"])
        assert view["watchers"] == 0

    def test_a_person_s_stream_that_closes_is_away_and_held_while_the_agent_is_not(
        self, skat, time, agent, result_table, hold_seconds
    ):
        person_seat = SEAT_OF[FOREHAND]
        with streams_of(skat, result_table.table_id, [(result_table.at[FOREHAND], None)]):
            pass
        away = {seat: chair["is_away"] for seat, chair in chairs_of(result_table).items()}

        stay_connected(skat, time, agent, hold_seconds + 1)

        assert (away[person_seat], away[AGENT_SEAT]) == (True, False)
        assert occupied_seats(skat, result_table.table_id) == {1, 2, 3} - {person_seat}


class TestTheNextDeal:
    def test_a_pending_result_waits_for_an_agent_that_is_not_ready(self, skat, time, agent, result_table):
        mark_ready(result_table, FOREHAND, REARHAND)
        with persons_streams(result_table):
            advance(skat, time, NEXT_DEAL_PAUSE_SECONDS * 2)
            view = agent.read(result_table.table_id).json()

        assert hand_of(result_table) is None
        assert view["result"]["ordinal"] == FIRST_RESULT
        assert [chair["ready"] for chair in view["chairs"] if chair["is_mine"]] == [False]

    def test_the_agent_saying_weiter_last_deals_at_once_and_a_retry_changes_nothing_twice(
        self, skat, agent, result_table
    ):
        mark_ready(result_table, FOREHAND, REARHAND)
        with persons_streams(result_table):
            answer = continues(agent, result_table)
            dealt = skat.store.tables[result_table.table_id]
            retried = continues(agent, result_table)

        assert not answer.is_error, answer.text
        assert dealt.hand is not None
        assert not retried.is_error
        assert skat.store.tables[result_table.table_id] == dealt

    @pytest.mark.parametrize(
        ("state", "ordinal", "reason"),
        [
            pytest.param("result", FIRST_RESULT + 1, Refusal.STALE_RESULT, id="a stale ordinal"),
            pytest.param("hand", FIRST_RESULT, Refusal.NO_RESULT, id="no result"),
        ],
    )
    def test_a_refused_weiter_is_a_failed_result_with_its_reason_and_spends_the_command_id(
        self, skat, agent, hand_table, state, ordinal, reason
    ):
        if state == "result":
            end_the_first_game(skat.store, hand_table.table_id)
        before = skat.store.tables[hand_table.table_id]

        refused = continues(agent, hand_table, ordinal=ordinal)
        again = continues(agent, hand_table, ordinal=FIRST_RESULT)

        assert (refused.is_error, refused.json()["reason"]) == (True, reason)
        assert again.is_error
        assert skat.store.tables[hand_table.table_id] == before

    def test_a_weiter_of_an_agent_without_a_chair_is_refused_as_not_seated(self, skat, issuer, result_table):
        stranger = Agent(skat, issuer, subject="another-agent")

        refused = continues(stranger, result_table)

        assert (refused.is_error, refused.json()["reason"]) == (True, Refusal.NOT_SEATED)

    def test_a_command_id_reused_for_another_ordinal_is_refused(self, skat, agent, result_table):
        continues(agent, result_table)
        before = skat.store.tables[result_table.table_id]

        refused = continues(agent, result_table, ordinal=FIRST_RESULT + 1)

        assert refused.is_error
        assert "reused" in refused.text
        assert skat.store.tables[result_table.table_id] == before

    def test_the_last_tap_of_a_person_deals_while_the_agents_lease_runs(self, skat, result_table):
        mark_ready(result_table, MIDDLEHAND, FOREHAND)
        with persons_streams(result_table):
            person_taps_weiter(result_table, REARHAND)

        assert hand_of(result_table) is not None

    def test_a_passed_in_hand_deals_after_its_pause_while_the_lease_runs(self, skat, time, agent, hand_table):
        with persons_streams(hand_table):
            pass_the_hand_in(hand_table, agent)
            advance(skat, time, NEXT_DEAL_PAUSE_SECONDS - 1)
            waiting = hand_of(hand_table)
            advance(skat, time, 1)

        assert waiting is None
        assert hand_of(hand_table) is not None

    def test_a_hand_that_ends_while_the_lease_runs_holds_only_the_chairs_of_those_without_a_stream(
        self, skat, time, agent, hand_table, hold_seconds
    ):
        pass_the_hand_in(hand_table, agent)

        stay_connected(skat, time, agent, hold_seconds + 1)

        assert occupied_seats(skat, hand_table.table_id) == {AGENT_SEAT}

    def test_a_lapsed_agent_gets_the_deal_asked_again_when_it_returns_and_it_comes_once(
        self, skat, time, agent, result_table
    ):
        advance(skat, time, LEASE_SECONDS + 1)
        mark_ready(result_table, MIDDLEHAND, FOREHAND, REARHAND)
        with persons_streams(result_table):
            advance(skat, time, NEXT_DEAL_PAUSE_SECONDS * 2)
            waiting = hand_of(result_table)
            agent.read(UNKNOWN_ID)
            advance(skat, time, NEXT_DEAL_PAUSE_SECONDS - 1)
            pausing = hand_of(result_table)
            advance(skat, time, 1)
            dealt = skat.store.tables[result_table.table_id]
            advance(skat, time, NEXT_DEAL_PAUSE_SECONDS * 3)

        assert (waiting, pausing) == (None, None)
        assert dealt.hand is not None
        assert skat.store.tables[result_table.table_id] == dealt


class TestUndealtTable:
    def test_a_table_with_a_seated_agent_is_not_ended_while_its_lease_runs(
        self, skat, time, agent, undealt_table, empty_seconds
    ):
        _, table_id = undealt_table

        stay_connected(skat, time, agent, empty_seconds + 1)

        assert not isinstance(skat.store.tables[table_id], EndedTable)

    def test_it_ends_one_wait_after_the_lease_lapses(self, skat, time, agent, undealt_table, empty_seconds):
        _, table_id = undealt_table
        stay_connected(skat, time, agent, empty_seconds + 1)

        advance(skat, time, LEASE_SECONDS + empty_seconds - 1)
        waiting = skat.store.tables[table_id]
        advance(skat, time, 2)

        assert not isinstance(waiting, EndedTable)
        assert isinstance(skat.store.tables[table_id], EndedTable)

    def test_an_agent_that_sits_nowhere_does_not_hold_a_table_open(self, skat, time, agent, empty_seconds):
        owner, _ = skat.member()
        table_id = skat.create(owner).json()["id"]
        skat.client.cookies.clear()

        stay_connected(skat, time, agent, empty_seconds + 1, table_id=table_id)

        assert isinstance(skat.store.tables[table_id], EndedTable)

    def test_an_agent_that_calls_only_about_another_table_is_still_present_where_it_sits(
        self, skat, time, agent, result_table
    ):
        owner, _ = skat.member()
        other_id = skat.create(owner).json()["id"]
        skat.client.cookies.clear()

        stay_connected(skat, time, agent, LEASE_SECONDS * 2, table_id=other_id)

        assert not is_away(result_table, AGENT_SEAT)
        assert agent.read(other_id).json()["watchers"] == 0


class TestRestart:
    @pytest.fixture
    def restarted(self, hold, issuer, skat, result_table):
        """The server started again on the same store, its clock at the start."""
        time = FakeTime()
        again = Skat(
            lambda: hold,
            store=skat.store,
            stores=skat.stores,
            issuer_transports=issuer.transports,
            chair_clock=time.clock,
            chair_scheduler=time,
        )
        with again.client:
            yield again, time

    def test_an_agent_calling_within_the_hold_keeps_its_chair_and_deals_at_its_weiter(
        self, restarted, issuer, result_table, hold_seconds
    ):
        again, time = restarted
        mark_ready(result_table, FOREHAND, REARHAND)
        agent = Agent(again, issuer)
        with streams_of(again, result_table.table_id, [(result_table.at[p], None) for p in (FOREHAND, REARHAND)]):
            stay_connected(again, time, agent, hold_seconds + 1)
            kept = occupied_seats(again, result_table.table_id)
            answer = continues(agent, result_table)

        assert AGENT_SEAT in kept
        assert not answer.is_error, answer.text
        assert again.store.tables[result_table.table_id].hand is not None

    def test_an_agent_silent_for_the_hold_loses_its_chair_between_hands(self, restarted, result_table, hold_seconds):
        again, time = restarted
        with streams_of(again, result_table.table_id, [(result_table.at[p], None) for p in (FOREHAND, REARHAND)]):
            advance(again, time, hold_seconds + 1)

        assert AGENT_SEAT not in occupied_seats(again, result_table.table_id)


class TestWhenTheTablesCannotBeRead:
    @staticmethod
    def failing_once(store):
        failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]
        read = store.occupied_chairs

        def occupied_chairs():
            if failures:
                raise failures.pop()
            return read()

        store.occupied_chairs = occupied_chairs

    def test_a_failed_read_at_a_lapse_is_retried_and_loses_neither_the_wake_nor_the_hold(
        self, skat, time, result_table, hold_seconds
    ):
        with streams_of(skat, result_table.table_id, [(result_table.watcher, None)]) as (messages,):
            advance(skat, time, CALL_EVERY_SECONDS)
            self.failing_once(skat.store)
            with capture_logs() as logs:
                advance(skat, time, LEASE_SECONDS - CALL_EVERY_SECONDS + 1)
            advance(skat, time, CHAIR_RELEASE_RETRY_SECONDS)
            woken = next(message for message in messages if message["chairs"][AGENT_SEAT - 1]["is_away"])

            advance(skat, time, hold_seconds)

        assert [(log["log_level"], log["error"]) for log in logs] == [NAMED_FAILURE]
        assert woken["chairs"][AGENT_SEAT - 1]["is_away"] is True
        assert AGENT_SEAT not in occupied_seats(skat, result_table.table_id)

    def test_a_failed_read_at_a_lease_start_is_retried_and_the_deal_still_comes(self, skat, time, agent, result_table):
        advance(skat, time, LEASE_SECONDS + 1)
        mark_ready(result_table, MIDDLEHAND, FOREHAND, REARHAND)
        with persons_streams(result_table):
            self.failing_once(skat.store)
            agent.read(UNKNOWN_ID)
            advance(skat, time, CHAIR_RELEASE_RETRY_SECONDS + NEXT_DEAL_PAUSE_SECONDS - 1)
            waiting = hand_of(result_table)
            advance(skat, time, 1)

        assert waiting is None
        assert hand_of(result_table) is not None

    def test_a_retry_after_the_agent_returned_frees_no_chair(self, skat, time, agent, result_table, hold_seconds):
        advance(skat, time, CALL_EVERY_SECONDS)
        self.failing_once(skat.store)
        advance(skat, time, LEASE_SECONDS - CALL_EVERY_SECONDS + 1)
        agent.read(UNKNOWN_ID)

        stay_connected(skat, time, agent, hold_seconds + CHAIR_RELEASE_RETRY_SECONDS)

        assert AGENT_SEAT in occupied_seats(skat, result_table.table_id)


class TestAStoppedPresence:
    def test_a_lease_renewed_after_the_presence_stopped_counts_for_nothing(self, holding):
        holding.stop()

        holding.renew_lease("agent")

        assert holding.live_leases() == frozenset()
