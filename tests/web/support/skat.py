from dataclasses import replace

from fastapi.testclient import TestClient
from webauth.config import install_web_auth_config, installed_web_auth_config

from skat.host.app import create_app
from skat.table.service import TableService
from skat.web.stores import SignInStores
from skat.web.tables import TABLE_SIT_SUFFIX, TABLE_STAND_SUFFIX, TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.support.page_build import fixture_page_build
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.support.signed_in import cookie_header, new_account, seed_member

FETCH = {"accept": "application/json"}
NAVIGATION = {"accept": "text/html"}
UNKNOWN_ID = "0" * 32


class Skat:
    def __init__(self, sign_in_settings, store=None, **app_options):
        self.stores = SignInStores.in_memory()
        self.store = store if store is not None else FakeTableStore()
        self.app = create_app(
            sign_in_settings().settings,
            page_build=fixture_page_build(),
            tables=TableService(self.store),
            stores=self.stores,
            **app_options,
        )
        self.config = installed_web_auth_config(self.app)
        self.client = TestClient(self.app, base_url=TEST_PUBLIC_ORIGIN, follow_redirects=False)

    def run_on_clock(self, now):
        """Reads webauth's time from `now[0]`, a list the test moves; call before the first member is seeded."""
        self.config = replace(self.config, wall_clock=lambda: now[0])
        install_web_auth_config(self.app, self.config)

    def member(self, **seed_options):
        member = seed_member(self.stores, self.config, account=new_account(self.stores, self.config), **seed_options)
        return {"cookie": cookie_header(member.set_cookie_headers), **FETCH}, member.account

    def create(self, headers, command_id="command-0001", **extra):
        return self.client.post(
            TABLES_PATH, json={"command_id": command_id, **extra}, headers={"origin": TEST_PUBLIC_ORIGIN, **headers}
        )

    def sit(self, headers, table_id, seat, command_id="command-sit", **extra):
        return self.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_SIT_SUFFIX}",
            json={"command_id": command_id, "seat": seat, **extra},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

    def stand(self, headers, table_id, command_id="command-stand", **extra):
        return self.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_STAND_SUFFIX}",
            json={"command_id": command_id, **extra},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )
