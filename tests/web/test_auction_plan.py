"""The route that sets, changes and clears a player's private plan for the auction answers the owner's view, wakes the
table when it leaves the version alone and carries the plan to nobody else.
"""

import json
from contextlib import contextmanager

import pytest

from skat.engine.deal import Position, positions_from
from skat.web.auction import TABLE_AUCTION_PLAN_SUFFIX
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, seated_three
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import FETCH, unnamed_lines

LIMIT = {"kind": "limit", "value": 30, "mode": "fixed"}


class Plans:
    """A dealt table of three seated people, told apart by position."""

    def __init__(self, skat):
        self.skat = skat
        self.table_id, people = seated_three(skat)
        by_position = {position: people[seat - 1][0] for seat, position in positions_from(DEALER_SEAT).items()}
        self.forehand = by_position[Position.FOREHAND]
        self.middlehand = by_position[Position.MIDDLEHAND]
        self.onlooker = people[3][0]

    @property
    def record(self):
        return self.skat.store.tables[self.table_id]

    def send(self, headers, plan, command_id="plan-0001", **extra):
        return self.skat.client.post(
            f"{TABLES_PATH}/{self.table_id}{TABLE_AUCTION_PLAN_SUFFIX}",
            json={"command_id": command_id, "plan": plan, **extra},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

    @contextmanager
    def second_tab(self, headers):
        """The table's views to one person's other tab, read after the first it opens with."""
        self.skat.client.cookies.clear()
        with self.skat.client.stream(
            "GET", f"{TABLES_PATH}/{self.table_id}{TABLE_EVENTS_SUFFIX}", headers=headers
        ) as stream:
            messages = (
                json.loads(line.removeprefix("data: "))
                for line in unnamed_lines(stream.iter_lines())
                if line.startswith("data: ")
            )
            next(messages)
            yield messages

    def read(self, headers):
        return self.skat.client.get(f"{TABLES_PATH}/{self.table_id}", headers=headers).json()["hand"]["auction"]


@pytest.fixture
def plans(skat):
    return Plans(skat)


class TestSetting:
    def test_a_limit_set_off_turn_answers_the_owners_view_and_leaves_the_version(self, plans):
        version = plans.record.version

        answer = plans.send(plans.forehand, LIMIT)

        assert answer.status_code == 200, answer.text
        assert answer.json()["hand"]["auction"]["plan"] == LIMIT
        assert (answer.json()["version"], plans.record.version) == (version, version)

    def test_a_limit_set_off_turn_reaches_the_owners_other_tab_at_the_unchanged_version(self, plans):
        version = plans.record.version

        with plans.second_tab(plans.forehand) as messages:
            plans.send(plans.forehand, LIMIT)
            woken = next(messages)

        assert (woken["hand"]["auction"]["plan"], woken["version"]) == (LIMIT, version)

    def test_the_mode_of_a_limit_is_ask_unless_it_says_fixed(self, plans):
        answer = plans.send(plans.forehand, {"kind": "limit", "value": 30})

        assert answer.json()["hand"]["auction"]["plan"] == {"kind": "limit", "value": 30, "mode": "ask"}

    def test_a_pass_ahead_is_set_and_null_clears_it(self, plans):
        assert plans.send(plans.forehand, {"kind": "pass"}).json()["hand"]["auction"]["plan"] == {
            "kind": "pass",
            "value": None,
            "mode": None,
        }

        cleared = plans.send(plans.forehand, None, command_id="plan-0002")

        assert cleared.json()["hand"]["auction"]["plan"] is None

    def test_the_plan_is_the_owners_alone(self, plans):
        plans.send(plans.forehand, LIMIT)

        assert plans.read(plans.forehand)["plan"] == LIMIT
        assert plans.read(plans.middlehand)["plan"] is None
        assert plans.read(plans.onlooker)["plan"] is None

    def test_a_plan_set_on_the_owners_turn_steps_and_answers_the_new_version(self, plans):
        version = plans.record.version

        answer = plans.send(plans.middlehand, {"kind": "pass"})

        assert (answer.status_code, answer.json()["version"]) == (200, version + 1)


class TestRefused:
    def test_a_value_off_the_ladder_is_refused_and_changes_nothing(self, plans):
        before = plans.record

        answer = plans.send(plans.forehand, {"kind": "limit", "value": 31})

        assert (answer.status_code, answer.json()["reason"]) == (409, "invalid-value")
        assert plans.record == before

    def test_a_player_without_a_chair_is_refused(self, plans):
        assert plans.send(plans.onlooker, {"kind": "pass"}).json()["reason"] == "not-seated"

    def test_signed_out_is_refused_and_changes_nothing(self, plans):
        before = plans.record

        answer = plans.send(FETCH, {"kind": "pass"})

        assert (answer.status_code, plans.record) == (401, before)

    @pytest.mark.parametrize(
        "plan",
        [
            pytest.param({"kind": "limit"}, id="a-limit-without-a-value"),
            pytest.param({"kind": "limit", "value": "30"}, id="a-value-that-is-text"),
            pytest.param({"kind": "limit", "value": 30, "mode": "maybe"}, id="a-mode-that-is-unknown"),
            pytest.param({"kind": "pass", "value": 30}, id="a-pass-with-a-value"),
            pytest.param({"kind": "stay"}, id="a-kind-that-is-unknown"),
            pytest.param({"value": 30}, id="no-kind"),
        ],
    )
    def test_a_body_that_breaks_the_contract_is_refused_and_stores_nothing(self, plans, plan):
        before = plans.record

        answer = plans.send(plans.forehand, plan)

        assert (answer.status_code, plans.record) == (422, before)

    def test_a_body_without_a_plan_is_refused(self, plans):
        answer = plans.skat.client.post(
            f"{TABLES_PATH}/{plans.table_id}{TABLE_AUCTION_PLAN_SUFFIX}",
            json={"command_id": "plan-0001"},
            headers={"origin": TEST_PUBLIC_ORIGIN, **plans.forehand},
        )

        assert answer.status_code == 422
