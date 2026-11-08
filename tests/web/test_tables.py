import asyncio

import pytest

from skat.table.service import TableService
from skat.web.presence import Presence
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH, create_tables_router
from tests.support.faulty_tables import FaultyTableTransactions
from tests.support.page_build import FIXTURE_DIRECTORY, fixture_page_build
from tests.web.support.skat import FETCH, NAVIGATION, UNKNOWN_ID


class TestCreateTable:
    def test_seats_the_signed_in_opener_in_chair_one_and_answers_with_the_table(self, skat):
        headers, account = skat.member()

        answer = skat.create(headers)

        assert answer.status_code == 200
        assert answer.headers["cache-control"] == "no-store"
        chairs = [(c["seat"], c["occupant_name"], c["is_mine"]) for c in answer.json()["chairs"]]
        assert chairs == [
            (1, account.username, True),
            (2, None, False),
            (3, None, False),
        ]

    def test_answers_a_retry_with_the_same_table(self, skat):
        headers, _ = skat.member()

        first = skat.create(headers).json()

        assert skat.create(headers).json() == first
        assert len(skat.store.tables) == 1

    def test_refuses_a_command_id_that_comes_back_with_another_request(self, skat):
        headers, account = skat.member()
        skat.create(headers)
        receipt = skat.store.receipts[(account.id, "command-0001")]
        skat.store.receipts[(account.id, "command-0001")] = type(receipt)(
            receipt.account_id, receipt.command_id, "another-command", receipt.payload, receipt.table_id
        )

        assert skat.create(headers).status_code == 409
        assert len(skat.store.tables) == 1

    @pytest.mark.parametrize("extra", [{"chair": 2}, {"account_id": "someone-else"}, {"seat": 3, "username": "x"}])
    def test_refuses_a_request_that_names_a_chair_or_an_account_and_writes_nothing(self, skat, extra):
        headers, _ = skat.member()

        assert skat.create(headers, **extra).status_code == 422
        assert skat.store.tables == {}

    @pytest.mark.parametrize("command_id", ["", "short", "has space in it", "x" * 65])
    def test_refuses_a_malformed_command_id(self, skat, command_id):
        headers, _ = skat.member()

        assert skat.create(headers, command_id=command_id).status_code == 422
        assert skat.store.tables == {}

    def test_signed_out_writes_nothing_and_shows_no_table(self, skat):
        answer = skat.create(FETCH)

        assert answer.status_code == 401
        assert skat.store.tables == {}


class TestReadTable:
    def test_shows_another_member_the_table_with_the_opener_in_chair_one_and_no_chair_of_their_own(self, skat):
        opener_headers, opener = skat.member()
        table_id = skat.create(opener_headers).json()["id"]
        visitor_headers, _ = skat.member()

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=visitor_headers)

        assert answer.status_code == 200
        assert answer.headers["cache-control"] == "no-store"
        chairs = [(c["occupant_name"], c["is_mine"]) for c in answer.json()["chairs"]]
        assert chairs == [
            (opener.username, False),
            (None, False),
            (None, False),
        ]

    def test_shows_the_opener_the_same_table_after_a_reload(self, skat):
        headers, _ = skat.member()
        created = skat.create(headers).json()

        assert skat.client.get(f"{TABLES_PATH}/{created['id']}", headers=headers).json() == created

    def test_reads_who_is_connected_on_the_event_loop_that_owns_the_presence(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]
        threads_with_a_loop = []

        class ProbingPresence(Presence):
            def connected(self, read_table_id):
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    threads_with_a_loop.append(False)
                else:
                    threads_with_a_loop.append(True)
                return super().connected(read_table_id)

        skat.app.include_router(create_tables_router(TableService(skat.store), fixture_page_build(), ProbingPresence()))
        # The probing router goes first so that it, not the composed one, answers the read.
        skat.app.router.routes.insert(0, skat.app.router.routes.pop())

        skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers)

        assert threads_with_a_loop == [True]

    @pytest.mark.parametrize("table_id", [UNKNOWN_ID, "not-an-id", "%27%3B--", "A" * 32])
    def test_an_unknown_or_malformed_id_is_not_found_without_a_database_message(self, skat, table_id):
        headers, _ = skat.member()

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers)

        assert answer.status_code == 404
        assert answer.json() == {"detail": "table not found"}

    def test_signed_out_gets_no_table_data(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=FETCH)

        assert answer.status_code == 401
        assert table_id not in answer.text

    def test_shows_a_seated_member_without_a_stream_as_away_to_every_other_viewer_and_names_no_account(self, skat):
        headers, account = skat.member()
        table_id = skat.create(headers).json()["id"]
        other_headers, other = skat.member()

        answers = [
            skat.client.get(f"{TABLES_PATH}/{table_id}", headers=viewer_headers)
            for viewer_headers in (other_headers, headers)
        ]

        assert [[c["is_away"] for c in answer.json()["chairs"]] for answer in answers] == [
            [True, False, False],
            [False, False, False],
        ]
        assert all(account.id not in answer.text and other.id not in answer.text for answer in answers)


class TestTablePage:
    def test_serves_the_page_shell_to_a_member_for_any_id(self, skat):
        headers, _ = skat.member()

        for table_id in (UNKNOWN_ID, "anything"):
            answer = skat.client.get(f"{TABLE_PAGE_PREFIX}{table_id}", headers={**headers, **NAVIGATION})
            assert answer.status_code == 200
            assert answer.content == (FIXTURE_DIRECTORY / "index.html").read_bytes()
            assert answer.headers["cache-control"] == "no-cache"

    def test_sends_a_signed_out_visitor_to_the_sign_in_page(self, skat):
        answer = skat.client.get(f"{TABLE_PAGE_PREFIX}{UNKNOWN_ID}", headers=NAVIGATION)

        assert answer.status_code == 302


class RecordingPresence(Presence):
    def __init__(self):
        super().__init__()
        self.woken = []

    def wake_table(self, table_id):
        self.woken.append(table_id)
        super().wake_table(table_id)


def answering_first(skat, tables, presence):
    """Route requests through a tables router that has this service and presence, ahead of the composed one."""
    skat.app.include_router(create_tables_router(tables, fixture_page_build(), presence))
    skat.app.router.routes.insert(0, skat.app.router.routes.pop())


@pytest.fixture
def table(skat):
    headers, owner = skat.member()
    return skat.create(headers).json()["id"], owner


class TestSitDown:
    def test_seats_the_member_in_the_chair_and_answers_with_the_table_they_see(self, skat, table):
        table_id, owner = table
        headers, account = skat.member()

        answer = skat.sit(headers, table_id, 2)

        assert answer.status_code == 200
        assert answer.headers["cache-control"] == "no-store"
        chairs = [(c["occupant_name"], c["is_mine"]) for c in answer.json()["chairs"]]
        assert chairs == [
            (owner.username, False),
            (account.username, True),
            (None, False),
        ]

    @pytest.mark.parametrize("action", ["sit", "stand"])
    def test_answers_an_occupant_with_a_connected_stream_as_present(self, skat, table, action):
        table_id, owner = table
        headers, _ = skat.member()
        presence = Presence()
        answering_first(skat, TableService(skat.store), presence)
        presence.subscribe(table_id, owner.id, lambda: None)
        if action == "stand":
            skat.sit(headers, table_id, 2)

        answer = getattr(skat, action)(headers, table_id, *([2] if action == "sit" else []), command_id="command-act")

        assert answer.json()["chairs"][0]["is_away"] is False

    def test_the_second_one_for_a_chair_is_told_who_got_it(self, skat, table):
        table_id, owner = table
        headers, _ = skat.member()

        answer = skat.sit(headers, table_id, 1)

        assert answer.status_code == 409
        assert answer.json() == {"reason": "seat-taken", "holder_name": owner.username}

    def test_a_seated_member_asking_for_a_second_chair_is_refused_and_keeps_the_first(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)

        answer = skat.sit(headers, table_id, 3, command_id="command-second")

        assert answer.status_code == 409
        assert answer.json()["reason"] == "already-seated"
        mine = [c["is_mine"] for c in skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers).json()["chairs"]]
        assert mine == [False, True, False]

    def test_a_retry_with_the_same_command_id_answers_with_the_first_outcome_and_writes_nothing_more(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        first = skat.sit(headers, table_id, 2).json()
        written = dict(skat.store.tables)

        assert skat.sit(headers, table_id, 2).json() == first
        assert skat.store.tables == written

    def test_refuses_a_command_id_that_comes_back_with_another_chair(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)

        assert skat.sit(headers, table_id, 3).status_code == 409
        assert skat.sit(headers, table_id, 3).json() == {"detail": "command id reused with another request"}

    @pytest.mark.parametrize("seat", [0, 4, -1, "two", None, "2", 2.0, True])
    def test_refuses_a_seat_that_is_no_whole_chair_number_and_writes_nothing(self, skat, table, seat):
        table_id, _ = table
        headers, _ = skat.member()
        before = dict(skat.store.tables)

        assert skat.sit(headers, table_id, seat).status_code == 422
        assert skat.store.tables == before

    @pytest.mark.parametrize("extra", [{"account_id": "someone-else"}, {"username": "x"}])
    def test_refuses_a_request_that_names_an_account(self, skat, table, extra):
        table_id, _ = table
        headers, _ = skat.member()

        assert skat.sit(headers, table_id, 2, **extra).status_code == 422

    def test_signed_out_writes_nothing(self, skat, table):
        table_id, _ = table
        before = dict(skat.store.tables)

        assert skat.sit(FETCH, table_id, 2).status_code == 401
        assert skat.store.tables == before

    @pytest.mark.parametrize("table_id", [UNKNOWN_ID, "not-an-id", "A" * 32])
    def test_an_unknown_or_malformed_table_is_not_found_and_writes_nothing(self, skat, table_id):
        headers, _ = skat.member()

        answer = skat.sit(headers, table_id, 1)

        assert answer.status_code == 404
        assert answer.json() == {"detail": "table not found"}
        assert skat.store.tables == {}
        assert skat.store.receipts == {}

    def test_wakes_every_stream_of_the_table_after_the_commit(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        presence = RecordingPresence()
        answering_first(skat, TableService(skat.store), presence)

        skat.sit(headers, table_id, 2)

        assert presence.woken == [table_id]

    def test_a_refusal_changes_nothing_and_wakes_nobody(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        presence = RecordingPresence()
        answering_first(skat, TableService(skat.store), presence)

        skat.sit(headers, table_id, 1)

        assert presence.woken == []

    def test_a_failing_transaction_writes_and_publishes_nothing(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        presence = RecordingPresence()

        faulty = TableService(FaultyTableTransactions(skat.store, receipt_failure=RuntimeError("connection lost")))
        answering_first(skat, faulty, presence)
        before = (dict(skat.store.tables), dict(skat.store.receipts))

        with pytest.raises(RuntimeError, match="connection lost"):
            skat.sit(headers, table_id, 2)

        assert presence.woken == []
        state = (skat.store.tables, skat.store.receipts)
        assert state == before


class TestStandUp:
    def test_frees_the_own_chair_keeping_every_number(self, skat, table):
        table_id, owner = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 3)

        answer = skat.stand(headers, table_id)

        assert answer.status_code == 200
        chairs = [(c["seat"], c["occupant_name"], c["is_mine"]) for c in answer.json()["chairs"]]
        assert chairs == [
            (1, owner.username, False),
            (2, None, False),
            (3, None, False),
        ]

    def test_a_member_without_a_chair_is_refused_and_nothing_changes(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        before = dict(skat.store.tables)

        answer = skat.stand(headers, table_id)

        assert answer.status_code == 409
        assert answer.json() == {"reason": "not-seated", "holder_name": None}
        assert skat.store.tables == before

    def test_a_retry_answers_with_the_first_outcome(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)
        first = skat.stand(headers, table_id).json()

        assert skat.stand(headers, table_id).json() == first

    def test_refuses_a_command_id_that_a_sit_already_used(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)

        assert skat.stand(headers, table_id, command_id="command-sit").status_code == 409

    def test_signed_out_writes_nothing(self, skat, table):
        table_id, _ = table
        before = (dict(skat.store.tables), dict(skat.store.receipts))

        assert skat.stand(FETCH, table_id).status_code == 401
        state = (skat.store.tables, skat.store.receipts)
        assert state == before

    def test_an_unknown_table_is_not_found(self, skat):
        headers, _ = skat.member()

        assert skat.stand(headers, UNKNOWN_ID).status_code == 404

    def test_wakes_every_stream_of_the_table_after_the_commit(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)
        presence = RecordingPresence()
        answering_first(skat, TableService(skat.store), presence)

        skat.stand(headers, table_id, command_id="command-stand")

        assert presence.woken == [table_id]
