import pytest
from playwright.sync_api import expect

from tests.e2e.support.tables import open_new_table, sit_in, watch

pytestmark = pytest.mark.e2e


def test_forced_failure(open_person, e2e_server):
    anna = open_person(username="anna")
    path = open_new_table(anna, e2e_server)
    viewer = open_person()
    watch(viewer, e2e_server, path)
    sit_in(viewer, 2)
    viewer.close()
    expect(anna.locator(".watchers span")).to_have_text("7", timeout=1500)
