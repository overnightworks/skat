from contextlib import nullcontext
from typing import TYPE_CHECKING

from webauth.admission import AdmissionConfig, NoAdmins
from webauth.dependencies import LoginRedirect
from webauth.middleware import SessionGate
from webauth.policies import PathRules, PublicRule

from skat.web.constants import (
    CALL_SIGN_IN_PATH,
    HEALTH_PATH,
    IMMUTABLE_ASSET_PATH_RULES,
    LOGIN_GROUP,
    LOGIN_PATH,
    NO_ACCESS_PATH,
    RETURN_PATH_QUERY_NAME,
    VERSION_FILE_PATH,
)

if TYPE_CHECKING:
    from webauth.ports import SessionRecordStore

PUBLIC_PATHS = frozenset({HEALTH_PATH, LOGIN_PATH, CALL_SIGN_IN_PATH, NO_ACCESS_PATH, VERSION_FILE_PATH})


def admission_for(issuer: str) -> AdmissionConfig:
    """Who is admitted, for a sign-in and for a token alike: the login group, and no admins."""
    return AdmissionConfig(bound_issuer=issuer, login_group=LOGIN_GROUP, admin_group=NoAdmins.IN_THIS_APP)


def session_gate(sessions: SessionRecordStore, resource_rule: PublicRule) -> SessionGate:
    # Each call takes the stores' shared guard, so a sign-in entry in progress holds this call back.
    return SessionGate(
        session_transaction=lambda: nullcontext(sessions),
        login_redirect=LoginRedirect(LOGIN_PATH, RETURN_PATH_QUERY_NAME),
        public=(
            PublicRule(PathRules(exact=PUBLIC_PATHS)),
            PublicRule(IMMUTABLE_ASSET_PATH_RULES),
            resource_rule,
        ),
    )
