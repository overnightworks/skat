import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from agents.member import LEASE_SECONDS
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from webauth.config import install_web_auth_config
from webauth.middleware import install_web_auth_middleware
from webauth.policies import (
    BodySizePolicy,
    CacheControlRule,
    CspDirective,
    CsrfPolicy,
    RateLimitPolicy,
    RateLimitRule,
    SecurityHeadersPolicy,
    default_content_security_policy,
)

from skat.table.records import TableId
from skat.web.account import create_account_router
from skat.web.auction import create_auction_router
from skat.web.constants import (
    ANNOUNCER_STYLE_SOURCES,
    DEFAULT_RATE_LIMIT_BUDGET,
    DEFAULT_REQUEST_BODY_MAX_BYTES,
    NO_CACHE_PATH_RULES,
    PERMISSIONS_POLICY,
    RATE_LIMIT_EXEMPT_PATH_RULES,
    SIGN_IN_PATHS,
    SIGN_IN_RATE_LIMIT_BUDGET,
    STREAM_HEARTBEAT_SECONDS,
)
from skat.web.declaring import create_declaring_router
from skat.web.game_list import create_game_list_router
from skat.web.gate import session_gate
from skat.web.kontra import create_kontra_router
from skat.web.mcp import McpAccess, mount_mcp
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
from skat.web.ready import create_ready_router
from skat.web.routes import create_router
from skat.web.sign_in import (
    ISSUER_OVER_HTTPS,
    IssuerTransports,
    build_relying_party,
    build_sign_in_configs,
    install_sign_in,
)
from skat.web.stores import InMemorySessions, SignInStores
from skat.web.streams import create_streams_router
from skat.web.tables import create_tables_router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Sequence
    from contextlib import AbstractContextManager

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
    added_sources: dict[CspDirective, Sequence[str]] = {CspDirective.STYLE_SRC: ANNOUNCER_STYLE_SOURCES}
    if call_origin is not None:
        added_sources[CspDirective.FRAME_ANCESTORS] = (call_origin,)
    return default_content_security_policy(page_build.script_hashes, added_sources=added_sources)


def _install_web_auth(
    app: FastAPI, sessions: InMemorySessions, page_build: PageBuild, call_origin: str | None, mcp: McpAccess
) -> None:
    install_web_auth_middleware(
        app,
        security_headers=SecurityHeadersPolicy(
            content_security_policy=_content_security_policy(page_build, call_origin),
            permissions_policy=PERMISSIONS_POLICY,
            cache_control_rules=(
                SIGN_IN_PATHS.cache_control_rule,
                CacheControlRule(paths=NO_CACHE_PATH_RULES, value="no-cache"),
            ),
        ),
        csrf_origin=CsrfPolicy(exempt=SIGN_IN_PATHS.backchannel),
        body_size=BodySizePolicy(
            default_max_bytes=DEFAULT_REQUEST_BODY_MAX_BYTES,
            rules=(SIGN_IN_PATHS.backchannel_body_size_rule,),
        ),
        rate_limit=RateLimitPolicy(
            default=DEFAULT_RATE_LIMIT_BUDGET,
            rules=(RateLimitRule(paths=SIGN_IN_PATHS.browser_paths, budget=SIGN_IN_RATE_LIMIT_BUDGET),),
            exempt=RATE_LIMIT_EXEMPT_PATH_RULES,
        ),
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


def _empty_table(settings: ServerSettings, tables: TableService) -> EmptyTable:
    async def end(table_id: str, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        return await run_in_threadpool(
            tables.end_empty_table, TableId(table_id), connected_accounts, settings.empty_table_seconds
        )

    async def note(table_id: str, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        return await run_in_threadpool(
            tables.note_presence, TableId(table_id), connected_accounts, settings.empty_table_seconds
        )

    return EmptyTable(settings.empty_table_seconds, end, note)


def _include_table_sub_routers(app: FastAPI, tables: TableService, presence: Presence) -> None:
    app.include_router(create_auction_router(tables, presence))
    app.include_router(create_declaring_router(tables, presence))
    app.include_router(create_playing_router(tables, presence))
    app.include_router(create_kontra_router(tables, presence))
    app.include_router(create_ready_router(tables, presence))
    app.include_router(create_game_list_router(tables))
    app.include_router(create_paused_router(tables))


def create_app(
    settings: ServerSettings,
    *,
    page_build: PageBuild,
    tables: TableService,
    issuer_transports: IssuerTransports = ISSUER_OVER_HTTPS,
    stores: SignInStores | None = None,
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
    chair_clock: Callable[[], float] = time.monotonic,
    chair_scheduler: Scheduler | None = None,
) -> FastAPI:
    sign_in_configs = build_sign_in_configs(settings)

    _configure_logging()

    sign_in_stores = stores if stores is not None else SignInStores.in_memory()
    relying_party = build_relying_party(sign_in_configs, issuer_transports)

    # Wrapped first, so the timers' commands capture the service that counts a lease as presence.
    tables = tables.with_leases(lambda: presence.live_leases())
    presence = Presence(
        _chair_hold(settings, tables, chair_clock, chair_scheduler if chair_scheduler is not None else LoopScheduler()),
        _next_deal(tables),
        _empty_table(settings, tables),
        _agent_lease(tables),
    )

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

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=hold_chairs_while_serving)
    app.include_router(create_router(page_build))
    app.include_router(create_account_router(settings.oidc_issuer))
    app.include_router(create_tables_router(tables, page_build, presence))
    _include_table_sub_routers(app, tables, presence)
    app.include_router(create_streams_router(tables, presence, sign_in_stores.sessions, heartbeat_seconds))
    app.state.stop_streams = presence.stop
    install_web_auth_config(app, sign_in_configs.web_auth)
    install_sign_in(app, relying_party, sign_in_stores.transaction, page_build)
    mcp = mount_mcp(app, relying_party, sign_in_stores.transaction, settings.public_origin, presence.renew_lease)
    app.state.mcp_front = mcp.front
    _install_web_auth(app, sign_in_stores.sessions, page_build, settings.call_origin, mcp)

    return app
