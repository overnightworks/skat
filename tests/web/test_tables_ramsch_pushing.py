import pytest

from skat.web.rule_sets import RULE_SETS_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN

POINTS = {"occasion": "passed-in", "scoring": "points", "jungfrau": "doubles-loser", "durchmarsch": "wins-120"}


def pushing_options(rule="jacks-stay"):
    return {"ramsch": {**POINTS, "pushing": {"rule": rule}}}


class TestOpeningAPushingTable:
    @pytest.mark.parametrize("rule", ["jacks-stay", "jacks-may-go", "no-doubling"])
    def test_answers_the_rule_as_sent(self, skat, rule):
        headers, _ = skat.member()

        opened = skat.create(headers, options=pushing_options(rule))

        assert opened.json()["options"]["ramsch"] == {**POINTS, "pushing": {"rule": rule}}

    def test_a_table_without_the_rule_answers_null_for_it(self, skat):
        headers, _ = skat.member()

        opened = skat.create(headers, options={"ramsch": POINTS})

        assert opened.json()["options"]["ramsch"] == {**POINTS, "pushing": None}

    def test_a_saved_set_keeps_the_rule_and_a_table_opened_with_it_plays_it(self, skat):
        headers, _ = skat.member()

        saved = skat.client.post(
            RULE_SETS_PATH,
            json={"name": "Schieben", "options": pushing_options("jacks-may-go")},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

        expected = {**POINTS, "pushing": {"rule": "jacks-may-go"}}
        assert saved.json()["options"]["ramsch"] == expected
        assert skat.create(headers, options=pushing_options("jacks-may-go")).json()["options"]["ramsch"] == expected

    def test_a_retry_with_the_same_rule_is_the_first_table_and_with_another_rule_is_refused(self, skat):
        headers, _ = skat.member()
        first = skat.create(headers, options=pushing_options())

        same = skat.create(headers, options=pushing_options())
        other = skat.create(headers, options=pushing_options("no-doubling"))

        assert same.json()["id"] == first.json()["id"]
        assert other.status_code == 409

    @pytest.mark.parametrize(
        "options",
        [
            pytest.param({"ramsch": {**POINTS, "pushing": {"rule": "always"}}}, id="a-rule-outside-the-three"),
            pytest.param(
                {"ramsch": {**POINTS, "pushing": {"rule": "jacks-stay", "grand_hand": "off"}}}, id="an-extra-key"
            ),
            pytest.param({"ramsch": {**POINTS, "pushing": {}}}, id="an-empty-rule"),
            pytest.param({"ramsch": {**POINTS, "pushing": "jacks-stay"}}, id="a-bare-token"),
            pytest.param({"pushing": {"rule": "jacks-stay"}}, id="pushing-without-ramsch"),
        ],
    )
    def test_refuses_what_is_no_pushing_rule_with_422_and_opens_no_table(self, skat, options):
        headers, _ = skat.member()

        answer = skat.create(headers, options=options)

        assert answer.status_code == 422
        assert skat.store.tables == {}
