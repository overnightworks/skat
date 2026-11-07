import argparse
from typing import TYPE_CHECKING, TypedDict

import uvicorn

from skat.host.app import create_app
from skat.store.migrate import create_store_engine, migrate, require_head
from skat.store.tables import PostgresTableTransactions
from skat.table.service import TableService
from skat.web.constants import GRACEFUL_SHUTDOWN_SECONDS, UVICORN_LOG_LEVEL
from skat.web.page_build import BUILD_DIRECTORY, PageBuild
from skat.web.secret_files import read_secret_file
from skat.web.settings import DatabaseSettings, ServerSettings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path


class UvicornOptions(TypedDict):
    host: str
    port: int
    access_log: bool
    proxy_headers: bool
    log_level: str
    timeout_graceful_shutdown: int


def uvicorn_options(settings: ServerSettings) -> UvicornOptions:
    return UvicornOptions(
        host=settings.host,
        port=settings.port,
        access_log=False,
        proxy_headers=False,
        log_level=UVICORN_LOG_LEVEL,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
    )


def command_line_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skat")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="start the server; it refuses a database that is not at the newest migration")
    commands.add_parser("migrate", help="bring the database to the newest migration")
    return parser


def main(
    arguments: Sequence[str] | None = None,
    *,
    run_server: Callable[..., None] = uvicorn.run,
    build_directory: Path = BUILD_DIRECTORY,
) -> None:
    command = command_line_parser().parse_args(arguments).command
    # The required settings come from the environment, which the type checker cannot see.
    if command == "migrate":
        database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
        migrate(
            create_store_engine(read_secret_file(database.database_url_file, "database_url_file").get_secret_value())
        )
        return
    settings = ServerSettings()  # pyright: ignore[reportCallIssue]
    engine = create_store_engine(read_secret_file(settings.database_url_file, "database_url_file").get_secret_value())
    require_head(engine)
    app = create_app(
        settings,
        page_build=PageBuild.load(build_directory),
        tables=TableService(PostgresTableTransactions(engine)),
    )
    run_server(app, **uvicorn_options(settings))


if __name__ == "__main__":
    main()
