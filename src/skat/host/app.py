import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
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
from skat.web.gate import session_gate
from skat.web.presence import ChairHold, LoopScheduler, Presence
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
    from collections.abc import AsyncGenerator

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


def _install_web_auth(app: FastAPI, sessions: InMemorySessions, page_build: PageBuild) -> None:
    install_web_auth_middleware(
        app,
        security_headers=SecurityHeadersPolicy(
            content_security_policy=default_content_security_policy(
                page_build.script_hashes, added_sources={CspDirective.STYLE_SRC: ANNOUNCER_STYLE_SOURCES}
            ),
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
        session_gate=session_gate(sessions, page_build.sign_in_assets),
    )


def _chair_hold(settings: ServerSettings, tables: TableService) -> ChairHold:
    async def free_chair(table_id: str, account_id: str) -> bool:
        return await run_in_threadpool(tables.free_chair, TableId(table_id), account_id)

    return ChairHold(settings.chair_hold_seconds, time.monotonic, LoopScheduler(), free_chair)


def create_app(
    settings: ServerSettings,
    *,
    page_build: PageBuild,
    tables: TableService,
    issuer_transports: IssuerTransports = ISSUER_OVER_HTTPS,
    stores: SignInStores | None = None,
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
) -> FastAPI:
    sign_in_configs = build_sign_in_configs(settings)

    _configure_logging()

    sign_in_stores = stores if stores is not None else SignInStores.in_memory()
    relying_party = build_relying_party(sign_in_configs, issuer_transports)

    presence = Presence(_chair_hold(settings, tables))

    @asynccontextmanager
    async def hold_chairs_while_serving(_app: FastAPI) -> AsyncGenerator[None]:
        # Leave times are not stored, so every chair seated at the start is held for a full hold from now.
        occupied = await run_in_threadpool(tables.occupied_chairs)
        presence.hold_chairs((chair.table_id.value, chair.account_id) for chair in occupied)
        try:
            yield
        finally:
            presence.stop()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=hold_chairs_while_serving)
    app.include_router(create_router(page_build))
    app.include_router(create_account_router(settings.oidc_issuer))
    app.include_router(create_tables_router(tables, page_build, presence))
    app.include_router(create_streams_router(tables, presence, sign_in_stores.sessions, heartbeat_seconds))
    app.state.stop_streams = presence.stop
    install_web_auth_config(app, sign_in_configs.web_auth)
    install_sign_in(app, relying_party, sign_in_stores.transaction, page_build)
    _install_web_auth(app, sign_in_stores.sessions, page_build)

    return app
