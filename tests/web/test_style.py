import pytest

from skat.table.records import Refusal, TableStyle
from skat.web.style import TABLE_STYLE_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import seated_three
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.presence import view_of_version
from tests.web.support.skat import streams_of

STYLE_COMMAND_ID = "style-0001"


def choose(server, headers, table_id, style, *, command_id=STYLE_COMMAND_ID, **extra):
    answer = server.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_STYLE_SUFFIX}",
        json={"command_id": command_id, "style": style, **extra},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )
    server.client.cookies.clear()
    return answer


@pytest.fixture
def table(server):
    """Anna, Ben and Cleo in seats 1 to 3, the fourth member Dora watching; returns the id and all four."""
    table_id, people = seated_three(server)
    server.client.cookies.clear()
    return table_id, people


class TestChoosingTheTablesStyle:
    def test_a_table_reads_klassik_until_a_member_chooses(self, server, table):
        table_id, people = table

        read = server.client.get(f"{TABLES_PATH}/{table_id}", headers=people[3][0])

        assert read.json()["style"] == TableStyle.KLASSIK

    def test_a_seated_member_chooses_and_every_page_at_the_table_reads_it_with_one_new_version(self, server, table):
        table_id, people = table
        before = server.store.tables[table_id]
        with streams_of(server, table_id, people) as streams:
            answer = choose(server, people[1][0], table_id, TableStyle.STRANDBAR)

            assert answer.status_code == 200, answer.text
            assert answer.headers["cache-control"] == "no-store"
            assert answer.json()["style"] == TableStyle.STRANDBAR
            for messages in streams:
                view = view_of_version(messages, before.version + 1)
                assert (view["style"], view["version"]) == (TableStyle.STRANDBAR, before.version + 1)

    def test_a_page_that_loads_afterwards_reads_the_style_too(self, server, table):
        table_id, people = table
        choose(server, people[2][0], table_id, TableStyle.STRANDBAR)

        read = server.client.get(f"{TABLES_PATH}/{table_id}", headers=people[3][0])

        assert read.json()["style"] == TableStyle.STRANDBAR

    def test_a_member_chooses_klassik_again(self, server, table):
        table_id, people = table
        choose(server, people[0][0], table_id, TableStyle.STRANDBAR)

        answer = choose(server, people[1][0], table_id, TableStyle.KLASSIK, command_id="style-0002")

        assert answer.json()["style"] == TableStyle.KLASSIK

    def test_a_watcher_is_refused_and_the_table_stays_as_it_was(self, server, table):
        table_id, people = table
        before = server.store.tables[table_id]

        answer = choose(server, people[3][0], table_id, TableStyle.STRANDBAR)

        assert (answer.status_code, answer.json()["reason"]) == (409, Refusal.NOT_SEATED)
        assert server.store.tables[table_id] == before

    def test_the_style_already_chosen_is_accepted_and_changes_nothing(self, server, table):
        table_id, people = table
        choose(server, people[0][0], table_id, TableStyle.STRANDBAR)
        chosen = server.store.tables[table_id]

        again = choose(server, people[1][0], table_id, TableStyle.STRANDBAR, command_id="style-other-tab")

        assert again.status_code == 200, again.text
        assert server.store.tables[table_id] == chosen

    def test_a_retry_with_the_same_command_answers_the_same_and_writes_once(self, server, table):
        table_id, people = table
        first = choose(server, people[0][0], table_id, TableStyle.STRANDBAR)
        version = server.store.tables[table_id].version

        retry = choose(server, people[0][0], table_id, TableStyle.STRANDBAR)

        assert retry.json() == first.json()
        assert server.store.tables[table_id].version == version

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"style": "pokerkeller"}, id="an-unknown-style"),
            pytest.param({"style": None}, id="no-style"),
            pytest.param({"style": "strandbar", "seat": 1}, id="names-a-chair"),
        ],
    )
    def test_refuses_a_malformed_request_and_writes_nothing(self, server, table, body):
        table_id, people = table
        before = server.store.tables[table_id]

        answer = server.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_STYLE_SUFFIX}",
            json={"command_id": STYLE_COMMAND_ID, **body},
            headers={"origin": TEST_PUBLIC_ORIGIN, **people[0][0]},
        )

        assert answer.status_code == 422
        assert server.store.tables[table_id] == before

    def test_a_signed_out_request_changes_nothing(self, server, table):
        table_id, _ = table
        before = server.store.tables[table_id]

        answer = choose(server, {}, table_id, TableStyle.STRANDBAR)

        assert answer.status_code == 401
        assert server.store.tables[table_id] == before
