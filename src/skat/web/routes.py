from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from skat.web.constants import (
    APP_ASSET_PATH,
    HEALTH_PATH,
    HOME_PATH,
    IMMUTABLE_ASSET_CACHE_CONTROL,
    IMMUTABLE_ASSET_PATH_RULES,
)
from skat.web.languages import LANGUAGE_VARY, language_of_request
from skat.web.mcp import Exclusion, excluded

if TYPE_CHECKING:
    import os

    from starlette.types import Scope
    from webauth.config import WebAuthConfig
    from webauth.ports import SessionRecordStore

    from skat.web.page_build import BuiltPage, PageBuild

READ_METHODS = ["GET", "HEAD"]


def built_page_response(page: BuiltPage, status_code: int = 200) -> Response:
    return Response(page.content, status_code=status_code, media_type="text/html", headers={"ETag": page.etag})


class _PageBuildFiles(StaticFiles):
    """The page build's files, with the immutable ones marked so for the browser, a 304 included."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory=directory)
        self._directory = directory.resolve()

    def file_response(
        self, full_path: str | os.PathLike[str], stat_result: os.stat_result, scope: Scope, status_code: int = 200
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        served_path = f"{APP_ASSET_PATH}/{Path(full_path).resolve().relative_to(self._directory).as_posix()}"
        if IMMUTABLE_ASSET_PATH_RULES.matches(served_path):
            response.headers["Cache-Control"] = IMMUTABLE_ASSET_CACHE_CONTROL
        return response


def create_router(page_build: PageBuild, sessions: SessionRecordStore, web_auth: WebAuthConfig) -> APIRouter:
    router = APIRouter()

    @router.api_route(HEALTH_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.READINESS_PROBE))
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @router.api_route(HOME_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE))
    def home_page(request: Request) -> Response:
        response = built_page_response(
            page_build.shell_in(language_of_request(request, sessions=sessions, config=web_auth))
        )
        response.headers["Vary"] = LANGUAGE_VARY
        return response

    router.mount(APP_ASSET_PATH, _PageBuildFiles(page_build.app_directory), name="page-build")
    return router
