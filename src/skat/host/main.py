import argparse
from typing import TYPE_CHECKING, TypedDict

import uvicorn

from skat.host.app import create_app
from skat.web.constants import UVICORN_LOG_LEVEL
from skat.web.page_build import BUILD_DIRECTORY, PageBuild
from skat.web.settings import ServerSettings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path


class UvicornOptions(TypedDict):
    host: str
    port: int
    access_log: bool
    proxy_headers: bool
    log_level: str


def uvicorn_options(settings: ServerSettings) -> UvicornOptions:
    return UvicornOptions(
        host=settings.host,
        port=settings.port,
        access_log=False,
        proxy_headers=False,
        log_level=UVICORN_LOG_LEVEL,
    )


def command_line_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skat")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="start the server")
    return parser


def main(
    arguments: Sequence[str] | None = None,
    *,
    run_server: Callable[..., None] = uvicorn.run,
    build_directory: Path = BUILD_DIRECTORY,
) -> None:
    command_line_parser().parse_args(arguments)
    # The required settings come from the environment, which the type checker cannot see.
    settings = ServerSettings()  # pyright: ignore[reportCallIssue]
    app = create_app(settings, page_build=PageBuild.load(build_directory))
    run_server(app, **uvicorn_options(settings))


if __name__ == "__main__":
    main()
