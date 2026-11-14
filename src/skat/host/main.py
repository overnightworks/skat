import argparse
from typing import TYPE_CHECKING, TypedDict, Unpack

import uvicorn
from sqlalchemy.engine import make_url

from skat.host.app import create_app
from skat.store.migrate import ReadinessProbe, create_store_engine, database_health, migrate, require_head
from skat.store.rule_sets import PostgresRuleSets
from skat.store.tables import PostgresTableTransactions
from skat.table.rule_sets import RuleSetService
from skat.table.service import TableService
from skat.web.constants import GRACEFUL_SHUTDOWN_SECONDS, UVICORN_LOG_LEVEL
from skat.web.page_build import BUILD_DIRECTORY, PageBuild
from skat.web.secret_files import read_secret_file
from skat.web.settings import DatabaseSettings, ServerSettings

if TYPE_CHECKING:
    import socket
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from fastapi import FastAPI
    from sqlalchemy import Engine


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


class StreamsEndingServer(uvicorn.Server):
    """uvicorn's server that ends every open table stream before it waits for connections to close.

    uvicorn runs the app's lifespan shutdown only after that wait, and an open stream never finishes by
    itself, so the wait would run out and cancel each stream with an error in the log.
    """

    def __init__(self, config: uvicorn.Config, stop_streams: Callable[[], None]) -> None:
        super().__init__(config)
        self._stop_streams = stop_streams

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        self._stop_streams()
        await super().shutdown(sockets)


def streams_ending_server(app: FastAPI, **options: Unpack[UvicornOptions]) -> StreamsEndingServer:
    return StreamsEndingServer(uvicorn.Config(app, **options), app.state.stop_streams)


def serve(app: FastAPI, **options: Unpack[UvicornOptions]) -> None:
    streams_ending_server(app, **options).run()  # pragma: no cover - blocks until a signal stops the server


def create_database_engine(settings: DatabaseSettings) -> Engine:
    """The store's engine on the database URL with the password from its file set into it."""
    password = read_secret_file(settings.database_password_file, "database_password_file")
    url = make_url(settings.database_url).set(password=password.get_secret_value())
    # The store takes a string; the rendered URL goes nowhere but into the engine.
    return create_store_engine(url.render_as_string(hide_password=False))


def command_line_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skat")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="start the server; it refuses a database that is not at the newest migration")
    commands.add_parser("migrate", help="bring the database to the newest migration")
    return parser


def main(
    arguments: Sequence[str] | None = None,
    *,
    run_server: Callable[..., None] = serve,
    build_directory: Path = BUILD_DIRECTORY,
) -> None:
    command = command_line_parser().parse_args(arguments).command
    # The required settings come from the environment, which the type checker cannot see.
    if command == "migrate":
        database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
        migrate(create_database_engine(database), operator_account_id=database.operator_account_id)
        return
    settings = ServerSettings()  # pyright: ignore[reportCallIssue]
    engine = create_database_engine(settings)
    require_head(engine)
    app = create_app(
        settings,
        page_build=PageBuild.load(build_directory),
        tables=TableService(PostgresTableTransactions(engine)),
        rule_sets=RuleSetService(PostgresRuleSets(engine)),
        database_ready=ReadinessProbe(lambda: database_health(engine)),
    )
    run_server(app, **uvicorn_options(settings))


if __name__ == "__main__":
    main()
