from contextlib import nullcontext
from typing import TYPE_CHECKING

from webauth.dependencies import LoginRedirect
from webauth.middleware import SessionGate
from webauth.policies import PathRules, PublicRule

from skat.web.constants import HEALTH_PATH, LOGIN_PATH, NO_ACCESS_PATH, RETURN_PATH_QUERY_NAME, SIGN_IN_PATHS

if TYPE_CHECKING:
    from webauth.ports import SessionRecordStore

PUBLIC_PATHS = frozenset({HEALTH_PATH, LOGIN_PATH, NO_ACCESS_PATH})


def session_gate(
    sessions: SessionRecordStore, sign_in_assets: frozenset[str], resource_rule: PublicRule
) -> SessionGate:
    # Each call takes the stores' shared guard, so a sign-in entry in progress holds this call back.
    return SessionGate(
        session_transaction=lambda: nullcontext(sessions),
        login_redirect=LoginRedirect(LOGIN_PATH, RETURN_PATH_QUERY_NAME),
        public=(
            PublicRule(PathRules(exact=PUBLIC_PATHS | sign_in_assets)),
            *SIGN_IN_PATHS.public_rules,
            resource_rule,
        ),
    )
