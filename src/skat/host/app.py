import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

import structlog
from agents.mcp_server import ResourceChanges
from agents.member import LEASE_SECONDS
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from webauth.config import install_web_auth_config
from webauth.middleware import install_web_auth_middleware
from webauth.policies import (
    CacheControlRule,
    CspDirective,
    CsrfPolicy,
    PathRules,
    RateLimitPolicy,
    SecurityHeadersPolicy,
    default_content_security_policy,
)
from webauth.single_process_stores import SingleProcessStores

from skat.table.records import TableId
from skat.web.account import create_account_router
from skat.web.auction import create_auction_router
from skat.web.call import create_call_router
from skat.web.constants import (
    HEALTH_PATH,
    NO_CACHE_PATH_RULES,
    SIGN_IN_PATHS,
    STREAM_HEARTBEAT_SECONDS,
)
from skat.web.declaring import create_declaring_router
from skat.web.game_list import create_game_list_router
from skat.web.gate import session_gate
from skat.web.kontra import create_kontra_router
from skat.web.mcp import McpAccess, mount_mcp
from skat.web.member_place import AskClock, member_front, standing_signal, view_signal
from skat.web.paused import create_paused_router
from skat.web.playing import create_playing_router
from skat.web.presence import (
    NEXT_DEAL_PAUSE_SECONDS,
    AgentLease,
    ChairHold,
    EmptyTable,
    LoopScheduler,
    NextDeal,
    Presence,
    Scheduler,
)
from skat.web.pushing import create_pushing_router
from skat.web.ready import create_ready_router
from skat.web.routes import create_router
from skat.web.rule_sets import create_rule_sets_router
from skat.web.seating import create_seating_router
from skat.web.series_end import create_series_end_router
from skat.web.sign_in import (
    ISSUER_OVER_HTTPS,
    IssuerTransports,
    LoggingAuditSink,
    build_relying_party,
    build_sign_in_configs,
    install_sign_in,
)
from skat.web.streams import create_streams_router
from skat.web.tables import create_tables_router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Sequence
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

    from webauth.ports import SessionRecordStore

    from skat.table.rule_sets import RuleSetService
    from skat.table.service import TableService
    from skat.web.page_build import PageBuild
    from skat.web.settings import ServerSettings


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            # The default exception formatter switches to rich tracebacks with locals as soon as rich is installed.
            structlog.dev.ConsoleRenderer(exception_formatter=structlog.dev.plain_traceback),
        ],
    )


def _content_security_policy(page_build: PageBuild, call_origin: str | None) -> str:
    added_sources: dict[CspDirective, Sequence[str]] = {
        CspDirective.STYLE_SRC: ("'unsafe-hashes'", f"'{page_build.announcer_style_hash}'")
    }
    if call_origin is not None:
        added_sources[CspDirective.FRAME_ANCESTORS] = (call_origin,)
    return default_content_security_policy(page_build.script_hashes, added_sources=added_sources)


def _install_web_auth(
    app: FastAPI, sessions: SessionRecordStore, page_build: PageBuild, call_origin: str | None, mcp: McpAccess
) -> None:
    install_web_auth_middleware(
        app,
        sign_in_paths=SIGN_IN_PATHS,
        security_headers=SecurityHeadersPolicy(
            content_security_policy=_content_security_policy(page_build, call_origin),
            cache_control_rules=(CacheControlRule(paths=NO_CACHE_PATH_RULES, value="no-cache"),),
        ),
        csrf_origin=CsrfPolicy(),
        # /health is the edge's readiness probe.
        rate_limit=RateLimitPolicy(exempt=PathRules(exact=frozenset({HEALTH_PATH}))),
        bearer_gate=mcp.bearer_gate,
        session_gate=session_gate(sessions, mcp.public_rule),
    )


def _chair_hold(
    settings: ServerSettings, tables: TableService, clock: Callable[[], float], scheduler: Scheduler
) -> ChairHold:
    async def free_chair(table_id: str, account_id: str, due: AbstractContextManager[bool]) -> bool:
        return await run_in_threadpool(tables.free_chair, TableId(table_id), account_id, due)

    return ChairHold(settings.chair_hold_seconds, clock, scheduler, free_chair)


def _agent_lease(tables: TableService) -> AgentLease:
    async def seated_tables(account_id: str) -> list[str]:
        held = await run_in_threadpool(tables.tables_held_by, account_id)
        return [table_id.value for table_id in held]

    return AgentLease(LEASE_SECONDS, seated_tables)


def _next_deal(tables: TableService) -> NextDeal:
    async def deal(table_id: str, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        return await run_in_threadpool(tables.deal_next, TableId(table_id), connected_accounts)

    return NextDeal(NEXT_DEAL_PAUSE_SECONDS, deal)


def _empty_table(settings: ServerSettings, tables: TableService, asks: AskClock) -> EmptyTable:
    async def end(table_id: str, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        ended = await run_in_threadpool(
            tables.end_empty_table, TableId(table_id), connected_accounts, settings.empty_table_seconds
        )
        if ended:
            asks.drop(table_id)
        return ended

    async def note(table_id: str, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        ended = await run_in_threadpool(
            tables.note_presence, TableId(table_id), connected_accounts, settings.empty_table_seconds
        )
        if ended:
            asks.drop(table_id)
        return ended

    return EmptyTable(settings.empty_table_seconds, end, note)


def _presence(
    settings: ServerSettings,
    tables: TableService,
    clock: Callable[[], float],
    scheduler: Scheduler,
    asks: AskClock,
) -> Presence:
    return Presence(
        _chair_hold(settings, tables, clock, scheduler),
        _next_deal(tables),
        _empty_table(settings, tables, asks),
        _agent_lease(tables),
    )


def _include_table_routers(app: FastAPI, tables: TableService, page_build: PageBuild, presence: Presence) -> None:
    app.include_router(create_seating_router(tables, presence))
    app.include_router(create_tables_router(tables, page_build, presence))


def _include_table_sub_routers(
    app: FastAPI, settings: ServerSettings, tables: TableService, presence: Presence
) -> None:
    app.include_router(create_auction_router(tables, presence))
    app.include_router(create_declaring_router(tables, presence))
    app.include_router(create_pushing_router(tables, presence))
    app.include_router(create_playing_router(tables, presence))
    app.include_router(create_kontra_router(tables, presence))
    app.include_router(create_ready_router(tables, presence))
    app.include_router(create_series_end_router(tables, presence))
    app.include_router(create_game_list_router(tables))
    app.include_router(create_paused_router(tables, settings.paused_table_days))


def _refuse_invalid_request(_request: Request, refusal: Exception) -> JSONResponse:
    # The refused input stays out of the answer: text with a lone surrogate cannot be encoded as UTF-8.
    problems = cast("RequestValidationError", refusal).errors()
    kept = [{key: value for key, value in problem.items() if key != "input"} for problem in problems]
    return JSONResponse({"detail": jsonable_encoder(kept)}, status_code=422)


def _serving(
    settings: ServerSettings, tables: TableService, presence: Presence
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def hold_chairs_while_serving(serving: FastAPI) -> AsyncGenerator[None]:
        # Leave times are not stored, so every chair seated at the start is held for a full hold from now.
        # A table already past its wait has ended before the first request; every other waits what is left of it.
        occupied = await run_in_threadpool(tables.occupied_chairs)
        presence.hold_chairs((chair.table_id.value, chair.account_id) for chair in occupied)
        presence.watch_empty_tables(await run_in_threadpool(tables.resume_empty_waits, settings.empty_table_seconds))
        try:
            async with serving.state.mcp_front.running():
                yield
        finally:
            presence.stop()
            await presence.finish_writes()

    return hold_chairs_while_serving


def create_app(
    settings: ServerSettings,
    *,
    page_build: PageBuild,
    tables: TableService,
    rule_sets: RuleSetService,
    issuer_transports: IssuerTransports = ISSUER_OVER_HTTPS,
    stores: SingleProcessStores | None = None,
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
    chair_clock: Callable[[], float] = time.monotonic,
    chair_scheduler: Scheduler | None = None,
    resource_changes: ResourceChanges | None = None,
) -> FastAPI:
    sign_in_configs = build_sign_in_configs(settings)

    _configure_logging()

    sign_in_stores = stores if stores is not None else SingleProcessStores(audit=LoggingAuditSink())
    relying_party = build_relying_party(sign_in_configs, issuer_transports)

    changes = resource_changes if resource_changes is not None else ResourceChanges()
    # Wrapped first, so the timers' commands capture the service that counts leases and tells agents their standing and
    # their tables' views.
    tables = (
        tables.with_leases(lambda: presence.live_leases())
        .with_standing_signal(standing_signal(changes, relying_party.issuer))
        .with_view_signal(view_signal(changes, relying_party.issuer))
    )
    # One scheduler and one clock of waits serve the presence and the member front, so stopping the presence cancels
    # the pulses that ask a seat again with the chair holds' timers.
    scheduler = chair_scheduler if chair_scheduler is not None else LoopScheduler()
    asks = AskClock(chair_clock)
    presence = _presence(settings, tables, chair_clock, scheduler, asks)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=_serving(settings, tables, presence))
    app.add_exception_handler(RequestValidationError, _refuse_invalid_request)
    app.include_router(create_router(page_build))
    app.include_router(create_account_router(settings.oidc_issuer))
    app.include_router(create_call_router(settings.call_origin))
    _include_table_routers(app, tables, page_build, presence)
    app.include_router(create_rule_sets_router(rule_sets))
    _include_table_sub_routers(app, settings, tables, presence)
    app.include_router(create_streams_router(tables, presence, sign_in_stores.sessions, heartbeat_seconds))
    app.state.stop_streams = presence.stop
    install_web_auth_config(app, sign_in_configs.web_auth)
    install_sign_in(app, relying_party, sign_in_stores.transaction, page_build)
    mcp = mount_mcp(
        app,
        relying_party,
        sign_in_stores.transaction,
        settings.public_origin,
        presence.renew_lease,
        member_front(tables, presence, changes, scheduler, asks),
    )
    app.state.mcp_front = mcp.front
    _install_web_auth(app, sign_in_stores.sessions, page_build, settings.call_origin, mcp)

    return app
