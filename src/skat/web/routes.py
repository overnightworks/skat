from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from skat.web.constants import (
    APP_ASSET_PATH,
    HEALTH_PATH,
    HOME_PATH,
    IMMUTABLE_ASSET_CACHE_CONTROL,
    IMMUTABLE_ASSET_DIRECTORY,
)

if TYPE_CHECKING:
    import os

    from starlette.types import Scope

    from skat.web.page_build import BuiltPage, PageBuild

READ_METHODS = ["GET", "HEAD"]


def built_page_response(page: BuiltPage, status_code: int = 200) -> Response:
    return Response(page.content, status_code=status_code, media_type="text/html", headers={"ETag": page.etag})


class _PageBuildFiles(StaticFiles):
    """The page build's files, with the immutable ones marked so for the browser, a 304 included."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory=directory)
        self._immutable_directory = (directory / IMMUTABLE_ASSET_DIRECTORY).resolve()

    def file_response(
        self, full_path: str | os.PathLike[str], stat_result: os.stat_result, scope: Scope, status_code: int = 200
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        if Path(full_path).is_relative_to(self._immutable_directory):
            response.headers["Cache-Control"] = IMMUTABLE_ASSET_CACHE_CONTROL
        return response


def create_router(page_build: PageBuild) -> APIRouter:
    router = APIRouter()

    @router.api_route(HEALTH_PATH, methods=READ_METHODS)
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @router.api_route(HOME_PATH, methods=READ_METHODS)
    def home_page() -> Response:
        return built_page_response(page_build.shell)

    router.mount(APP_ASSET_PATH, _PageBuildFiles(page_build.app_directory), name="page-build")
    return router
