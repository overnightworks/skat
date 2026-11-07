import pytest
from fastapi.testclient import TestClient
from webauth.config import installed_web_auth_config

from skat.host.app import create_app
from skat.table.service import TableService
from skat.web.stores import SignInStores
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.support.page_build import FIXTURE_DIRECTORY, fixture_page_build
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, new_account, seed_member

FETCH = {"accept": "application/json"}
NAVIGATION = {"accept": "text/html"}
UNKNOWN_ID = "0" * 32


class Skat:
    def __init__(self, sign_in_settings):
        self.stores = SignInStores.in_memory()
        self.store = FakeTableStore()
        self.app = create_app(
            sign_in_settings().settings,
            page_build=fixture_page_build(),
            tables=TableService(self.store),
            stores=self.stores,
        )
        self.config = installed_web_auth_config(self.app)
        self.client = TestClient(self.app, base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False)

    def member(self):
        member = seed_member(self.stores, self.config, account=new_account(self.stores, self.config))
        return {"cookie": cookie_header(member.set_cookie_headers), **FETCH}, member.account

    def create(self, headers, command_id="command-0001", **extra):
        return self.client.post(
            TABLES_PATH, json={"command_id": command_id, **extra}, headers={"origin": TEST_PUBLIC_ORIGIN, **headers}
        )


@pytest.fixture
def skat(sign_in_settings):
    return Skat(sign_in_settings)


class TestCreateTable:
    def test_seats_the_signed_in_opener_in_chair_one_and_answers_with_the_table(self, skat):
        headers, account = skat.member()

        answer = skat.create(headers)

        assert answer.status_code == 200
        assert answer.headers["cache-control"] == "no-store"
        assert [(c["seat"], c["occupant_name"], c["is_mine"]) for c in answer.json()["chairs"]] == [
            (1, account.username, True),
            (2, None, False),
            (3, None, False),
        ]

    def test_answers_a_retry_with_the_same_table(self, skat):
        headers, _ = skat.member()

        assert skat.create(headers).json() == skat.create(headers).json()
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
        assert [(c["occupant_name"], c["is_mine"]) for c in answer.json()["chairs"]] == [
            (opener.username, False),
            (None, False),
            (None, False),
        ]

    def test_shows_the_opener_the_same_table_after_a_reload(self, skat):
        headers, _ = skat.member()
        created = skat.create(headers).json()

        assert skat.client.get(f"{TABLES_PATH}/{created['id']}", headers=headers).json() == created

    @pytest.mark.parametrize("table_id", [UNKNOWN_ID, "not-an-id", "%27%3B--", "A" * 32])
    def test_an_unknown_or_malformed_id_is_not_found_without_a_database_message(self, skat, table_id):
        headers, _ = skat.member()

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers)

        assert (answer.status_code, answer.json()) == (404, {"detail": "table not found"})

    def test_signed_out_gets_no_table_data(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=FETCH)

        assert answer.status_code == 401
        assert table_id not in answer.text


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
