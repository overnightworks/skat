"""Which language a request is answered in.

webauth's resolver decides it, from the account's language the issuer gave at sign-in, else the browser's
`Accept-Language`, else the default; Skat offers the languages of its catalog files.
"""

from typing import TYPE_CHECKING

from webauth.dependencies import account_language_of_session
from webauth.languages import AppLanguages, resolve_language

from skat.web.words import LANGUAGES, SOURCE_LANGUAGE

if TYPE_CHECKING:
    from starlette.requests import HTTPConnection
    from webauth.config import WebAuthConfig
    from webauth.ports import SessionRecordStore

    from skat.web.words import Language

APP_LANGUAGES = AppLanguages(offered=LANGUAGES, default=SOURCE_LANGUAGE)
# The request headers the resolver reads; the cookie carries the session with the account's language.
LANGUAGE_VARY = "Accept-Language, Cookie"


def language_of_request(connection: HTTPConnection, *, sessions: SessionRecordStore, config: WebAuthConfig) -> Language:
    tag = resolve_language(
        APP_LANGUAGES,
        account_tag=account_language_of_session(connection, sessions=sessions, config=config),
        accept_language=connection.headers.get("accept-language"),
    )
    return next(language for language in LANGUAGES if language == tag)
