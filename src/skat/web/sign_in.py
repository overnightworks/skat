import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated
from urllib.parse import parse_qs, quote, urlsplit

import structlog
from fastapi import APIRouter, FastAPI, Query, Response
from fastapi.responses import RedirectResponse
from webauth.admission import AdmissionRefusal
from webauth.config import SessionLifetime, WebAuthConfig
from webauth.https_client import fetch_key_set_over_https
from webauth.oidc import OidcClientConfig, OidcRefusal, OidcRelyingParty, TokenRequestPost
from webauth.oidc_transport import post_token_request_over_https
from webauth.proxies import TrustedProxies
from webauth.rate_limit import SingleProcessRateLimitBackend
from webauth.sign_in_routes import (
    LogoutPageText,
    RefusalPage,
    SignInRefusal,
    install_sign_in_routes,
)

from skat.web.constants import (
    AUTH_CALLBACK_PATH,
    AUTH_START_PATH,
    CALL_MODE,
    CALL_SIGN_IN_PATH,
    LOGIN_PATH,
    MODE_QUERY_NAME,
    NO_ACCESS_PATH,
    OIDC_LEEWAY_SECONDS,
    OIDC_SCOPES,
    RETURN_PATH_QUERY_NAME,
    SESSION_LIFETIME_SECONDS,
    SIGN_IN_PATHS,
)
from skat.web.gate import admission_for
from skat.web.languages import language_of_request
from skat.web.mcp import Exclusion, excluded
from skat.web.page_build import BuiltPage
from skat.web.routes import READ_METHODS, built_page_response
from skat.web.secret_files import StartRefusedError, read_secret_file
from skat.web.tables import TABLE_PAGE_PREFIX

if TYPE_CHECKING:
    from pydantic import SecretStr
    from webauth.jwt_verification import KeySetFetch
    from webauth.ports import AccountEvent, SessionRecordStore, SignInTransaction

    from skat.web.page_build import PageBuild
    from skat.web.settings import ServerSettings

OPENID_CONNECT_PATH = "/protocol/openid-connect"
LOGOUT_LABEL = "Log out"
SIGN_IN_ADDRESS = f'href="{AUTH_START_PATH}"'.encode()

logger = structlog.get_logger()


class LoggingAuditSink:
    """Logs each account event by its kind, the issuer's subject and the role, never a username."""

    def account_event(self, event: AccountEvent) -> None:
        logger.info("account_event", kind=event.kind.value, subject_id=event.subject_id, role=event.role)


class SignInConfigurationError(StartRefusedError):
    """The sign-in settings cannot start Skat; the message names settings, never their values."""


@dataclass(frozen=True)
class SignInConfigs:
    oidc_client: OidcClientConfig
    web_auth: WebAuthConfig


@dataclass(frozen=True)
class IssuerTransports:
    """The two network calls to the issuer, the only seam a test replaces."""

    post_token_request: TokenRequestPost
    fetch_key_set: KeySetFetch


ISSUER_OVER_HTTPS = IssuerTransports(
    post_token_request=post_token_request_over_https, fetch_key_set=fetch_key_set_over_https
)


def build_sign_in_configs(settings: ServerSettings) -> SignInConfigs:
    client_secret = read_secret_file(settings.oidc_client_secret_file, "oidc_client_secret_file")
    session_secret = read_secret_file(settings.session_secret_file, "session_secret_file")
    try:
        oidc_client = _build_oidc_client(settings, client_secret)
    except ValueError as refusal:
        raise SignInConfigurationError(f"oidc_issuer and public_origin are refused: {refusal}") from None
    trusted_proxies = _parse_trusted_proxies(settings.trusted_proxies)
    try:
        web_auth = _build_web_auth(settings, session_secret, trusted_proxies)
    except ValueError as refusal:
        raise SignInConfigurationError(f"session_secret_file is refused: {refusal}") from None
    return SignInConfigs(oidc_client=oidc_client, web_auth=web_auth)


def _parse_trusted_proxies(raw: str) -> TrustedProxies:
    try:
        return TrustedProxies.parse(raw)
    except ValueError:
        raise SignInConfigurationError("trusted_proxies is refused: name addresses or CIDR blocks") from None


def _build_oidc_client(settings: ServerSettings, client_secret: SecretStr) -> OidcClientConfig:
    openid_connect = settings.oidc_issuer + OPENID_CONNECT_PATH
    return OidcClientConfig(
        issuer=settings.oidc_issuer,
        authorization_endpoint=f"{openid_connect}/auth",
        token_endpoint=f"{openid_connect}/token",
        jwks_url=f"{openid_connect}/certs",
        end_session_endpoint=f"{openid_connect}/logout",
        client_id=settings.oidc_client_id,
        client_secret=client_secret,
        redirect_uri=settings.public_origin + AUTH_CALLBACK_PATH,
        post_logout_redirect_uri=settings.public_origin + LOGIN_PATH,
        scopes=OIDC_SCOPES,
        leeway_seconds=OIDC_LEEWAY_SECONDS,
    )


def _build_web_auth(
    settings: ServerSettings, session_secret: SecretStr, trusted_proxies: TrustedProxies
) -> WebAuthConfig:
    return WebAuthConfig(
        session_secret=session_secret,
        trusted_proxies=trusted_proxies,
        rate_limits=SingleProcessRateLimitBackend(),
        allowed_hosts_exact=frozenset({urlsplit(settings.public_origin).netloc}),
        session_lifetime=SessionLifetime(
            idle_seconds=SESSION_LIFETIME_SECONDS, absolute_max_age_seconds=SESSION_LIFETIME_SECONDS
        ),
        cookie_samesite="lax",
        cookie_secure=True,
    )


def build_relying_party(sign_in_configs: SignInConfigs, issuer_transports: IssuerTransports) -> OidcRelyingParty:
    return OidcRelyingParty(
        sign_in_configs.oidc_client,
        post_token_request=issuer_transports.post_token_request,
        fetch_key_set=issuer_transports.fetch_key_set,
        wall_clock=sign_in_configs.web_auth.wall_clock,
        monotonic_clock=time.monotonic,
    )


def install_sign_in(
    app: FastAPI,
    relying_party: OidcRelyingParty,
    transaction: SignInTransaction,
    page_build: PageBuild,
    sessions: SessionRecordStore,
    web_auth: WebAuthConfig,
) -> None:
    """The library serves the start, callback, logout and back-channel routes; the pages stay Skat's."""
    install_sign_in_routes(
        app,
        paths=SIGN_IN_PATHS,
        relying_party=lambda _request: relying_party,
        admission=admission_for(relying_party.issuer),
        transaction=transaction,
        refused=lambda _request, refusal: _refusal_response(refusal, page_build),
        keeps_id_token=True,
        max_sessions=None,
        logout_page_text=lambda _request: LogoutPageText(language="en", button_label=LOGOUT_LABEL),
        ui_language=lambda request: language_of_request(request, sessions=sessions, config=web_auth),
    )
    app.include_router(_create_pages_router(page_build))


def _create_pages_router(page_build: PageBuild) -> APIRouter:
    router = APIRouter()
    signed_out_page = page_build.signed_out
    if signed_out_page.content.count(SIGN_IN_ADDRESS) != 1:
        raise SignInConfigurationError(
            f"The signed-out page lacks its one {AUTH_START_PATH} address; run make frontend"
        )

    @router.api_route(LOGIN_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE))
    def signed_out(next_path: Annotated[str | None, Query(alias=RETURN_PATH_QUERY_NAME)] = None) -> Response:
        """Carries the raw `next` onto the sign-in address; webauth is the only validator of it."""
        if next_path is None:
            return built_page_response(signed_out_page)
        if _is_call_mode_table(next_path):
            return RedirectResponse(
                f"{CALL_SIGN_IN_PATH}?{RETURN_PATH_QUERY_NAME}={quote(next_path, safe='')}", HTTPStatus.SEE_OTHER
            )
        address = f"{AUTH_START_PATH}?{RETURN_PATH_QUERY_NAME}={quote(next_path, safe='')}".encode()
        return built_page_response(
            BuiltPage.of(signed_out_page.content.replace(SIGN_IN_ADDRESS, b'href="' + address + b'"'))
        )

    @router.api_route(CALL_SIGN_IN_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE))
    def call_sign_in() -> Response:
        return built_page_response(page_build.call_sign_in)

    @router.api_route(NO_ACCESS_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE))
    def no_access() -> Response:
        return built_page_response(page_build.no_access)

    return router


def _is_call_mode_table(next_path: str) -> bool:
    """Only chooses the page; webauth alone validates where a sign-in lands."""
    try:
        address = urlsplit(next_path)
    except ValueError:
        return False
    return (
        not address.scheme
        and not address.netloc
        and address.path.startswith(TABLE_PAGE_PREFIX)
        and CALL_MODE in parse_qs(address.query).get(MODE_QUERY_NAME, [])
    )


def _refusal_response(refusal: SignInRefusal, page_build: PageBuild) -> Response:
    _log_refusal(refusal.cause)
    if refusal.page is RefusalPage.NO_ACCESS:
        return Response(status_code=HTTPStatus.SEE_OTHER, headers={"location": NO_ACCESS_PATH})
    return built_page_response(page_build.login_failed, status_code=HTTPStatus.FORBIDDEN)


def _log_refusal(refusal: OidcRefusal | AdmissionRefusal) -> None:
    if isinstance(refusal, AdmissionRefusal):
        logger.info("sign_in_refused", reason=refusal.value)
        return
    codes = {
        "idp_error": refusal.idp_error,
        "token_rejection": None if refusal.token_rejection is None else refusal.token_rejection.value,
    }
    logger.info("sign_in_refused", reason=refusal.reason.value, **{name: code for name, code in codes.items() if code})
