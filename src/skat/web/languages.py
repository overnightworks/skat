"""Which language a request is answered in.

webauth's resolver decides it, from the account's language the issuer gave at sign-in, else the browser's
`Accept-Language`, else the default; Skat only names the languages it offers.
"""

from typing import TYPE_CHECKING

from webauth.dependencies import account_language_of_session
from webauth.languages import AppLanguages, resolve_language

if TYPE_CHECKING:
    from starlette.requests import HTTPConnection
    from webauth.config import WebAuthConfig
    from webauth.ports import SessionRecordStore

APP_LANGUAGES = AppLanguages(offered=("de",), default="de")


def language_of_request(connection: HTTPConnection, *, sessions: SessionRecordStore, config: WebAuthConfig) -> str:
    return resolve_language(
        APP_LANGUAGES,
        account_tag=account_language_of_session(connection, sessions=sessions, config=config),
        accept_language=connection.headers.get("accept-language"),
    )
