import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skat.web.constants import APP_ASSET_PATH, HEALTH_PATH, HOME_PATH
from skat.web.routes import create_router
from skat.web.sign_in import build_sign_in_configs
from tests.support.in_memory_stores import in_memory_stores
from tests.support.page_build import fixture_page_build


@pytest.fixture
def client(sign_in_settings):
    application = FastAPI()
    sessions = in_memory_stores().sessions
    web_auth = build_sign_in_configs(sign_in_settings().settings).web_auth
    application.include_router(create_router(fixture_page_build(), sessions, web_auth))
    return TestClient(application)


class TestHealthEndpoint:
    def test_returns_ok_status(self, client):
        response = client.get(HEALTH_PATH)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


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
