from contextlib import nullcontext
from typing import TYPE_CHECKING

from webauth.dependencies import LoginRedirect
from webauth.middleware import SessionGate
from webauth.policies import PathRules, PublicRule

from skat.web.constants import (
    CALL_SIGN_IN_PATH,
    HEALTH_PATH,
    IMMUTABLE_ASSET_PATH_RULES,
    LOGIN_PATH,
    NO_ACCESS_PATH,
    RETURN_PATH_QUERY_NAME,
    SIGN_IN_PATHS,
    VERSION_FILE_PATH,
)

if TYPE_CHECKING:
    from webauth.ports import SessionRecordStore

PUBLIC_PATHS = frozenset({HEALTH_PATH, LOGIN_PATH, CALL_SIGN_IN_PATH, NO_ACCESS_PATH, VERSION_FILE_PATH})


def session_gate(sessions: SessionRecordStore) -> SessionGate:
    # Each call takes the stores' shared guard, so a sign-in entry in progress holds this call back.
    return SessionGate(
        session_transaction=lambda: nullcontext(sessions),
        login_redirect=LoginRedirect(LOGIN_PATH, RETURN_PATH_QUERY_NAME),
        public=(
            PublicRule(PathRules(exact=PUBLIC_PATHS)),
            PublicRule(IMMUTABLE_ASSET_PATH_RULES),
            *SIGN_IN_PATHS.public_rules,
        ),
    )
