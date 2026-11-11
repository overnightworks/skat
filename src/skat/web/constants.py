import re

from webauth.policies import PathRules
from webauth.sign_in_routes import SignInPaths

DEFAULT_HOST = "0.0.0.0"  # noqa: S104 - the container must listen on every interface and SKAT_HOST overrides it
DEFAULT_PORT = 8080

HOME_PATH = "/"
HEALTH_PATH = "/health"
APP_ASSET_PATH = "/_app"
IMMUTABLE_ASSET_DIRECTORY = "immutable"
# SvelteKit's client fetches it whenever a page regains focus; it holds only the build's id.
VERSION_FILE_PATH = f"{APP_ASSET_PATH}/version.json"
ACCOUNT_PATH = "/api/account"
ACCOUNT_CONSOLE_PATH = "/account"
AUTH_START_PATH = "/auth/start"
AUTH_CALLBACK_PATH = "/auth/callback"
LOGIN_PATH = "/login"
# The sign-in page a table framed by the call opens; the call mode is the agreed marker of such a table address.
CALL_SIGN_IN_PATH = "/login/call"
MODE_QUERY_NAME = "mode"
CALL_MODE = "call"
NO_ACCESS_PATH = "/no-access"
LOGOUT_PATH = "/logout"
# The sign-in page ignores it; the gate's redirect type requires a name for the address the visitor asked for.
RETURN_PATH_QUERY_NAME = "next"
# A table page opened through an automatic sign-in carries it, so the page can tell a refusal right after
# that sign-in from the first one without keeping anything on the device.
SIGNED_IN_AGAIN_QUERY_NAME = "signedInAgain"
BACKCHANNEL_LOGOUT_PATH = "/auth/backchannel-logout"
SIGN_IN_PATHS = SignInPaths(
    start=AUTH_START_PATH, callback=AUTH_CALLBACK_PATH, logout=LOGOUT_PATH, backchannel_logout=BACKCHANNEL_LOGOUT_PATH
)

# The immutable files of the page build set their own header on success (routes.py): a rule here would also
# stamp it onto the 401, 429 and 404 that the same path can answer. Every other build file is revalidated.
NO_CACHE_PATH_RULES = PathRules(
    exact=frozenset({HOME_PATH, LOGIN_PATH, CALL_SIGN_IN_PATH, NO_ACCESS_PATH}),
    patterns=(re.compile(rf"^{APP_ASSET_PATH}/(?!{IMMUTABLE_ASSET_DIRECTORY}/)"),),
)
IMMUTABLE_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
# Every file of the build's immutable directory is public; a segment never starts with a dot or holds an escape.
_IMMUTABLE_SEGMENT = r"[A-Za-z0-9_-][A-Za-z0-9._-]*"
IMMUTABLE_ASSET_PATH_RULES = PathRules(
    patterns=(
        re.compile(rf"^{APP_ASSET_PATH}/{IMMUTABLE_ASSET_DIRECTORY}/(?:{_IMMUTABLE_SEGMENT}/)*{_IMMUTABLE_SEGMENT}\Z"),
    )
)

# SvelteKit 3.1.0 writes this one inline style on its route announcer (src/runtime/components/root.svelte):
# 'unsafe-hashes' with the hash of exactly that text admits it, and every other inline style stays refused.
ANNOUNCER_STYLE_SOURCES = ("'unsafe-hashes'", "'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo='")

OIDC_CLIENT_ID = "skat"
LOGIN_GROUP = "/apps/skat"
OIDC_SCOPES = ("openid", "profile", "groups")
OIDC_LEEWAY_SECONDS = 30
SESSION_LIFETIME_SECONDS = 12 * 60 * 60

# An open table stream admits its session again this often when nothing changes, so an ended session's stream
# stops within one interval.
STREAM_HEARTBEAT_SECONDS = 15

UVICORN_LOG_LEVEL = "warning"
# The server ends its open event streams itself when it stops; this limit is the backstop for any still open after that.
GRACEFUL_SHUTDOWN_SECONDS = 3
