import asyncio
import signal
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, NoReturn, cast

import structlog
from agents.mcp_server import ResourceChanges
from agents.member import LEASE_SECONDS
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from logline import current_traceparent
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from webauth.config import installed_web_auth_config
from webauth.policies import (
    CacheControlRule,
    CspDirective,
    PathRules,
    RateLimitPolicy,
    SecurityHeadersPolicy,
    default_content_security_policy,
)
from webauth.session_groups import SessionGroups

from skat.table.records import TableId
from skat.web.abort import create_abort_router
from skat.web.account import create_account_router
from skat.web.auction import create_auction_router
from skat.web.call import create_call_router
from skat.web.calling import AgentRecords, AgentRoster, CallerMembership, create_calling_router
from skat.web.constants import (
    HEALTH_PATH,
    NO_CACHE_PATH_RULES,
    STREAM_HEARTBEAT_SECONDS,
)
from skat.web.declaring import create_declaring_router
from skat.web.end_answers import EndAnswers
from skat.web.game_list import create_game_list_router
from skat.web.gate import session_gate
from skat.web.kontra import create_kontra_router
from skat.web.lobby import AttentionSource, create_lobby_router
from skat.web.mcp import McpAccess, mount_mcp
from skat.web.member_place import member_front, nudge_signal, standing_signal, tools_signal, view_signal
from skat.web.nudging import create_nudging_router
from skat.web.paused import create_paused_router
from skat.web.playing import create_playing_router
from skat.web.presence import (
    AgentLease,
    ChairHold,
    EmptyTable,
    LoopScheduler,
    NextDeal,
    Presence,
    Scheduler,
)
from skat.web.pushing import create_pushing_router
from skat.web.reacting import create_reacting_router
from skat.web.ready import create_ready_router
from skat.web.routes import create_router, unknown_address_handler
from skat.web.rule_sets import create_rule_sets_router
from skat.web.run_line import RunLine
from skat.web.seating import create_seating_router
from skat.web.series_end import create_series_end_router
from skat.web.sign_in import (
    ISSUER_OVER_HTTPS,
    IssuerTransports,
    SignInConfigs,
    SignInPorts,
    build_sign_in_configs,
    build_web_auth,
    create_pages_router,
    sessions_entry,
)
from skat.web.stopping import create_stopping_router
from skat.web.streams import StreamSlots, StreamSource, create_streams_router
from skat.web.style import create_style_router
from skat.web.tables import create_tables_router
from skat.web.wakes import SharedWakes, WakeList

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

    from agents.mcp_server import PlaceStore
    from webauth.config import WebAuthConfig
    from webauth.oidc import OidcRelyingParty
    from webauth.ports import AgentFacts, RateLimitBackend, SessionRecordStore, WallClock
    from webauth.web_auth import WebAuth

    from skat.table.rule_sets import RuleSetService
    from skat.table.server_steps import EndAnswerLapse
    from skat.table.service import TableService
    from skat.web.page_build import PageBuild
    from skat.web.presence_roster import StreamLeases
    from skat.web.settings import ServerSettings
    from skat.web.sign_in import ExpirableSessions
    from skat.web.wakes import WakeChannel


UNPLAYED_SWEEP_SECONDS: Final = 3600
# How often a pod re-reads the stored proposals to end a series, so one whose timer ran on a pod that is gone lapses.
END_ANSWER_RECOVERY_SECONDS: Final = 15


@dataclass(frozen=True, kw_only=True)
class ServerRounds:
    """How often the server runs its two standing rounds: the end of unplayed tables and the re-read of the stored end
    proposals.
    """

    unplayed_sweep_seconds: float = UNPLAYED_SWEEP_SECONDS
    end_answer_recovery_seconds: float = END_ANSWER_RECOVERY_SECONDS


STANDARD_ROUNDS: Final = ServerRounds()


@dataclass(frozen=True, kw_only=True)
class Clocks:
    """The two clocks the server reads: the wall clock that judges when a session expires, and the clock of the chair
    holds and of the waits at the table, which a test that lets a minute pass moves itself.
    """

    wall: WallClock = time.time
    chair: Callable[[], float] = time.monotonic


STANDARD_CLOCKS: Final = Clocks()


log = structlog.get_logger()


async def _always_ready() -> bool:  # NOSONAR(S7503) the database_ready port is awaited
    return True


def end_with_sigterm() -> None:
    """Ask the server to stop as an orchestrator does, which ends its streams and lets the platform restart it."""
    signal.raise_signal(signal.SIGTERM)


@dataclass(frozen=True, kw_only=True)
class PodLinks:
    """What the pods of one deployment share: the counts of their sign-in limits, the channel that carries their
    wakes, the place store that tells them which agents listen and what changed for them, the record of each agent's
    name and owner, the leases that count who watches which table, and how a pod stops itself when the wake channel
    cannot be heard.
    """

    rate_limits: RateLimitBackend
    wake_channel: WakeChannel
    place_store: PlaceStore
    agent_records: AgentRecords
    stream_leases: StreamLeases
    end_process: Callable[[], None] = end_with_sigterm


def _content_security_policy(page_build: PageBuild, call_origin: str | None) -> str:
    added_sources: dict[CspDirective, Sequence[str]] = {
        CspDirective.STYLE_SRC: ("'unsafe-hashes'", f"'{page_build.announcer_style_hash}'")
    }
    if call_origin is not None:
        added_sources[CspDirective.FRAME_ANCESTORS] = (call_origin,)
    return default_content_security_policy(page_build.script_hashes, added_sources=added_sources)


def _build_web_auth(
    sign_in_configs: SignInConfigs,
    issuer_transports: IssuerTransports,
    stores: SignInPorts,
    page_build: PageBuild,
    call_origin: str | None,
) -> WebAuth:
    return build_web_auth(
        sign_in_configs,
        issuer_transports,
        stores,
        page_build,
        security_headers=SecurityHeadersPolicy(
            content_security_policy=_content_security_policy(page_build, call_origin),
            cache_control_rules=(CacheControlRule(paths=NO_CACHE_PATH_RULES, value="no-cache"),),
        ),
        # /health is the edge's readiness probe.
        rate_limit=RateLimitPolicy(exempt=PathRules(exact=frozenset({HEALTH_PATH}))),
        gate=session_gate(),
    )


def _chair_hold(
    settings: ServerSettings, tables: TableService, clock: Callable[[], float], scheduler: Scheduler
) -> ChairHold:
    async def leave(table_id: str, account_id: str) -> None:
        await run_in_threadpool(
            tables.note_leave, TableId(table_id), account_id, settings.chair_hold_seconds, newest_wins=True
        )

    async def lapse(table_id: str, account_id: str) -> None:
        await run_in_threadpool(
            tables.note_leave, TableId(table_id), account_id, settings.chair_hold_seconds, newest_wins=False
        )

    async def clear(table_id: str, account_id: str) -> None:
        await run_in_threadpool(tables.clear_hold, TableId(table_id), account_id)

    async def due() -> list[tuple[str, str]]:
        return [(held.table_id.value, held.account_id) for held in await run_in_threadpool(tables.due_holds)]

    async def free_chair(table_id: str, account_id: str, absent: AbstractContextManager[bool | None]) -> bool:
        return await run_in_threadpool(tables.free_held_chair, TableId(table_id), account_id, absent)

    return ChairHold(clock, scheduler, leave, lapse, clear, due, free_chair)


def _agent_lease(tables: TableService) -> AgentLease:
    async def seated_tables(account_id: str) -> list[str]:
        held = await run_in_threadpool(tables.tables_held_by, account_id)
        return [table_id.value for table_id in held]

    return AgentLease(LEASE_SECONDS, seated_tables)


def _caller_membership(
    relying_party: OidcRelyingParty,
    sign_in_configs: SignInConfigs,
    stores: SignInPorts,
    clock: Callable[[], float],
) -> CallerMembership:
    groups = SessionGroups(relying_party, sessions_entry(stores), sign_in_configs.web_auth)
    return CallerMembership(groups, sign_in_configs.web_auth, relying_party.issuer, clock)


def _agent_roster(
    changes: ResourceChanges,
    relying_party: OidcRelyingParty,
    records: AgentRecords,
    sign_in_configs: SignInConfigs,
) -> AgentRoster:
    return AgentRoster(changes.listeners, relying_party.issuer, records, sign_in_configs.web_auth.signing_key)


def _agent_changes(store: PlaceStore) -> ResourceChanges:
    """The changes the pods tell their listening agents through `store`."""
    return ResourceChanges(store)


def _telling_agents(
    tables: TableService, live_leases: Callable[[], frozenset[str]], changes: ResourceChanges, issuer: str
) -> TableService:
    """`tables` counting `live_leases`, storing the trace of each commit and telling agents their standing, their
    tables' views and their tools.
    """
    return (
        tables.with_leases(live_leases)
        .with_trace(current_traceparent)
        .with_standing_signal(standing_signal(changes, issuer))
        .with_view_signal(view_signal(changes, issuer))
        .with_tools_signal(tools_signal(changes, issuer))
    )


def _agent_heard(presence: Presence, roster: AgentRoster) -> Callable[[str, AgentFacts], Awaitable[None]]:
    async def heard(account_id: str, facts: AgentFacts) -> None:
        presence.renew_lease(account_id)
        await roster.heard(account_id, facts)

    return heard


def _next_deal(tables: TableService) -> NextDeal:
    async def deal(table_id: str, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        return await run_in_threadpool(tables.deal_next, TableId(table_id), connected_accounts)

    async def after_pause(table_id: str, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        return await run_in_threadpool(tables.deal_after_pause, TableId(table_id), connected_accounts)

    async def pause(table_id: str) -> None:
        await run_in_threadpool(tables.pause_next_deal, TableId(table_id))

    async def defer(table_id: str) -> None:
        await run_in_threadpool(tables.deal_next_soon, TableId(table_id))

    async def due() -> list[str]:
        return [table_id.value for table_id in await run_in_threadpool(tables.due_next_deals)]

    return NextDeal(deal, after_pause, pause, defer, due)


def _end_answers(tables: TableService) -> EndAnswers:
    async def lapse(table_id: str) -> EndAnswerLapse:
        return await run_in_threadpool(tables.lapse_end_answers, TableId(table_id))

    return EndAnswers(lapse)


def _empty_table(settings: ServerSettings, tables: TableService) -> EmptyTable:
    async def end(table_id: str, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        return await run_in_threadpool(
            tables.end_empty_table, TableId(table_id), connected_accounts, settings.empty_table_seconds
        )

    async def note(table_id: str, connected_accounts: AbstractContextManager[frozenset[str] | None]) -> bool:
        return await run_in_threadpool(
            tables.note_presence, TableId(table_id), connected_accounts, settings.empty_table_seconds
        )

    async def due() -> list[str]:
        return [
            table_id.value
            for table_id in await run_in_threadpool(tables.due_empty_tables, settings.empty_table_seconds)
        ]

    return EmptyTable(end, note, due)


def _presence(
    settings: ServerSettings,
    tables: TableService,
    clock: Callable[[], float],
    scheduler: Scheduler,
    wakes: WakeList,
    stream_leases: StreamLeases,
) -> Presence:
    return Presence(
        _chair_hold(settings, tables, clock, scheduler),
        _next_deal(tables),
        _empty_table(settings, tables),
        _agent_lease(tables),
        wakes,
        stream_leases,
        _end_answers(tables),
    )


def _include_edge_routers(
    app: FastAPI,
    settings: ServerSettings,
    page_build: PageBuild,
    sessions: SessionRecordStore,
    web_auth: WebAuthConfig,
    database_ready: Callable[[], Awaitable[bool]],
) -> None:
    app.include_router(create_router(page_build, sessions, web_auth, database_ready))
    app.add_exception_handler(HTTPException, unknown_address_handler(page_build, sessions, web_auth))
    app.include_router(create_account_router(settings.oidc_issuer))
    app.include_router(create_call_router(settings.call_origin))


def _include_table_routers(
    app: FastAPI,
    tables: TableService,
    page_build: PageBuild,
    presence: Presence,
    wakes: WakeList,
    sessions: SessionRecordStore,
    web_auth: WebAuthConfig,
) -> None:
    app.include_router(create_seating_router(tables, presence, wakes))
    app.include_router(create_stopping_router(tables, presence))
    app.include_router(create_tables_router(tables, page_build, presence, sessions, web_auth))


def _include_stream_routers(
    app: FastAPI,
    settings: ServerSettings,
    tables: TableService,
    presence: Presence,
    wakes: WakeList,
    slots: StreamSlots,
    sessions: SessionRecordStore,
    heartbeat_seconds: float,
) -> None:

    def attention_of(table_id: str, account_id: str) -> StreamSource:
        return AttentionSource(tables, presence, wakes, account_id, settings.paused_table_days, table_id)

    app.include_router(create_streams_router(tables, presence, sessions, slots, heartbeat_seconds, attention_of))
    app.include_router(
        create_lobby_router(tables, presence, wakes, sessions, slots, heartbeat_seconds, settings.paused_table_days)
    )
    app.state.stop_streams = presence.stop


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
    app.include_router(create_abort_router(tables, presence))
    app.include_router(create_style_router(tables, presence))
    app.include_router(create_reacting_router(tables, presence))
    app.include_router(create_game_list_router(tables))
    app.include_router(create_paused_router(tables, settings.paused_table_days))


def _refuse_invalid_request(_request: Request, refusal: Exception) -> JSONResponse:
    # The refused input stays out of the answer: text with a lone surrogate cannot be encoded as UTF-8.
    problems = cast("RequestValidationError", refusal).errors()
    kept = [{key: value for key, value in problem.items() if key != "input"} for problem in problems]
    return JSONResponse({"detail": jsonable_encoder(kept)}, status_code=422)


async def _end_unplayed_tables(
    settings: ServerSettings, tables: TableService, presence: Presence, *, at_start: bool
) -> int:
    """End every table whose days without a deal or step of play are up and wake its streams, and return how many
    ended. A table that fails is skipped and retried by the next run, except at the start, where the failure stops the
    server.
    """
    days = settings.paused_table_days
    ended_count = 0
    for table_id in await run_in_threadpool(tables.unplayed_tables, days):
        try:
            ended = await run_in_threadpool(tables.end_unplayed_table, table_id, days, presence.writing())
        except Exception as failure:
            if at_start:
                raise
            # The failure's message may carry an account id, so only its type is logged.
            log.error("unplayed_table_end.failed", table_id=table_id.value, error_type=type(failure).__name__)
            continue
        if ended:
            presence.table_ended(table_id.value)
            ended_count += 1
    return ended_count


async def _watch_pending_end_answers(tables: TableService, presence: Presence) -> None:
    presence.end_answer_watch.watch_all(await run_in_threadpool(tables.pending_end_answers))


def _recover_end_answers(tables: TableService, presence: Presence, scheduler: Scheduler, period_seconds: float) -> None:
    """Every `period_seconds` arm the minute of each stored proposal that has no timer on this pod; a failed read is
    logged by its type, and the next round reads again.
    """

    async def recover() -> None:
        try:
            await _watch_pending_end_answers(tables, presence)
        except Exception as failure:
            log.error("end_answers_read.failed", error_type=type(failure).__name__)
        if not presence.stopped:
            scheduler.schedule(period_seconds, recover)

    scheduler.schedule(period_seconds, recover)


async def _forget_ended_tables(settings: ServerSettings, tables: TableService) -> int:
    return await run_in_threadpool(tables.forget_ended_tables, settings.ended_table_days)


def _session_forgetter(app: FastAPI, sessions: ExpirableSessions) -> Callable[[], Awaitable[int]]:
    """The call that deletes the sessions expired by webauth's clock and returns how many went; every pod runs it, and
    a repeat deletes none.
    """

    async def forget() -> int:
        now = datetime.fromtimestamp(installed_web_auth_config(app).wall_clock(), UTC)
        return await run_in_threadpool(sessions.delete_expired, now)

    return forget


async def _swept(step: Callable[[], Awaitable[int]], log_failure: Callable[[str], None]) -> int | None:
    """Run one step of a sweep and return its count; a failure is logged by its type and counts nothing, and the next
    step and the next sweep still run.
    """
    try:
        return await step()
    except Exception as failure:
        log_failure(type(failure).__name__)
        return None


def _sweep_tables(
    settings: ServerSettings,
    tables: TableService,
    presence: Presence,
    scheduler: Scheduler,
    forget_expired_sessions: Callable[[], Awaitable[int]],
    period_seconds: float,
) -> None:
    line = RunLine("table_sweep.ended")

    async def sweep() -> None:
        step = line.run()
        ended = await _swept(
            lambda: _end_unplayed_tables(settings, tables, presence, at_start=False),
            lambda failure: log.error("unplayed_tables_read.failed", error_type=failure),
        )
        forgotten_tables = await _swept(
            lambda: _forget_ended_tables(settings, tables),
            lambda failure: log.error("ended_tables_forget.failed", error_type=failure),
        )
        forgotten_sessions = await _swept(
            forget_expired_sessions, lambda failure: log.error("expired_sessions_forget.failed", error_type=failure)
        )
        counts = {
            "ended_table_count": ended or 0,
            "forgotten_table_count": forgotten_tables or 0,
            "forgotten_session_count": forgotten_sessions or 0,
        }
        line.written(step, counts, failed=None in (ended, forgotten_tables, forgotten_sessions))
        if not presence.stopped:
            scheduler.schedule(period_seconds, sweep)

    scheduler.schedule(period_seconds, sweep)


def _log_if_failed(lapses: asyncio.Task[NoReturn]) -> None:
    """A pod that stops serving the lapsed leases still hears its streams' heartbeats, which re-read who is present;
    only the wake of a dead pod's table is late.
    """
    if not lapses.cancelled():
        log.error("stream_lapses.stopped", error_type=type(lapses.exception()).__name__)


def _serving(
    settings: ServerSettings,
    tables: TableService,
    presence: Presence,
    scheduler: Scheduler,
    sessions: ExpirableSessions,
    rounds: ServerRounds,
    shared_wakes: SharedWakes,
    wakes: WakeList,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def while_serving(serving: FastAPI) -> AsyncGenerator[None]:
        # The wakes come first: a pod that serves before it hears them may show a state another pod has changed.
        async with shared_wakes.following(wakes):
            await _watch_pending_end_answers(tables, presence)
            _recover_end_answers(tables, presence, scheduler, rounds.end_answer_recovery_seconds)
            await _end_unplayed_tables(settings, tables, presence, at_start=True)
            await _forget_ended_tables(settings, tables)
            forget_expired_sessions = _session_forgetter(serving, sessions)
            await forget_expired_sessions()
            _sweep_tables(settings, tables, presence, scheduler, forget_expired_sessions, rounds.unplayed_sweep_seconds)
            # The holds, pauses and waits are stored, so the first sweeps act on those that fell due while no pod ran.
            presence.start_sweeps()
            lapses = asyncio.create_task(presence.serve_lapses())
            lapses.add_done_callback(_log_if_failed)
            try:
                async with serving.state.mcp_front.running():
                    log.info("process.ready")
                    yield
            finally:
                lapses.cancel()
                presence.stop()
                await presence.finish_writes()
                await asyncio.gather(lapses, return_exceptions=True)

    return while_serving


def _new_app(lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]]) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_exception_handler(RequestValidationError, _refuse_invalid_request)
    return app


def _mount_agent_front(
    app: FastAPI,
    settings: ServerSettings,
    tables: TableService,
    presence: Presence,
    scheduler: Scheduler,
    roster: AgentRoster,
    changes: ResourceChanges,
    issuer: str,
) -> McpAccess:
    mcp = mount_mcp(
        app,
        issuer,
        settings.public_origin,
        _agent_heard(presence, roster),
        member_front(tables, presence, changes, scheduler, presence.waits),
        settings.realm,
    )
    app.state.mcp_front = mcp.front
    return mcp


def create_app(
    settings: ServerSettings,
    *,
    page_build: PageBuild,
    tables: TableService,
    rule_sets: RuleSetService,
    stores: SignInPorts,
    pods: PodLinks,
    issuer_transports: IssuerTransports = ISSUER_OVER_HTTPS,
    heartbeat_seconds: float = STREAM_HEARTBEAT_SECONDS,
    clocks: Clocks = STANDARD_CLOCKS,
    chair_scheduler: Scheduler | None = None,
    rounds: ServerRounds = STANDARD_ROUNDS,
    resource_changes: Callable[[PlaceStore], ResourceChanges] = _agent_changes,
    database_ready: Callable[[], Awaitable[bool]] = _always_ready,
) -> FastAPI:
    sign_in_configs = build_sign_in_configs(settings, pods.rate_limits, clocks.wall)

    auth = _build_web_auth(sign_in_configs, issuer_transports, stores, page_build, settings.call_origin)
    relying_party = auth.relying_party

    changes = resource_changes(pods.place_store)
    roster = _agent_roster(changes, relying_party, pods.agent_records, sign_in_configs)
    # Wrapped first, so the timers' commands capture the service that counts leases and tells agents.
    tables = _telling_agents(tables, lambda: presence.live_leases(), changes, relying_party.issuer)
    # One scheduler and one clock of waits serve the presence and the member front, so stopping the presence cancels
    # the pulses that ask a seat again with the chair holds' timers.
    scheduler = chair_scheduler if chair_scheduler is not None else LoopScheduler()
    shared_wakes = SharedWakes(pods.wake_channel, end_process=pods.end_process)
    wakes = WakeList(shared_wakes.publish)
    slots = StreamSlots(settings.streams_per_account)
    presence = _presence(settings, tables, clocks.chair, scheduler, wakes, pods.stream_leases)

    app = _new_app(
        _serving(
            settings,
            tables,
            presence,
            scheduler,
            stores.sessions,
            rounds,
            shared_wakes,
            wakes,
        )
    )
    _include_edge_routers(app, settings, page_build, stores.sessions, sign_in_configs.web_auth, database_ready)
    _include_table_routers(app, tables, page_build, presence, wakes, stores.sessions, sign_in_configs.web_auth)
    membership = _caller_membership(relying_party, sign_in_configs, stores, clocks.chair)
    app.include_router(create_calling_router(tables, presence, roster, membership))
    app.include_router(create_rule_sets_router(rule_sets))
    _include_table_sub_routers(app, settings, tables, presence)
    app.include_router(create_nudging_router(tables, presence, nudge_signal(changes, relying_party.issuer)))
    _include_stream_routers(app, settings, tables, presence, wakes, slots, stores.sessions, heartbeat_seconds)
    app.include_router(create_pages_router(page_build, stores.sessions, sign_in_configs.web_auth))
    mcp = _mount_agent_front(app, settings, tables, presence, scheduler, roster, changes, relying_party.issuer)
    auth.install(app, bearer=mcp.bearer_gate)

    return app
