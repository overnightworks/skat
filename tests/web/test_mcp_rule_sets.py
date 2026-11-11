import pytest

from skat.web.mcp import READ_RULE_SETS_TOOL, SAVE_RULE_SET_TOOL
from skat.web.rule_sets import RULE_SETS_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import SUBJECT
from tests.web.support.skat import FETCH, Skat


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


class TestRuleSets:
    def test_an_agent_saves_and_reads_its_own_sets_and_its_owners_list_never_holds_them(self, skat, agent):
        owner, _ = skat.member()
        saved = agent.call(SAVE_RULE_SET_TOOL, name="Abend", options={"show_running_points": True})

        listed = agent.call(READ_RULE_SETS_TOOL)

        assert not saved.is_error
        assert listed.json() == {"sets": [saved.json()]}
        assert saved.json()["options"] == {"show_running_points": True, "kontra": None, "bock": None, "ramsch": None}
        assert skat.client.get(RULE_SETS_PATH, headers=owner).json() == {"sets": []}
        assert [each.owner_account for each in skat.rule_set_store.rule_sets.values()] == [
            skat.stores.accounts.get(SUBJECT).id
        ]

    def test_a_refused_save_is_a_failed_result_with_its_reason(self, agent):
        agent.call(SAVE_RULE_SET_TOOL, name="Abend", options={})

        refused = agent.call(SAVE_RULE_SET_TOOL, name="Abend", options={"show_running_points": True})

        assert (refused.is_error, refused.json()) == (True, {"reason": "name-taken"})

    def test_the_agents_bearer_cannot_delete_a_set_and_nothing_is_deleted(self, skat, issuer, agent):
        saved = agent.call(SAVE_RULE_SET_TOOL, name="Abend", options={})
        token = issuer.agent_token(SUBJECT)

        refused = skat.client.delete(
            f"{RULE_SETS_PATH}/{saved.json()['id']}",
            headers={"authorization": f"Bearer {token}", **FETCH, "origin": TEST_PUBLIC_ORIGIN},
        )

        assert refused.status_code in {401, 403}
        assert agent.call(READ_RULE_SETS_TOOL).json() == {"sets": [saved.json()]}
