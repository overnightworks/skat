from typing import Final

from fastapi import APIRouter
from pydantic import BaseModel

from skat.web.mcp import Exclusion, excluded
from skat.web.routes import READ_METHODS

CALL_ORIGIN_PATH: Final = "/api/call-origin"


class CallOrigin(BaseModel):
    origin: str | None


def create_call_router(call_origin: str | None) -> APIRouter:
    router = APIRouter()

    @router.api_route(CALL_ORIGIN_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.CALL_ORIGIN))
    def call_origin_of_the_frame() -> CallOrigin:
        return CallOrigin(origin=call_origin)

    return router
