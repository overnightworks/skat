from fastapi.testclient import TestClient
from webauth.config import installed_web_auth_config

from skat.host.app import create_app
from skat.table.service import TableService
from skat.web.stores import SignInStores
from skat.web.tables import TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.support.page_build import fixture_page_build
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, new_account, seed_member

FETCH = {"accept": "application/json"}
NAVIGATION = {"accept": "text/html"}
UNKNOWN_ID = "0" * 32


class Skat:
    def __init__(self, sign_in_settings, **app_options):
        self.stores = SignInStores.in_memory()
        self.store = FakeTableStore()
        self.app = create_app(
            sign_in_settings().settings,
            page_build=fixture_page_build(),
            tables=TableService(self.store),
            stores=self.stores,
            **app_options,
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
