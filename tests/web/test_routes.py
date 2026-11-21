from typing import ClassVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from skat.web.constants import APP_ASSET_PATH, HEALTH_PATH, HOME_PATH
from skat.web.routes import create_router, unknown_address_handler
from skat.web.sign_in import build_sign_in_configs
from tests.support.in_memory_stores import in_memory_stores, in_process_rate_limits
from tests.support.page_build import fixture_page_build


class Database:
    """The readiness of the database the route asks, set by the test."""

    def __init__(self) -> None:
        self.ready = True

    async def __call__(self) -> bool:
        return self.ready


@pytest.fixture
def database() -> Database:
    return Database()


@pytest.fixture
def client(sign_in_settings, database):
    application = FastAPI()
    sessions = in_memory_stores().sessions
    web_auth = build_sign_in_configs(sign_in_settings().settings, in_process_rate_limits()).web_auth
    page_build = fixture_page_build()
    application.include_router(create_router(page_build, sessions, web_auth, database))
    application.add_exception_handler(HTTPException, unknown_address_handler(page_build, sessions, web_auth))
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


class TestUnknownAddress:
    HTML: ClassVar[dict[str, str]] = {"Accept": "text/html,application/xhtml+xml"}

    @pytest.mark.parametrize("method", ["get", "head"])
    def test_a_page_request_gets_the_shell_with_404(self, client, method):
        response = getattr(client, method)("/no-such-page", headers=self.HTML)
        shell = client.get(HOME_PATH).content

        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["vary"] == "Accept-Language, Cookie"
        if method == "get":
            assert response.content == shell

    def test_the_shell_comes_in_the_language_of_the_request(self, client):
        german = client.get("/no-such-page", headers={**self.HTML, "Accept-Language": "de"})
        english = client.get("/no-such-page", headers={**self.HTML, "Accept-Language": "en"})

        assert b'lang="de"' in german.content
        assert b'lang="en"' in english.content

    @pytest.mark.parametrize("path", ["/api/no-such-thing", "/mcp/x", "/health/x", f"{APP_ASSET_PATH}/no-such-file"])
    def test_a_machine_path_keeps_its_plain_404(self, client, path):
        response = client.get(path, headers=self.HTML)

        assert response.status_code == 404
        assert not response.headers["content-type"].startswith("text/html")

    def test_a_request_not_asking_for_a_page_keeps_the_json_404(self, client):
        response = client.get("/no-such-page", headers={"Accept": "application/json"})

        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}

    def test_a_post_keeps_its_405_or_404_answer_as_json(self, client):
        response = client.post("/no-such-page", headers=self.HTML)

        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
