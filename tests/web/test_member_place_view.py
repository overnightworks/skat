"""A table is a place an agent reads its own view of at /mcp, and is told when it changes: a scripted client listens,
is woken by a person's move, reads its view, acts with the tool the view calls for and the table moves.
"""

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from agents.member import LEASE_SECONDS, STANDING_URI
from starlette.concurrency import run_in_threadpool
from structlog.testing import capture_logs

from skat.engine.deal import Position
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.table.asking import revision_of
from skat.table.records import EndedTable, Ending, Series, TableId, TableOptions
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX
from skat.web.mcp import (
    AGREE_TO_END_SERIES_TOOL,
    AUCTION_BID_TOOL,
    AUCTION_HOLD_TOOL,
    AUCTION_PASS_TOOL,
    CONTINUE_AFTER_RESULT_TOOL,
    DECLARE_GAME_TOOL,
    DECLINE_GIVE_UP_TOOL,
    MCP_GROUP,
    PLAY_CARD_TOOL,
    PUT_BACK_CARDS_TOOL,
    SAY_KONTRA_TOOL,
    SAY_NO_WORD_TOOL,
    STAND_UP_TOOL,
    START_NEW_SERIES_TOOL,
    TAKE_SKAT_TOOL,
)
from skat.web.member_place import view_signal
from skat.web.playing import TABLE_GIVE_UP_SUFFIX
from skat.web.ready import TABLE_NEW_SERIES_SUFFIX, TABLE_READY_SUFFIX
from skat.web.series_end import TABLE_SERIES_END_AGREE_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.calls import call_facts
from tests.support.payload_cards import with_known_deal
from tests.support.played_game import after_the_first_game
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import Agent, person_passes, person_posts, view_uri_of
from tests.web.support.playing import HERZ_GAME, card_body
from tests.web.support.presence import HOLD_SECONDS
from tests.web.support.sdk_agent import SdkAgent
from tests.web.support.skat import UNKNOWN_ID, AgentTable, Skat

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
UNKNOWN = "Unknown resource"
OWNER = "the-agents-owner"
INVITATION_SECONDS = 600
OTHER_AGENT_SUBJECT = "other-agent-subject"
ISSUER = "https://issuer.test.invalid"


class ViewSignalTap:
    """Stands between the service and the app's view signal: keeps what the service told, and tells the real signal
    again when a test wants a change that arrives late.
    """

    def __init__(self):
        self.told = []
        self._signal = None

    def through(self, signal):
        self._signal = signal

        def tell(table_id, accounts):
            self.told.append((table_id.value, accounts))
            signal(table_id, accounts)

        return tell

    def tell_late(self, skat, table_id, account):
        async def tell():
            await run_in_threadpool(self._signal, TableId(table_id), frozenset({account}))

        skat.client.portal.call(tell)


@pytest.fixture
def tap():
    return ViewSignalTap()


@pytest.fixture
def view_signal_through(tap):
    return tap.through


@pytest.fixture
def skat(hold, issuer, time, view_signal_through):
    skat = Skat(
        lambda: hold,
        issuer_transports=issuer.transports,
        chair_clock=time.clock,
        chair_scheduler=time,
        now=time.moment,
        view_signal_through=view_signal_through,
    )
    with skat.client:
        yield skat


@pytest.fixture
def sdk(skat, issuer):
    """The seated agent as a runner connects: through the SDK's client."""
    return SdkAgent(skat, issuer)


def a_person(skat, issuer):
    """A person's own token at /mcp: it carries no agent facts."""
    return Agent(skat, issuer, skat.member()[1].id, agent_owner=None, agent_name=None, groups=[MCP_GROUP])


def another_agent(skat, issuer, subject=OTHER_AGENT_SUBJECT):
    return Agent(skat, issuer, subject, agent_name="Bach")


def agent_account(skat, agent):
    return skat.stores.accounts.get(agent.subject).id


def unknown(answer):
    return answer.json()["error"]["message"] == UNKNOWN


def commands():
    """A fresh command id for each act of a scripted client."""
    number = 0
    while True:
        number += 1
        yield f"agent-act-{number:04d}"


def acts(session, table_id):
    """The client's tool call with its view's table version and a fresh command id."""
    ids = commands()

    def act(tool, view, **arguments):
        answer = session.call(
            tool, table_id=table_id, command_id=next(ids), version=view["state"]["version"], **arguments
        )
        assert not answer.is_error, answer.text
        return session.view(table_id)

    return act


class TestTheViewIsAServedResource:
    def test_a_seated_agent_lists_its_table_view_and_its_standing_says_the_view_is_served(
        self, agent, middlehand_auction
    ):
        standing = json.loads(agent.standing())["standings"]

        assert agent.listed_resources() == sorted([STANDING_URI, view_uri_of(middlehand_auction.table_id)])
        assert [(each["state"], each["serves_view"]) for each in standing] == [("active", True)]

    def test_the_revision_is_the_tables_version_with_no_ask_and_the_seat_on_turn_awaits(
        self, agent, middlehand_auction
    ):
        view = agent.view(middlehand_auction.table_id)

        assert (view["revision"], view["awaits_you"]) == (revision_of(middlehand_auction.record.version, 0), True)

    def test_the_state_is_what_read_table_answers_for_the_same_seat(self, agent, middlehand_auction):
        view = agent.view(middlehand_auction.table_id)

        assert without_presence(view["state"]) == without_presence(agent.read(middlehand_auction.table_id).json())

    def test_a_seat_that_is_not_on_turn_does_not_await(self, agent, forehand_auction):
        assert agent.view(forehand_auction.table_id)["awaits_you"] is False

    def test_the_state_holds_only_the_agents_own_cards_and_counts_for_the_others(self, agent, middlehand_auction):
        state = agent.view(middlehand_auction.table_id)["state"]

        assert len(state["hand"]["own_cards"]) == 10
        assert [chair["hand"]["card_count"] for chair in state["chairs"]] == [10, 10, 10]
        assert state["hand"]["skat_count"] == 2


def without_presence(state):
    """The part of a table answer that says who is present, which changes with no new revision, left out."""
    state = {key: value for key, value in state.items() if key != "watchers"}
    chairs = state.get("chairs", [])
    return {**state, "chairs": [{key: value for key, value in chair.items() if key != "is_away"} for chair in chairs]}


class TestOnlyTheSeatedAgentReadsItsView:
    @pytest.fixture
    def uri(self, middlehand_auction):
        return view_uri_of(middlehand_auction.table_id)

    def test_a_persons_token_reads_an_unknown_resource_and_lists_nothing(self, skat, issuer, uri):
        person = a_person(skat, issuer)

        assert (unknown(person.read_resource(uri)), person.listed_resources()) == (True, [])

    def test_a_token_without_agent_facts_for_the_seated_agents_account_reads_an_unknown_resource(
        self, skat, issuer, agent, uri
    ):
        person_token = Agent(skat, issuer, agent.subject, agent_owner=None, agent_name=None, groups=[MCP_GROUP])

        assert (unknown(person_token.read_resource(uri)), person_token.listed_resources()) == (True, [])

    def test_another_agent_that_holds_no_chair_there_reads_an_unknown_resource_and_lists_only_its_standing(
        self, skat, issuer, uri
    ):
        other = another_agent(skat, issuer)

        assert (unknown(other.read_resource(uri)), other.listed_resources()) == (True, [STANDING_URI])

    def test_an_agent_that_is_only_invited_reads_an_unknown_resource(self, skat, issuer, time, middlehand_auction, uri):
        other = another_agent(skat, issuer)
        skat.client.portal.call(_inviting, skat, middlehand_auction.table_id, call_facts(other.subject, OWNER))

        assert (unknown(other.read_resource(uri)), other.listed_resources()) == (True, [STANDING_URI])

    def test_a_table_that_does_not_exist_reads_an_unknown_resource(self, agent, middlehand_auction):
        assert unknown(agent.read_resource(view_uri_of(UNKNOWN_ID)))

    @pytest.mark.parametrize(
        "spell",
        [
            pytest.param(str.upper, id="upper-case"),
            pytest.param(lambda uri: uri + "/", id="trailing-slash"),
            pytest.param(lambda uri: uri + "?x=1", id="query"),
            pytest.param(lambda uri: uri.removesuffix("/view"), id="the-window-without-the-view"),
            pytest.param(lambda uri: uri.replace("/table/", "/room/"), id="another-kind-of-place"),
            pytest.param(lambda uri: uri.replace("member://", "MEMBER://"), id="another-scheme-spelling"),
        ],
    )
    def test_a_uri_that_is_not_the_canonical_spelling_reads_an_unknown_resource(self, agent, uri, spell):
        assert unknown(agent.read_resource(spell(uri)))

    def test_the_answers_for_all_of_them_are_the_same(self, skat, issuer, agent, uri):
        person = a_person(skat, issuer)
        other = another_agent(skat, issuer)

        answers = {
            json.dumps(reader.read_resource(each).json()["error"], sort_keys=True)
            for reader in (person, other, agent)
            for each in (view_uri_of(UNKNOWN_ID), uri.upper())
        } | {json.dumps(person.read_resource(uri).json()["error"], sort_keys=True)}

        assert len(answers) == 1


async def _inviting(skat, table_id, facts):
    return await run_in_threadpool(
        skat.tables.invite_agent, TableId(table_id), facts, timedelta(seconds=INVITATION_SECONDS)
    )


def a_standing_change(skat, agent, time):
    """A change of the agent's standing that a person causes and no removal explains: an invitation to a table of a
    member, which the agent does not sit at.
    """
    person = skat.member()
    table_id = skat.create(person[0]).json()["id"]
    skat.client.portal.call(_inviting, skat, table_id, call_facts(agent.subject, OWNER))
    skat.client.cookies.clear()


class TestTheViewEndsWithTheChair:
    def test_standing_up_takes_the_table_from_the_listing_and_the_view(self, skat, agent):
        table_id = agent.open_table().json()["id"]
        listed = agent.listed_resources()

        agent.stand_up(table_id)

        assert view_uri_of(table_id) in listed
        assert agent.listed_resources() == [STANDING_URI]
        assert unknown(agent.read_resource(view_uri_of(table_id)))

    @pytest.mark.parametrize(
        ("removal", "standing_changes"),
        [
            pytest.param(
                lambda skat, time, session, table_id: session.call(
                    STAND_UP_TOOL, table_id=table_id, command_id="agent-stand-up"
                ),
                1,
                id="stand-up",
            ),
            pytest.param(
                lambda skat, time, session, table_id: skat.client.portal.call(
                    time.advance, LEASE_SECONDS + HOLD_SECONDS + 1
                ),
                1,
                id="hold-release",
            ),
            pytest.param(
                lambda skat, time, session, table_id: skat.store.tables.__setitem__(
                    table_id,
                    EndedTable(TableId(table_id), skat.store.tables[table_id].version + 1, Ending.empty(3600)),
                ),
                0,
                id="table-end",
            ),
        ],
    )
    def test_a_removal_ends_the_delivery_of_the_view_on_a_stream_that_is_open(
        self, skat, time, tap, sdk, agent, removal, standing_changes
    ):
        table_id = agent.open_table().json()["id"]

        with sdk.connected() as session, session.listening() as events:
            removal(skat, time, session, table_id)
            assert [events.next_uri() for _ in range(standing_changes)] == [STANDING_URI] * standing_changes
            tap.tell_late(skat, table_id, agent_account(skat, agent))
            a_standing_change(skat, agent, time)

            assert events.next_uri() == STANDING_URI

        assert agent.listed_resources() == [STANDING_URI]
        assert unknown(agent.read_resource(view_uri_of(table_id)))


class TestTheViewFollowsTheLease:
    def test_a_view_signalled_after_the_lease_lapsed_is_not_delivered_and_the_next_listen_delivers_again(
        self, skat, time, tap, sdk, agent, forehand_auction
    ):
        table = forehand_auction

        with sdk.connected() as session, session.listening() as lapsed:
            tap.told.clear()
            skat.client.portal.call(time.advance, LEASE_SECONDS + 1)
            table.middlehand_bids()
            assert tap.told == [(table.table_id, frozenset({agent_account(skat, agent)}))]
            a_standing_change(skat, agent, time)

            assert lapsed.next_uri() == STANDING_URI
            with session.listening() as relistened:
                moved = session.call(
                    AUCTION_HOLD_TOOL,
                    table_id=table.table_id,
                    command_id="agent-hold-0001",
                    version=table.record.version,
                )
                view = relistened.woken_view(table.table_id)

        assert (moved.is_error, view["revision"], view["awaits_you"]) == (
            False,
            revision_of(table.record.version, 0),
            False,
        )


class TestTheWakeOfACommit:
    def test_a_render_of_the_table_signals_nothing(self, skat, agent, forehand_auction, tap):
        tap.told.clear()
        agent.view(forehand_auction.table_id)
        agent.read(forehand_auction.table_id)
        forehand_auction.read_as(forehand_auction.watcher)

        assert tap.told == []

    def test_two_agents_each_read_only_their_own_hand(self, skat, issuer):
        first = Agent(skat, issuer, "first-agent", agent_name="Mozart")
        second = another_agent(skat, issuer)
        person = skat.member()
        table_id = skat.create(person[0]).json()["id"]
        first.sit_down(table_id, 2)
        second.sit_down(table_id, 3)
        with_known_deal(skat, table_id)
        skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_BID_SUFFIX}",
            json={"command_id": "person-bid", "version": skat.store.tables[table_id].version, "value": 18},
            headers={"origin": TEST_PUBLIC_ORIGIN, **person[0]},
        )

        views = [each.view(table_id)["state"] for each in (first, second)]

        assert [[chair["is_mine"] for chair in view["chairs"]] for view in views] == [
            [False, True, False],
            [False, False, True],
        ]
        assert views[0]["hand"]["own_cards"] != views[1]["hand"]["own_cards"]
        assert [each.view(table_id)["awaits_you"] for each in (first, second)] == [False, True]


class TestAPersonsMoveSignalsEachSeatedAgent:
    @pytest.fixture
    def pulses(self):
        return []

    @pytest.fixture
    def view_signal_through(self, pulses):
        class Recording:
            def changed(self, recipient, uri):
                pulses.append((recipient.sub, uri))

        return lambda _signal: view_signal(Recording(), ISSUER)

    def test_each_agent_is_signalled_on_its_own_view_uri(self, skat, issuer, pulses):
        first = Agent(skat, issuer, "first-agent", agent_name="Mozart")
        second = another_agent(skat, issuer)
        person = skat.member()
        table_id = skat.create(person[0]).json()["id"]
        first.sit_down(table_id, 2)
        second.sit_down(table_id, 3)
        with_known_deal(skat, table_id)
        pulses.clear()

        skat.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_AUCTION_BID_SUFFIX}",
            json={"command_id": "person-bid", "version": skat.store.tables[table_id].version, "value": 18},
            headers={"origin": TEST_PUBLIC_ORIGIN, **person[0]},
        )

        assert sorted(pulses) == sorted((agent_account(skat, each), view_uri_of(table_id)) for each in (first, second))


class TestASignalThatFailsAfterTheCommit:
    @pytest.fixture
    def view_signal_through(self):
        class Failing:
            def changed(self, recipient, uri):
                raise ConnectionResetError

        return lambda _signal: view_signal(Failing(), ISSUER)

    def test_is_logged_by_its_type_and_the_command_stays_committed(self, skat, agent, forehand_auction):
        before = forehand_auction.record.version

        with capture_logs() as logs:
            forehand_auction.middlehand_bids()

        assert forehand_auction.record.version == before + 1
        assert [log["error"] for log in logs if log["event"] == "member_signal_failed"] == ["ConnectionResetError"]
        assert agent.view(forehand_auction.table_id)["revision"] == revision_of(before + 1, 0)


class TestTheToolDescriptionsNameTheView:
    def test_every_description_that_sends_a_seated_agent_to_read_table_also_names_the_table_view(self, agent):
        tools = agent.request("tools/list").json()["result"]["tools"]
        before_a_chair = {"sit_down", "open_table", "read_paused_tables"}

        naming_read_table = {tool["name"] for tool in tools if "read_table" in tool["description"]} - before_a_chair
        naming_the_view = {tool["name"] for tool in tools if "view" in tool["description"]}

        assert naming_read_table <= naming_the_view
        assert len(naming_read_table) > 10


class TestARestartReadsTheSameView:
    def test_the_view_after_a_restart_is_the_view_before_it(self, skat, issuer, hold, agent, middlehand_auction):
        before = agent.view(middlehand_auction.table_id)

        restarted = Skat(lambda: hold, store=skat.store, stores=skat.stores, issuer_transports=issuer.transports)
        with restarted.client:
            after = Agent(restarted, issuer, agent.subject).view(middlehand_auction.table_id)

        assert without_presence(after["state"]) == without_presence(before["state"])
        assert (after["revision"], after["awaits_you"]) == (before["revision"], True)


class TestARefusedActIsAnErrorResult:
    @pytest.mark.parametrize(
        ("tool", "arguments"),
        [
            pytest.param(AUCTION_BID_TOOL, {"version": 99, "value": 18}, id="stale-version"),
            pytest.param(PLAY_CARD_TOOL, {"version": 1, **card_body(HERZ_GAME[0])}, id="wrong-phase"),
            pytest.param(AUCTION_PASS_TOOL, {}, id="arguments-that-do-not-fit"),
            pytest.param(AUCTION_PASS_TOOL, {"table_id": UNKNOWN_ID, "version": 1}, id="unknown-table"),
        ],
    )
    def test_a_refusal_of_the_table_answers_an_error_and_not_a_success(
        self, agent, middlehand_auction, tool, arguments
    ):
        arguments = {"table_id": middlehand_auction.table_id, "command_id": "agent-refused", **arguments}

        assert agent.call(tool, **arguments).is_error is True

    def test_a_repeated_mark_is_a_success(self, agent, forehand_auction):
        table = forehand_auction
        table.declared_hand_game()
        skat_table = table.skat.store
        skat_table.tables[table.table_id] = after_the_first_game(table.record)
        version = table.record.version

        marks = [
            agent.call(CONTINUE_AFTER_RESULT_TOOL, table_id=table.table_id, command_id=f"agent-mark-{each}", ordinal=1)
            for each in (1, 2)
        ]

        assert [mark.is_error for mark in marks] == [False, False]
        assert table.record.version == version + 1


class TestAScriptedClientIsWokenAndPlays:
    """Each case of `awaits_you`: the SDK client listens on the standing, a person's move wakes it, it reads its view,
    calls the tool the view asks for and reads the table moved on."""

    def test_case_1_the_auction_asks_the_forehand_to_answer_a_bid(self, skat, sdk, forehand_auction):
        table = forehand_auction

        with sdk.connected() as session, session.listening() as events:
            act = acts(session, table.table_id)
            table.middlehand_bids()
            view = events.woken_view(table.table_id)
            moved = act(AUCTION_HOLD_TOOL, view)

        assert (view["awaits_you"], view["state"]["hand"]["auction"]["awaiting"]) == (True, "answer")
        assert (moved["revision"] > view["revision"], moved["awaits_you"]) == (True, False)

    def test_case_2_the_declarer_takes_puts_back_and_declares_each_at_a_new_revision(
        self, skat, sdk, agent, middlehand_auction
    ):
        table = middlehand_auction
        assert not agent.take_step(AUCTION_BID_TOOL, table, command_id="agent-bid", value=18).is_error
        person_passes(table, FOREHAND)

        with sdk.connected() as session, session.listening() as events:
            act = acts(session, table.table_id)
            person_passes(table, REARHAND)
            choosing = events.woken_view(table.table_id)
            discarding = act(TAKE_SKAT_TOOL, choosing)
            two = discarding["state"]["hand"]["own_cards"][:2]
            picked = act(PUT_BACK_CARDS_TOOL, discarding, cards=two)
            declared = act(DECLARE_GAME_TOOL, picked, game="herz", hand=False, ouvert=False, announcement="none")

        stages = [view["state"]["hand"]["declaring"]["stage"] for view in (choosing, discarding, picked)]
        assert stages == ["choosing", "discarding", "picked"]
        assert [view["awaits_you"] for view in (choosing, discarding, picked, declared)] == [True, True, True, False]
        revisions = [view["revision"] for view in (choosing, discarding, picked, declared)]
        assert revisions == sorted(set(revisions))

    def test_case_3_the_turn_in_play_asks_for_a_legal_card(self, skat, sdk, middlehand_auction):
        table = middlehand_auction
        table.declared_hand_game()

        with sdk.connected() as session, session.listening() as events:
            act = acts(session, table.table_id)
            table.accepted(HERZ_GAME[0])
            view = events.woken_view(table.table_id)
            moved = act(PLAY_CARD_TOOL, view, **card_body(HERZ_GAME[1]))

        assert view["awaits_you"] is True
        assert card_body(HERZ_GAME[1]) in view["state"]["hand"]["playing"]["legal_cards"]
        assert (moved["revision"] > view["revision"], moved["awaits_you"]) == (True, False)

    def test_case_4_a_give_up_question_asks_the_opponent_that_is_not_on_turn(self, skat, sdk, forehand_auction):
        table = forehand_auction
        table.declared_hand_game()
        # The declarer may ask to give up with the second trick led; the rearhand is on turn then.
        table.played_out(HERZ_GAME[:4])

        with sdk.connected() as session, session.listening() as events:
            act = acts(session, table.table_id)
            assert table.act(TABLE_GIVE_UP_SUFFIX).status_code == 200
            view = events.woken_view(table.table_id)
            moved = act(DECLINE_GIVE_UP_TOOL, view)

        playing = view["state"]["hand"]["playing"]
        assert (view["awaits_you"], playing["give_up"] is not None, playing["turn_seat"]) == (True, True, 2)
        assert (moved["revision"] > view["revision"], moved["awaits_you"]) == (True, False)

    def test_case_5_a_result_asks_the_seat_that_has_not_continued(self, skat, sdk, forehand_auction):
        table = after_a_game(forehand_auction)

        with sdk.connected() as session, session.listening() as events:
            person_posts(table, TABLE_READY_SUFFIX, MIDDLEHAND, ordinal=1)
            view = events.woken_view(table.table_id)
            ordinal = view["state"]["result"]["ordinal"]
            answer = session.call(
                CONTINUE_AFTER_RESULT_TOOL, table_id=table.table_id, command_id="agent-continue", ordinal=ordinal
            )
            moved = session.view(table.table_id)

        assert (view["awaits_you"], answer.is_error) == (True, False)
        assert (moved["revision"] > view["revision"], moved["awaits_you"]) == (True, False)

    def test_case_6_the_end_of_the_series_asks_the_seat_that_has_not_voted_on_a_new_series(
        self, skat, sdk, forehand_auction
    ):
        table = after_a_game(forehand_auction, series_deals=36)

        with sdk.connected() as session, session.listening() as events:
            person_posts(table, TABLE_NEW_SERIES_SUFFIX, MIDDLEHAND)
            view = events.woken_view(table.table_id)
            answer = session.call(START_NEW_SERIES_TOOL, table_id=table.table_id, command_id="agent-new-series")
            moved = session.view(table.table_id)

        assert (view["awaits_you"], view["state"]["series"]["over"], answer.is_error) == (True, True, False)
        assert (moved["revision"] > view["revision"], moved["awaits_you"]) == (True, False)

    def test_case_7_an_early_end_proposal_asks_the_seat_that_has_not_answered(self, skat, sdk, forehand_auction):
        table = after_a_game(forehand_auction, ready=(1, 2, 3))

        with sdk.connected() as session, session.listening() as events:
            person_posts(table, TABLE_SERIES_END_AGREE_SUFFIX, MIDDLEHAND)
            view = events.woken_view(table.table_id)
            answer = session.call(AGREE_TO_END_SERIES_TOOL, table_id=table.table_id, command_id="agent-agree")
            moved = session.view(table.table_id)

        assert (view["awaits_you"], view["state"]["series"]["end_proposal"] is not None) == (True, True)
        assert (answer.is_error, moved["revision"] > view["revision"], moved["awaits_you"]) == (False, True, False)


class TestAScriptedClientIsAskedForItsKontraWordOnce:
    @pytest.fixture
    def rearhand_table(self, skat, agent):
        """A table with Kontra where the agent holds the rearhand chair, an opponent who is not on turn."""
        table = AgentTable(skat, agent, REARHAND)
        options = KontraOptions(KontraSayer.ANY_OPPONENT, KontraReach.KONTRA_RE, KontraDeadline.OWN_CARD)
        record = skat.store.tables[table.table_id]
        skat.store.tables[table.table_id] = replace(record, options=TableOptions(kontra=options))
        skat.client.cookies.clear()
        return table

    @pytest.mark.parametrize(
        ("tool", "arguments"),
        [pytest.param(SAY_NO_WORD_TOOL, {}, id="no"), pytest.param(SAY_KONTRA_TOOL, {"word": "kontra"}, id="yes")],
    )
    def test_the_declaration_asks_the_opponent_and_the_answer_ends_the_wait(
        self, skat, sdk, rearhand_table, tool, arguments
    ):
        table = rearhand_table

        with sdk.connected() as session, session.listening() as events:
            act = acts(session, table.table_id)
            table.declared_hand_game()
            view = events.woken_view(table.table_id)
            moved = act(tool, view, **arguments)

        playing = view["state"]["hand"]["playing"]
        assert (view["awaits_you"], playing["kontra"]["my_word"], playing["turn_seat"]) == (True, "kontra", 3)
        assert (moved["revision"] > view["revision"], moved["awaits_you"]) == (True, False)

    def test_play_goes_on_and_the_answered_seat_is_not_asked_again_for_the_word(self, skat, sdk, rearhand_table):
        table = rearhand_table

        with sdk.connected() as session, session.listening() as events:
            act = acts(session, table.table_id)
            table.declared_hand_game()
            answered = act(SAY_NO_WORD_TOOL, events.woken_view(table.table_id))
            table.accepted(HERZ_GAME[0])
            later = session.view(table.table_id)

        assert (answered["awaits_you"], later["awaits_you"]) == (False, False)
        assert later["state"]["hand"]["playing"]["kontra"]["my_word_answered"] is True


def after_a_game(table, *, series_deals=1, ready=()):
    """The table the agent sits at, a game played out and the hand over, in the series of 36 games at its deal."""
    table.declared_hand_game()
    record = after_the_first_game(table.record, *ready)
    table.skat.store.tables[table.table_id] = replace(record, series=Series(36, series_deals))
    table.skat.client.cookies.clear()
    return table
