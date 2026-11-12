"""A nudge reaches an agent the way the deadline's ask does: a pulse on its view's URI at once and a revision raised by
one, with the same table and the same `awaits_you`; an agent nudges as a person does, through `nudge_seat`.
"""

import pytest
from structlog.testing import capture_logs

from skat.engine.deal import Position
from skat.table.asking import ASK_AGAIN_AFTER, ASKS_AGAIN, revision_of
from skat.table.nudging import NUDGES_PER_VERSION
from skat.web.mcp import AUCTION_HOLD_TOOL, NUDGE_SEAT_TOOL
from skat.web.nudging import TABLE_NUDGE_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import with_known_deal
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import Agent, view_uri_of
from tests.web.support.changes import RecordedChanges
from tests.web.support.sdk_agent import SdkAgent
from tests.web.support.skat import Skat

REARHAND = Position.REARHAND
AWAITED_AGENT_SUBJECT = "awaited-agent"
OTHER_AGENT_SUBJECT = "other-agent"


@pytest.fixture
def changes():
    return RecordedChanges()


@pytest.fixture
def skat(hold, issuer, time, changes):
    skat = Skat(
        lambda: hold,
        issuer_transports=issuer.transports,
        chair_clock=time.clock,
        chair_scheduler=time,
        now=time.moment,
        resource_changes=changes.wired,
    )
    with skat.client:
        yield skat


@pytest.fixture
def sdk(skat, issuer):
    return SdkAgent(skat, issuer)


@pytest.fixture
def pulses(changes):
    return changes.told


def wait(skat, time, seconds):
    skat.client.portal.call(time.advance, seconds)


def account_of(skat, agent):
    return skat.stores.accounts.get(agent.subject).id


def own_chair(view):
    return next(chair for chair in view["state"]["chairs"] if chair["is_mine"])


def nudge(skat, table_id, headers, seat, *, version, nudges=0):
    skat.client.cookies.clear()
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_NUDGE_SUFFIX}",
        json={"version": version, "seat": seat, "nudges": nudges},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


class TestAnAgentOnTurnIsNudged:
    def test_the_agent_is_told_at_once_and_reads_a_revision_raised_by_one_for_the_same_table(
        self, skat, time, agent, middlehand_auction, pulses
    ):
        table = middlehand_auction
        agent.view(table.table_id)
        wait(skat, time, ASK_AGAIN_AFTER)
        asked = agent.view(table.table_id)
        pulses.clear()

        answer = nudge(
            skat,
            table.table_id,
            table.at[REARHAND],
            own_chair(asked)["seat"],
            version=asked["state"]["version"],
        )
        nudged = agent.view(table.table_id)

        assert answer.status_code == 200, answer.text
        assert pulses == [(account_of(skat, agent), view_uri_of(table.table_id))]
        assert nudged["revision"] == asked["revision"] + 1
        assert (nudged["awaits_you"], nudged["state"]["version"]) == (True, asked["state"]["version"])
        nudge_shown = own_chair(nudged)["nudge"]
        assert (nudge_shown["nudges"], nudge_shown["may_nudge"], nudge_shown["by_name"] is not None) == (1, False, True)

    def test_every_ask_and_every_nudge_gives_a_revision_not_seen_before(self, skat, time, agent, middlehand_auction):
        table = middlehand_auction
        first = agent.view(table.table_id)
        version = first["state"]["version"]
        seat = own_chair(first)["seat"]
        revisions = [first["revision"]]

        for made in range(NUDGES_PER_VERSION):
            wait(skat, time, ASK_AGAIN_AFTER)
            revisions.append(agent.view(table.table_id)["revision"])
            answer = nudge(skat, table.table_id, table.at[REARHAND], seat, version=version, nudges=made)
            assert answer.status_code == 200, answer.text
            revisions.append(agent.view(table.table_id)["revision"])

        assert revisions == [revision_of(version, count) for count in range(ASKS_AGAIN + NUDGES_PER_VERSION + 1)]

    def test_the_agent_that_is_nudged_again_after_a_retry_is_not_told_twice(
        self, skat, time, agent, middlehand_auction, pulses
    ):
        table = middlehand_auction
        first = agent.view(table.table_id)
        wait(skat, time, ASK_AGAIN_AFTER)
        asked = (table.table_id, table.at[REARHAND], own_chair(first)["seat"])
        nudge(skat, *asked, version=first["state"]["version"])
        pulses.clear()

        retry = nudge(skat, *asked, version=first["state"]["version"])

        assert (retry.status_code, pulses) == (200, [])


class TestASignalThatFails:
    def test_is_logged_by_its_type_and_the_nudge_stands(self, skat, time, agent, middlehand_auction, changes):
        table = middlehand_auction
        first = agent.view(table.table_id)
        wait(skat, time, ASK_AGAIN_AFTER)
        changes.failure = ConnectionResetError()

        with capture_logs() as logs:
            answer = nudge(
                skat, table.table_id, table.at[REARHAND], own_chair(first)["seat"], version=first["state"]["version"]
            )

        assert answer.status_code == 200, answer.text
        assert [log["error"] for log in logs if log["event"] == "member_signal_failed"] == ["ConnectionResetError"]
        assert own_chair(agent.view(table.table_id))["nudge"]["nudges"] == 1


class TestTwoAgentsAtOneTable:
    """The awaited agent opened the table and holds the middlehand chair; a person holds the second chair and the
    other agent the third.
    """

    @pytest.fixture
    def awaited(self, skat, issuer):
        return Agent(skat, issuer, AWAITED_AGENT_SUBJECT, agent_name="Mozart")

    @pytest.fixture
    def other(self, skat, issuer):
        return Agent(skat, issuer, OTHER_AGENT_SUBJECT, agent_name="Bach")

    @pytest.fixture
    def person(self, skat):
        return skat.member()[0]

    @pytest.fixture
    def table_id(self, skat, awaited, other, person):
        table_id = awaited.open_table().json()["id"]
        skat.sit(person, table_id, 2)
        other.sit_down(table_id, 3)
        with_known_deal(skat, table_id)
        return table_id

    def test_the_agent_the_table_does_not_wait_for_keeps_its_revision_and_sees_the_chair_nudged(
        self, skat, time, awaited, other, person, table_id
    ):
        views = {each: each.view(table_id) for each in (awaited, other)}
        wait(skat, time, ASK_AGAIN_AFTER)
        before = other.view(table_id)
        version = views[other]["state"]["version"]

        assert nudge(skat, table_id, person, 1, version=version).status_code == 200
        after = other.view(table_id)

        assert before["revision"] == after["revision"] == views[other]["revision"]
        assert (before["state"]["chairs"][0]["nudge"], after["state"]["chairs"][0]["nudge"]) == (
            {"nudges": 0, "may_nudge": True, "by_name": None},
            {"nudges": 1, "may_nudge": True, "by_name": None},
        )

    def test_an_agent_nudges_through_the_tool_as_a_person_does(self, skat, time, awaited, other, table_id):
        awaited_view = awaited.view(table_id)
        version = awaited_view["state"]["version"]
        arguments = {"table_id": table_id, "version": version, "seat": 1, "nudges": 0}

        too_early = other.call(NUDGE_SEAT_TOOL, **arguments)
        wait(skat, time, ASK_AGAIN_AFTER)
        asked = awaited.view(table_id)
        nudged = other.call(NUDGE_SEAT_TOOL, **arguments)

        assert (too_early.is_error, too_early.json()["reason"]) == (True, "too-early")
        assert nudged.is_error is False
        assert awaited.view(table_id)["revision"] == asked["revision"] + 1


class TestAScriptedClientIsNudged:
    def test_a_client_on_turn_is_woken_by_the_nudge_reads_a_raised_revision_and_plays(
        self, skat, time, sdk, forehand_auction
    ):
        table = forehand_auction

        with sdk.connected() as session, session.listening() as events:
            table.middlehand_bids()
            view = events.woken_view(table.table_id)
            wait(skat, time, ASK_AGAIN_AFTER)
            asked = events.woken_view(table.table_id)
            version = asked["state"]["version"]
            answer = nudge(skat, table.table_id, table.at[REARHAND], own_chair(asked)["seat"], version=version)
            nudged = events.woken_view(table.table_id)
            hold = session.call(
                AUCTION_HOLD_TOOL, table_id=table.table_id, command_id="agent-hold", version=nudged["state"]["version"]
            )

        assert answer.status_code == 200, answer.text
        assert (asked["revision"], nudged["revision"]) == (view["revision"] + 1, view["revision"] + 2)
        assert (nudged["awaits_you"], nudged["state"]["version"]) == (True, version)
        assert hold.is_error is False
