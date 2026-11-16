import pytest

from skat.web.rule_sets import RULE_SETS_PATH
from skat.web.tables import TABLES_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN

SWITCHES = [
    pytest.param({}, {"partner_agrees": False, "any_time": False}, id="both-left-out"),
    pytest.param({"partner_agrees": True}, {"partner_agrees": True, "any_time": False}, id="partner-agrees"),
    pytest.param({"any_time": True}, {"partner_agrees": False, "any_time": True}, id="any-time"),
    pytest.param({"partner_agrees": True, "any_time": True}, {"partner_agrees": True, "any_time": True}, id="both-on"),
    pytest.param(
        {"partner_agrees": False, "any_time": False}, {"partner_agrees": False, "any_time": False}, id="both-off"
    ),
]


class TestOpeningATable:
    @pytest.mark.parametrize(("requested", "answered"), SWITCHES)
    def test_the_opener_and_a_watcher_read_the_special_rules_of_giving_up_the_table_was_opened_with(
        self, skat, requested, answered
    ):
        headers, _ = skat.member()
        watcher, _ = skat.member()

        opened = skat.create(headers, options={"give_up": requested})
        read = skat.client.get(f"{TABLES_PATH}/{opened.json()['id']}", headers=watcher)

        assert (opened.json()["options"]["give_up"], read.json()["options"]["give_up"]) == (answered, answered)

    def test_a_table_opened_without_options_gives_up_by_the_isko(self, skat):
        headers, _ = skat.member()

        opened = skat.create(headers)

        assert opened.json()["options"]["give_up"] == {"partner_agrees": False, "any_time": False}

    @pytest.mark.parametrize(
        "give_up",
        [{"partner_agrees": "yes"}, {"any_time": 1}, {"any_time": None}, {"other": True}, True, None],
    )
    def test_refuses_special_rules_that_are_no_strict_switch_and_stores_nothing(self, skat, give_up):
        headers, _ = skat.member()

        assert skat.create(headers, options={"give_up": give_up}).status_code == 422
        assert skat.store.tables == {}


class TestARuleSet:
    @pytest.mark.parametrize(("requested", "answered"), SWITCHES)
    def test_a_saved_set_answers_and_lists_its_special_rules_of_giving_up(self, skat, requested, answered):
        headers, _ = skat.member()
        writing = {"origin": TEST_PUBLIC_ORIGIN, **headers}

        saved = skat.client.post(
            RULE_SETS_PATH, json={"name": "Abend", "options": {"give_up": requested}}, headers=writing
        )
        listed = skat.client.get(RULE_SETS_PATH, headers=headers)

        assert (saved.json()["options"]["give_up"], listed.json()["sets"][0]["options"]["give_up"]) == (
            answered,
            answered,
        )
