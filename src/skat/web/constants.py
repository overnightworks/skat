import re

from webauth.policies import PathRules, RateLimitBudget
from webauth.sign_in_routes import SignInPaths

DEFAULT_HOST = "0.0.0.0"  # noqa: S104 - the container must listen on every interface and SKAT_HOST overrides it
DEFAULT_PORT = 8080

HOME_PATH = "/"
HEALTH_PATH = "/health"
APP_ASSET_PATH = "/_app"
IMMUTABLE_ASSET_DIRECTORY = "immutable"
ACCOUNT_PATH = "/api/account"
ACCOUNT_CONSOLE_PATH = "/account"
AUTH_START_PATH = "/auth/start"
AUTH_CALLBACK_PATH = "/auth/callback"
LOGIN_PATH = "/login"
NO_ACCESS_PATH = "/no-access"
LOGOUT_PATH = "/logout"
# The sign-in page ignores it; the gate's redirect type requires a name for the address the visitor asked for.
RETURN_PATH_QUERY_NAME = "next"
BACKCHANNEL_LOGOUT_PATH = "/auth/backchannel-logout"
SIGN_IN_PATHS = SignInPaths(
    start=AUTH_START_PATH, callback=AUTH_CALLBACK_PATH, logout=LOGOUT_PATH, backchannel_logout=BACKCHANNEL_LOGOUT_PATH
)
DEFAULT_REQUEST_BODY_MAX_BYTES = 4 * 1024
# A complete sign-in is two requests, so 40 requests in ten minutes admit 20 sign-ins from one address.
SIGN_IN_RATE_LIMIT_BUDGET = RateLimitBudget(name="sign-in", max_requests=40, window_seconds=10 * 60)
DEFAULT_RATE_LIMIT_BUDGET = RateLimitBudget(name="requests", max_requests=600, window_seconds=60)
# The health check is the edge's readiness probe; the back-channel logout comes from Keycloak's shared addresses.
RATE_LIMIT_EXEMPT_PATH_RULES = PathRules(exact=SIGN_IN_PATHS.backchannel.exact | {HEALTH_PATH})

# The immutable files of the page build set their own header on success (routes.py): a rule here would also
# stamp it onto the 401, 429 and 404 that the same path can answer. Every other build file is revalidated.
NO_CACHE_PATH_RULES = PathRules(
    exact=frozenset({HOME_PATH, LOGIN_PATH, NO_ACCESS_PATH}),
    patterns=(re.compile(rf"^{APP_ASSET_PATH}/(?!{IMMUTABLE_ASSET_DIRECTORY}/)"),),
)
# Private, because the assets sit behind the sign-in and a shared cache would hand them out past it (RFC 9111 5.2.2.9).
IMMUTABLE_ASSET_CACHE_CONTROL = "private, max-age=31536000, immutable"

# The page asks for no device; every capability a browser could grant stays off.
PERMISSIONS_POLICY = "camera=(), microphone=(), display-capture=(), geolocation=()"
# SvelteKit 3.1.0 writes this one inline style on its route announcer (src/runtime/components/root.svelte):
# 'unsafe-hashes' with the hash of exactly that text admits it, and every other inline style stays refused.
ANNOUNCER_STYLE_SOURCES = ("'unsafe-hashes'", "'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo='")

OIDC_CLIENT_ID = "skat"
LOGIN_GROUP = "/apps/skat"
OIDC_SCOPES = ("openid", "profile", "groups")
OIDC_LEEWAY_SECONDS = 30
SESSION_LIFETIME_SECONDS = 12 * 60 * 60
SESSION_SWEEP_SECONDS = 10 * 60

UVICORN_LOG_LEVEL = "warning"
