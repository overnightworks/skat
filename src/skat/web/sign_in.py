import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Protocol
from urllib.parse import parse_qs, quote, urlsplit

import structlog
from fastapi import APIRouter, FastAPI, Query, Request, Response
from fastapi.responses import RedirectResponse
from webauth.admission import AdmissionRefusal
from webauth.config import SessionLifetime, WebAuthConfig
from webauth.https_client import fetch_key_set_over_https
from webauth.oidc import OidcClientConfig, OidcRefusal, OidcRelyingParty, TokenRequestPost
from webauth.oidc_transport import post_token_request_over_https
from webauth.ports import SessionRecordStore
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
from skat.web.languages import LANGUAGE_VARY, language_of_request
from skat.web.mcp import Exclusion, excluded
from skat.web.page_build import BuiltPage
from skat.web.routes import READ_METHODS, built_page_response
from skat.web.secret_files import StartRefusedError, read_secret_file
from skat.web.tables import TABLE_PAGE_PREFIX
from skat.web.words import text

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from pydantic import SecretStr
    from starlette.requests import HTTPConnection
    from webauth.jwt_verification import KeySetFetch
    from webauth.ports import AccountEvent, SignInTransaction

    from skat.web.page_build import PageBuild, SignInPages
    from skat.web.settings import ServerSettings

OPENID_CONNECT_PATH = "/protocol/openid-connect"
SIGN_IN_ADDRESS = f'href="{AUTH_START_PATH}"'.encode()

logger = structlog.get_logger()


class LoggingAuditSink:
    """Logs each account event by its kind, the issuer's subject and the role, never a username."""

    def account_event(self, event: AccountEvent) -> None:
        logger.info("account_event", kind=event.kind.value, subject_id=event.subject_id, role=event.role)


class ExpirableSessions(SessionRecordStore, Protocol):
    """The sessions the session gate asks, which also drop the ones expired at a time."""

    def delete_expired(self, now: datetime) -> int: ...


class SignInPorts(Protocol):
    """What the app signs in with: the sessions the gate and the routes ask and the sign-in entry, both over the
    database every pod shares.
    """

    @property
    def sessions(self) -> ExpirableSessions: ...

    @property
    def transaction(self) -> SignInTransaction: ...


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

    def sign_in_pages_of(request: HTTPConnection) -> SignInPages:
        return page_build.sign_in_pages[language_of_request(request, sessions=sessions, config=web_auth)]

    install_sign_in_routes(
        app,
        paths=SIGN_IN_PATHS,
        relying_party=lambda _request: relying_party,
        admission=admission_for(relying_party.issuer),
        transaction=transaction,
        refused=lambda request, refusal: _refusal_response(refusal, sign_in_pages_of(request)),
        keeps_id_token=True,
        max_sessions=None,
        logout_page_text=lambda request: logout_page_text(request, sessions=sessions, config=web_auth),
        ui_language=lambda request: language_of_request(request, sessions=sessions, config=web_auth),
    )
    app.include_router(_create_pages_router(page_build, sign_in_pages_of))


def logout_page_text(request: HTTPConnection, *, sessions: SessionRecordStore, config: WebAuthConfig) -> LogoutPageText:
    language = language_of_request(request, sessions=sessions, config=config)
    return LogoutPageText(language=language, button_label=text(language, "logout.button"))


def _page_response(page: BuiltPage, status_code: int = HTTPStatus.OK) -> Response:
    """A sign-in page chosen by the request's language, which the caches are told."""
    response = built_page_response(page, status_code=status_code)
    response.headers["Vary"] = LANGUAGE_VARY
    return response


def _create_pages_router(page_build: PageBuild, sign_in_pages_of: Callable[[HTTPConnection], SignInPages]) -> APIRouter:
    router = APIRouter()
    for language, pages in page_build.sign_in_pages.items():
        if pages.signed_out.content.count(SIGN_IN_ADDRESS) != 1:
            raise SignInConfigurationError(
                f"The {language} signed-out page lacks its one {AUTH_START_PATH} address; run make frontend"
            )

    @router.api_route(LOGIN_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE))
    def signed_out(
        request: Request, next_path: Annotated[str | None, Query(alias=RETURN_PATH_QUERY_NAME)] = None
    ) -> Response:
        """Carries the raw `next` onto the sign-in address; webauth is the only validator of it."""
        signed_out_page = sign_in_pages_of(request).signed_out
        if next_path is None:
            return _page_response(signed_out_page)
        if _is_call_mode_table(next_path):
            # `+` with the encoded value on its right is the concatenation CodeQL's py/url-redirection accepts
            # as a fixed local target; an f-string is not.
            return RedirectResponse(
                CALL_SIGN_IN_PATH + "?" + RETURN_PATH_QUERY_NAME + "=" + quote(next_path, safe=""), HTTPStatus.SEE_OTHER
            )
        address = f"{AUTH_START_PATH}?{RETURN_PATH_QUERY_NAME}={quote(next_path, safe='')}".encode()
        carrying_next = signed_out_page.content.replace(SIGN_IN_ADDRESS, b'href="' + address + b'"')
        return _page_response(BuiltPage.of(carrying_next))

    @router.api_route(CALL_SIGN_IN_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE))
    def call_sign_in(request: Request) -> Response:
        return _page_response(sign_in_pages_of(request).call_sign_in)

    @router.api_route(NO_ACCESS_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE))
    def no_access(request: Request) -> Response:
        return _page_response(sign_in_pages_of(request).no_access)

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


def _refusal_response(refusal: SignInRefusal, sign_in_pages: SignInPages) -> Response:
    _log_refusal(refusal.cause)
    if refusal.page is RefusalPage.NO_ACCESS:
        return Response(status_code=HTTPStatus.SEE_OTHER, headers={"location": NO_ACCESS_PATH})
    return _page_response(sign_in_pages.login_failed, HTTPStatus.FORBIDDEN)


def _log_refusal(refusal: OidcRefusal | AdmissionRefusal) -> None:
    if isinstance(refusal, AdmissionRefusal):
        logger.info("sign_in_refused", reason=refusal.value)
        return
    codes = {
        "idp_error": refusal.idp_error,
        "token_rejection": None if refusal.token_rejection is None else refusal.token_rejection.value,
    }
    logger.info("sign_in_refused", reason=refusal.reason.value, **{name: code for name, code in codes.items() if code})
