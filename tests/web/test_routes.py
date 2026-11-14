import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skat.web.constants import APP_ASSET_PATH, HEALTH_PATH, HOME_PATH
from skat.web.routes import create_router
from skat.web.sign_in import build_sign_in_configs
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import fixture_page_build


class Database:
    """The readiness of the database the route asks, set by the test."""

    def __init__(self) -> None:
        self.ready = True
        self.asked = 0

    def __call__(self) -> bool:
        self.asked += 1
        return self.ready


@pytest.fixture
def database() -> Database:
    return Database()


@pytest.fixture
def client(sign_in_settings, database):
    application = FastAPI()
    sessions = in_memory_stores().sessions
    web_auth = build_sign_in_configs(sign_in_settings().settings).web_auth
    application.include_router(create_router(fixture_page_build(), sessions, web_auth, database))
    return TestClient(application)


class TestHealthEndpoint:
    def test_answers_200_while_the_database_is_ready(self, client):
        response = client.get(HEALTH_PATH)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_answers_503_with_nothing_but_the_status_while_the_database_is_not_ready(self, client, database):
        database.ready = False

        response = client.get(HEALTH_PATH)

        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}

    def test_follows_the_database_from_one_probe_to_the_next(self, client, database):
        answers = []
        for ready in (True, False, True):
            database.ready = ready
            answers.append(client.get(HEALTH_PATH).status_code)

        assert answers == [200, 503, 200]

    def test_a_head_probe_answers_503_while_the_database_is_not_ready(self, client, database):
        database.ready = False

        assert client.head(HEALTH_PATH).status_code == 503

    def test_no_other_route_asks_the_database(self, client, database):
        client.get(HOME_PATH)

        assert database.asked == 0


class TestHomePage:
    def test_answers_the_page_builds_shell_with_its_etag(self, client):
        response = client.get(HOME_PATH)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.content == fixture_page_build().shell_in("de").content
        assert response.headers["etag"] == fixture_page_build().shell_in("de").etag


class TestAppAssets:
    @pytest.mark.parametrize(("asset", "content_type"), [("immutable/x.js", "javascript"), ("version.json", "json")])
    def test_serves_the_build_files_under_the_app_path(self, client, asset, content_type):
        response = client.get(f"{APP_ASSET_PATH}/{asset}")
        assert response.status_code == 200
        assert content_type in response.headers["content-type"]


class TestHeadRequests:
    @pytest.mark.parametrize("path", [HOME_PATH, HEALTH_PATH])
    def test_head_answers_ok(self, client, path):
        assert client.head(path).status_code == 200
