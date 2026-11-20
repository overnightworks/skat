"""The person key: the pseudonym a framed table gives the call for each seated account, and its route."""

import re
from http import HTTPStatus

import pytest
from agents.tools import AGENT_TOOL_EXTENSION, ToolExclusion, read_decision

from skat.web.call import TABLE_PERSON_KEYS_SUFFIX, person_key
from skat.web.tables import TABLES_PATH
from tests.support.sign_in_settings import TEST_ISSUER
from tests.web.support.agent import SUBJECT
from tests.web.support.skat import FETCH, Skat

# The vector the call (hopin) checks its own derivation against: the same bytes in, the same key out.
VECTOR_ISSUER = "https://issuer.example/realms/hallucinai"
VECTOR_SUBJECT = "f3a1c9e7-77b2-4d0a-9c53-2e8d5a1b6f40"
VECTOR_TABLE = "00112233445566778899aabbccddeeff"
VECTOR_KEY = "353301ccc7ee3bc965f8709f628dc16f25e6b9a18b529b59c9ec0a74060be9af"
KEY_PATTERN = re.compile(r"[0-9a-f]{64}")


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


def person_keys_path(table_id):
    return f"{TABLES_PATH}/{table_id}{TABLE_PERSON_KEYS_SUFFIX}"


def read_person_keys(skat, headers, table_id):
    return skat.client.get(person_keys_path(table_id), headers=headers)


@pytest.fixture
def felix(skat):
    return skat.member()


@pytest.fixture
def table_id(skat, felix):
    """A table Felix opened and sits at, chair 1."""
    created = skat.create(felix[0])
    skat.client.cookies.clear()
    return created.json()["id"]


class TestThePersonKey:
    def test_the_vector_agreed_with_the_call_derives_the_same_key(self):
        assert person_key(VECTOR_ISSUER, VECTOR_SUBJECT, VECTOR_TABLE) == VECTOR_KEY

    @pytest.mark.parametrize(
        ("issuer", "subject", "table"),
        [
            pytest.param("https://issuer.example/realms/other", VECTOR_SUBJECT, VECTOR_TABLE, id="another-issuer"),
            pytest.param(VECTOR_ISSUER, "another-subject", VECTOR_TABLE, id="another-subject"),
            pytest.param(VECTOR_ISSUER, VECTOR_SUBJECT, "ffeeddccbbaa99887766554433221100", id="another-table"),
        ],
    )
    def test_each_of_issuer_subject_and_table_changes_the_key(self, issuer, subject, table):
        assert person_key(issuer, subject, table) != VECTOR_KEY

    def test_the_parts_cannot_be_shifted_into_one_another(self):
        assert person_key("a", "bc", VECTOR_TABLE) != person_key("ab", "c", VECTOR_TABLE)


class TestThePersonKeysRoute:
    def test_a_signed_out_request_is_refused_and_names_no_key(self, skat, table_id):
        answer = read_person_keys(skat, FETCH, table_id)

        assert answer.status_code == 401
        assert not KEY_PATTERN.search(answer.text)

    def test_answers_the_version_and_the_key_of_each_seated_account_by_seat(self, skat, felix, table_id):
        headers, account = felix
        other_headers, other_account = skat.member()
        skat.sit(other_headers, table_id, 3)

        answer = read_person_keys(skat, headers, table_id)

        body = answer.json()
        assert answer.status_code == 200
        assert body["version"] == skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers).json()["version"]
        assert [(entry["seat"], entry["key"]) for entry in body["keys"]] == [
            (1, person_key(TEST_ISSUER, account.id, table_id)),
            (3, person_key(TEST_ISSUER, other_account.id, table_id)),
        ]

    def test_a_free_chair_has_no_key_and_the_answer_names_no_account(self, skat, felix, table_id):
        headers, account = felix

        answer = read_person_keys(skat, headers, table_id)

        assert [entry["seat"] for entry in answer.json()["keys"]] == [1]
        assert account.id not in answer.text

    def test_the_same_account_has_another_key_at_another_table(self, skat, felix, table_id):
        headers, _account = felix
        other_table = skat.create(headers, command_id="command-0002").json()["id"]

        keys = [read_person_keys(skat, headers, table).json()["keys"][0]["key"] for table in (table_id, other_table)]

        assert keys[0] != keys[1]

    def test_an_onlooker_who_holds_no_chair_reads_the_same_keys(self, skat, felix, table_id):
        onlooker_headers, _account = skat.member()

        seated = read_person_keys(skat, felix[0], table_id).json()
        onlooking = read_person_keys(skat, onlooker_headers, table_id).json()

        assert onlooking == seated

    def test_a_chair_freed_leaves_no_key_and_a_newer_version(self, skat, felix, table_id):
        headers, _account = felix
        other_headers, _other = skat.member()
        skat.sit(other_headers, table_id, 2)
        before = read_person_keys(skat, headers, table_id).json()

        skat.stand(other_headers, table_id)
        after = read_person_keys(skat, headers, table_id).json()

        assert [entry["seat"] for entry in after["keys"]] == [1]
        assert after["version"] > before["version"]

    @pytest.mark.parametrize("table", ["not-a-table", "00112233445566778899aabbccddeeff"])
    def test_an_unknown_table_answers_not_found(self, skat, felix, table):
        assert read_person_keys(skat, felix[0], table).status_code == 404

    def test_the_agents_bearer_is_refused(self, skat, issuer, table_id):
        token = issuer.agent_token(SUBJECT)

        refused = skat.client.get(person_keys_path(table_id), headers={"authorization": f"Bearer {token}", **FETCH})

        assert refused.status_code == HTTPStatus.UNAUTHORIZED

    def test_the_route_is_no_agent_tool(self, skat):
        operation = skat.app.openapi()["paths"][f"{TABLES_PATH}/{{table_id}}{TABLE_PERSON_KEYS_SUFFIX}"]["get"]

        assert isinstance(read_decision(operation[AGENT_TOOL_EXTENSION]), ToolExclusion)
