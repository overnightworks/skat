from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from webauth.middleware import admitted_user

from skat.web.constants import ACCOUNT_CONSOLE_PATH, ACCOUNT_PATH
from skat.web.mcp import Exclusion, excluded
from skat.web.routes import READ_METHODS


class AccountName(BaseModel):
    name: str


def create_account_router(oidc_issuer: str) -> APIRouter:
    router = APIRouter()

    @router.api_route(ACCOUNT_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.ACCOUNT_NAME))
    def account(request: Request, response: Response) -> AccountName:
        user = admitted_user(request)
        # The gate refuses a request without a session before the route runs, so a missing user is a wiring fault.
        if user is None:  # pragma: no cover
            message = "The account route ran without an admitted user."
            raise RuntimeError(message)
        # The answer names the session's person, so no cache may keep it past the gate.
        response.headers["Cache-Control"] = "no-store"
        return AccountName(name=user.username)

    # The target comes from configuration, never from the request, so the redirect cannot be steered elsewhere.
    @router.api_route(ACCOUNT_CONSOLE_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.BROWSER_PAGE))
    def account_console() -> RedirectResponse:
        return RedirectResponse(f"{oidc_issuer}/account", status_code=303)

    return router
