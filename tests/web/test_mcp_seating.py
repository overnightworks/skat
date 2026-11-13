"""An agent opens a table, sits and stands like a person, and its chair says agent with the name its token carries."""

import copy

import pytest

from skat.engine.deal import Position, seats_from
from skat.table.records import Refusal
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.mcp import READ_SERIES_LIST_TOOL, THROW_DOWN_CARDS_TOOL
from skat.web.tables import TABLE_SIT_SUFFIX, TABLE_STAND_SUFFIX, TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import Agent
from tests.web.support.presence import end_the_first_game
from tests.web.support.skat import FETCH, UNKNOWN_ID, AgentTable, Skat, stored, streams_of

OWNER = "the-agents-owner"


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


def read_as(skat, headers, table_id):
    answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers)
    skat.client.cookies.clear()
    assert answer.status_code == 200, answer.text
    return answer.json()


def chairs_of(view):
    return [(chair["occupant_name"], chair["occupant_kind"]) for chair in view["chairs"]]


def with_the_agent(messages):
    """The first message of a stream that shows an agent in the third chair; others only count the watchers."""
    return next(message for message in messages if message["chairs"][2]["occupant_kind"] == "agent")


def person_opens(skat):
    """A member who opens a table; returns their headers, their account and the table's id."""
    headers, account = skat.member()
    return headers, account, skat.create(headers).json()["id"]


def person_sits(skat, headers, table_id, seat, command_id="command-sit"):
    answer = skat.sit(headers, table_id, seat, command_id=command_id)
    skat.client.cookies.clear()
    return answer


class TestOpenTable:
    def test_the_agent_sits_in_chair_one_as_an_agent_and_the_other_chairs_are_free(self, agent):
        answer = agent.open_table()

        view = answer.json()
        assert not answer.is_error, answer.text
        assert chairs_of(view) == [("Mozart", "agent"), (None, None), (None, None)]
        assert [chair["is_mine"] for chair in view["chairs"]] == [True, False, False]

    def test_a_person_who_reads_the_answers_id_sits_in_a_free_chair_as_a_person(self, skat, agent):
        table_id = agent.open_table().json()["id"]
        headers, account = skat.member()

        sat = person_sits(skat, headers, table_id, 2)

        assert sat.status_code == 200, sat.text
        assert chairs_of(sat.json()) == [("Mozart", "agent"), (account.username, "person"), (None, None)]

    def test_the_series_length_and_the_running_points_are_as_chosen(self, agent):
        answer = agent.open_table(series_length=12, options={"show_running_points": True})

        view = answer.json()
        assert (view["series"]["game_count"], view["options"]["show_running_points"]) == (12, True)

    def test_the_same_id_with_the_same_request_opens_no_second_table_and_with_another_request_is_refused(
        self, skat, agent
    ):
        first = agent.open_table(series_length=12)
        tables_before = len(skat.store.tables)

        again = agent.open_table(series_length=12)
        other = agent.open_table(series_length=15)

        assert again.json() == first.json()
        assert len(skat.store.tables) == tables_before
        assert other.is_error

    def test_a_refused_opening_is_a_failed_result_and_opens_nothing(self, skat, agent):
        agent.admitted()
        before = stored(skat)

        refused = agent.open_table(series_length=4)

        assert refused.is_error
        assert stored(skat)[0] == before[0]


class TestSitDown:
    def test_an_agent_takes_a_free_chair_of_a_persons_table_without_its_owner_at_the_table(self, skat, agent):
        agent.admitted()
        _, owner, table_id = person_opens(skat)

        answer = agent.sit_down(table_id, 3)

        assert not answer.is_error, answer.text
        assert chairs_of(answer.json()) == [(owner.username, "person"), (None, None), ("Mozart", "agent")]

    def test_an_agent_sits_while_people_watch(self, skat, agent):
        agent.admitted()
        headers, owner, table_id = person_opens(skat)

        with streams_of(skat, table_id, [(headers, None)]) as (opener_messages,):
            answer = agent.sit_down(table_id, 2)
            seen = next(opener_messages)

        assert not answer.is_error, answer.text
        assert chairs_of(seen) == [(owner.username, "person"), ("Mozart", "agent"), (None, None)]

    def test_an_agent_on_a_taken_chair_is_refused_with_who_holds_it(self, skat, agent):
        agent.admitted()
        _, owner, table_id = person_opens(skat)

        refused = agent.sit_down(table_id, 1)

        assert refused.is_error
        assert refused.json() == {"reason": Refusal.SEAT_TAKEN, "holder_name": owner.username}

    def test_a_person_on_the_agents_chair_is_refused_with_the_agents_name(self, skat, agent):
        table_id = agent.open_table().json()["id"]
        headers, _ = skat.member()

        refused = person_sits(skat, headers, table_id, 1)

        assert refused.status_code == 409
        assert refused.json() == {"reason": Refusal.SEAT_TAKEN, "holder_name": "Mozart"}

    def test_an_agent_that_already_sits_at_the_table_is_refused_a_second_chair(self, skat, agent):
        agent.admitted()
        _, _, table_id = person_opens(skat)
        agent.sit_down(table_id, 2)

        refused = agent.sit_down(table_id, 3, command_id="agent-sit-0002")

        assert refused.is_error
        assert refused.json()["reason"] == Refusal.ALREADY_SEATED

    def test_the_agent_that_fills_the_third_chair_deals_the_first_hand(self, skat, agent):
        agent.admitted()
        _, _, table_id = person_opens(skat)
        guest, _ = skat.member()
        person_sits(skat, guest, table_id, 2)

        answer = agent.sit_down(table_id, 3)

        assert answer.json()["hand"] is not None

    def test_an_agent_that_sits_while_a_result_stands_counts_as_ready(self, skat, agent):
        table = AgentTable(skat, agent, Position.MIDDLEHAND)
        end_the_first_game(skat.store, table.table_id)
        seat = seats_from(DEALER_SEAT)[Position.MIDDLEHAND]
        assert not agent.stand_up(table.table_id).is_error

        answer = agent.sit_down(table.table_id, seat, command_id="agent-sit-0002")

        agent_chair = next(chair for chair in answer.json()["chairs"] if chair["seat"] == seat)
        assert agent_chair["ready"] is True

    def test_the_token_name_is_the_chairs_name_and_not_the_accounts_username(self, skat, issuer):
        nova = Agent(skat, issuer, "nova-subject", agent_name="Nova")
        nova.admitted()
        _, _, table_id = person_opens(skat)

        answer = nova.sit_down(table_id, 2)

        assert chairs_of(answer.json())[1] == ("Nova", "agent")

    def test_the_chair_keeps_the_name_the_agent_sat_with_until_it_stands_up(self, skat, agent):
        agent.admitted()
        owner, _, table_id = person_opens(skat)
        agent.sit_down(table_id, 2)
        agent.claims["agent_name"] = "Nova"
        skat.stand(owner, table_id)
        skat.client.cookies.clear()

        kept = chairs_of(agent.read(table_id).json())[1]
        agent.stand_up(table_id)
        agent.sit_down(table_id, 2, command_id="agent-sit-0002")
        renamed = chairs_of(agent.read(table_id).json())[1]

        assert (kept, renamed) == (("Mozart", "agent"), ("Nova", "agent"))

    def test_a_retry_with_the_same_id_and_seat_changes_nothing_twice_and_another_seat_is_refused(self, skat, agent):
        agent.admitted()
        _, _, table_id = person_opens(skat)
        first = agent.sit_down(table_id, 2)
        before = stored(skat)

        again = agent.sit_down(table_id, 2)
        other = agent.sit_down(table_id, 3)

        assert again.json() == first.json()
        assert other.is_error
        assert stored(skat)[0] == before[0]

    def test_a_refused_sit_leaves_the_table_as_it_was_and_spends_the_id(self, skat, agent):
        agent.admitted()
        _, _, table_id = person_opens(skat)
        before = stored(skat)

        refused = agent.sit_down(table_id, 1)
        retried = agent.sit_down(table_id, 3)

        assert refused.is_error
        assert retried.is_error
        assert stored(skat)[0] == before[0]

    def test_a_table_that_does_not_exist_is_a_failed_result(self, agent):
        assert agent.sit_down(UNKNOWN_ID, 1).is_error


class TestStandUp:
    def test_an_agent_between_hands_frees_its_chair_and_the_number_stays(self, skat, agent):
        agent.admitted()
        _, _, table_id = person_opens(skat)
        agent.sit_down(table_id, 2)

        answer = agent.stand_up(table_id)

        assert not answer.is_error, answer.text
        assert [(chair["seat"], chair["occupant_kind"]) for chair in answer.json()["chairs"]] == [
            (1, "person"),
            (2, None),
            (3, None),
        ]

    def test_an_agent_stands_up_during_a_hand_and_the_chair_opens_with_the_hand_waiting_and_no_book_row(
        self, skat, agent
    ):
        table = AgentTable(skat, agent, Position.MIDDLEHAND)
        seat = seats_from(DEALER_SEAT)[Position.MIDDLEHAND]
        before = skat.store.tables[table.table_id]
        book = copy.deepcopy(skat.store.book)

        answer = agent.stand_up(table.table_id)

        after = skat.store.tables[table.table_id]
        assert not answer.is_error, answer.text
        assert answer.json()["hand"]["waiting_seat"] == seat
        assert (after.hand, after.progress.auction, after.chairs[seat - 1].occupant) == (
            before.hand,
            before.progress.auction,
            None,
        )
        assert skat.store.book == book

    def test_the_answer_of_a_stand_up_during_a_hand_names_the_former_holder_of_the_open_chair(self, skat, agent):
        table = AgentTable(skat, agent, Position.MIDDLEHAND)
        seat = seats_from(DEALER_SEAT)[Position.MIDDLEHAND]
        name = skat.store.tables[table.table_id].chairs[seat - 1].occupant.display_name

        answer = agent.stand_up(table.table_id)
        read = agent.read(table.table_id).json()

        names = [chair["former_holder_name"] for chair in read["chairs"]]
        assert [chair["former_holder_name"] for chair in answer.json()["chairs"]] == names
        assert names == [name if number == seat else None for number in (1, 2, 3)]

    def test_the_answer_and_the_read_of_an_agent_that_stood_up_during_a_hand_name_its_own_open_chair_to_return_to(
        self, skat, agent
    ):
        table = AgentTable(skat, agent, Position.MIDDLEHAND)
        seat = seats_from(DEALER_SEAT)[Position.MIDDLEHAND]
        expected = [number == seat for number in (1, 2, 3)]

        answer = agent.stand_up(table.table_id)
        read = agent.read(table.table_id).json()
        other = read_as(skat, table.at[Position.FOREHAND], table.table_id)

        assert [chair["is_mine_to_return"] for chair in answer.json()["chairs"]] == expected
        assert [chair["is_mine_to_return"] for chair in read["chairs"]] == expected
        assert not any(chair["is_mine_to_return"] for chair in other["chairs"])

    def test_an_agent_that_stood_up_during_a_hand_may_sit_only_in_its_own_chair_again(self, skat, agent):
        table = AgentTable(skat, agent, Position.MIDDLEHAND)
        seat = seats_from(DEALER_SEAT)[Position.MIDDLEHAND]
        other = seats_from(DEALER_SEAT)[Position.FOREHAND]
        agent.stand_up(table.table_id)
        skat.stand(table.at[Position.FOREHAND], table.table_id)
        before = stored(skat)

        refused = agent.sit_down(table.table_id, other, command_id="agent-sit-other")
        unchanged = stored(skat)
        own = agent.sit_down(table.table_id, seat, command_id="agent-sit-own")

        assert (refused.is_error, refused.json()["reason"]) == (True, Refusal.OWN_SEAT_ONLY)
        assert unchanged[0] == before[0]
        assert not own.is_error, own.text

    def test_an_agent_that_holds_no_chair_here_is_refused(self, skat, agent):
        agent.admitted()
        _, _, table_id = person_opens(skat)
        before = stored(skat)

        refused = agent.stand_up(table_id)

        assert refused.json()["reason"] == Refusal.NOT_SEATED
        assert stored(skat)[0] == before[0]

    def test_the_agents_chair_stays_when_its_owner_leaves_the_table(self, skat, agent):
        agent.admitted()
        owner, _, table_id = person_opens(skat)
        agent.sit_down(table_id, 2)

        with streams_of(skat, table_id, [(owner, None)]):
            skat.stand(owner, table_id)
            skat.client.cookies.clear()

        assert chairs_of(agent.read(table_id).json()) == [(None, None), ("Mozart", "agent"), (None, None)]

    def test_a_retry_with_the_same_id_changes_nothing_twice(self, skat, agent):
        agent.admitted()
        _, _, table_id = person_opens(skat)
        agent.sit_down(table_id, 2)
        first = agent.stand_up(table_id)
        before = stored(skat)

        again = agent.stand_up(table_id)

        assert again.json() == first.json()
        assert stored(skat)[0] == before[0]


class TestWhatEveryViewerSees:
    def test_every_answer_and_stream_message_shows_the_agents_chair_as_an_agent_without_an_account_or_owner(
        self, skat, agent, issuer
    ):
        agent.admitted()
        anna, anna_account, table_id = person_opens(skat)
        ben, ben_account = skat.member()
        watcher, watcher_account = skat.member()
        person_sits(skat, ben, table_id, 2)
        other_agent = Agent(skat, issuer, "other-subject", agent_name="Nova")
        other_agent.admitted()

        with streams_of(skat, table_id, [(anna, None), (watcher, None)]) as (anna_messages, watcher_messages):
            agent.sit_down(table_id, 3)
            seen = [
                read_as(skat, anna, table_id),
                read_as(skat, ben, table_id),
                read_as(skat, watcher, table_id),
                other_agent.read(table_id).json(),
                agent.read(table_id).json(),
                with_the_agent(anna_messages),
                with_the_agent(watcher_messages),
            ]

        for view in seen:
            assert chairs_of(view) == [
                (anna_account.username, "person"),
                (ben_account.username, "person"),
                ("Mozart", "agent"),
            ]
            text = str(view)
            assert OWNER not in text
            account_ids = {
                anna_account.id,
                ben_account.id,
                watcher_account.id,
                skat.stores.accounts.get(agent.subject).id,
                skat.stores.accounts.get(other_agent.subject).id,
            }
            assert not account_ids & set(text.split("'"))


class TestTheAgentsBearerAtTheRoutes:
    @pytest.mark.parametrize(
        ("path", "body"),
        [
            pytest.param(TABLES_PATH, {"series_length": 6}, id="open a table"),
            pytest.param(f"{TABLES_PATH}/{{table_id}}{TABLE_SIT_SUFFIX}", {"seat": 2}, id="sit"),
        ],
    )
    def test_the_bearer_is_admitted_as_the_agents_own_account(self, skat, agent, issuer, path, body):
        agent.admitted()
        _, _, table_id = person_opens(skat)
        token = issuer.agent_token(agent.subject)

        answer = skat.client.post(
            path.format(table_id=table_id),
            json={"command_id": "bearer-0001", **body},
            headers={"authorization": f"Bearer {token}", "origin": TEST_PUBLIC_ORIGIN, **FETCH},
        )

        assert answer.status_code == 200, answer.text
        assert ("Mozart", "agent") in chairs_of(answer.json())
        assert OWNER not in answer.text

    def test_the_bearer_stands_the_agents_own_chair_up(self, skat, agent, issuer):
        agent.admitted()
        _, _, table_id = person_opens(skat)
        agent.sit_down(table_id, 2)
        token = issuer.agent_token(agent.subject)

        answer = skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_STAND_SUFFIX}",
            json={"command_id": "bearer-0002"},
            headers={"authorization": f"Bearer {token}", "origin": TEST_PUBLIC_ORIGIN, **FETCH},
        )

        assert answer.status_code == 200, answer.text
        assert chairs_of(answer.json())[1] == (None, None)


class TestASeatedAgentPlays:
    def test_it_ends_a_game_and_the_list_entry_names_it_by_its_claim(self, skat, agent):
        table = AgentTable(skat, agent, Position.MIDDLEHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()

        thrown = agent.call(
            THROW_DOWN_CARDS_TOOL,
            table_id=table.table_id,
            command_id="agent-throw-0001",
            version=table.record.version,
        )

        entry = agent.call(READ_SERIES_LIST_TOOL, table_id=table.table_id).json()["entries"][0]
        assert not thrown.is_error, thrown.text
        assert entry["declarer_name"] == "Mozart"
        route = skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher)
        assert route.json()["entries"][0] == entry
