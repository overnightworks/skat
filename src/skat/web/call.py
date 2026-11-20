import hashlib
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from skat.web.mcp import Exclusion, excluded
from skat.web.routes import READ_METHODS
from skat.web.tables import TABLES_PATH, TableIdInPath

if TYPE_CHECKING:
    from skat.table.service import TableService

CALL_ORIGIN_PATH: Final = "/api/call-origin"
# The keys of a table's seated accounts: `TABLES_PATH/{table_id}` plus this.
TABLE_PERSON_KEYS_SUFFIX: Final = "/person-keys"
# The label that makes the key this app's and this derivation's alone; the call derives the same key from it.
PERSON_KEY_LABEL: Final = "hallucinai/skat/person-key/v1"


class CallOrigin(BaseModel):
    origin: str | None


class PersonKeyAnswer(BaseModel):
    seat: int
    key: str


class PersonKeysAnswer(BaseModel):
    version: int
    keys: list[PersonKeyAnswer]


def person_key(issuer: str, subject: str, table_id: str) -> str:
    """The pseudonym of an account at one table: hex SHA-256 over the label, issuer, subject and table, joined by NUL.
    Whoever holds the subject can derive it; to anyone else it is opaque and links no two tables.
    """
    return hashlib.sha256("\0".join((PERSON_KEY_LABEL, issuer, subject, table_id)).encode()).hexdigest()


def create_call_router(call_origin: str | None, issuer: str, tables: TableService) -> APIRouter:
    router = APIRouter()

    @router.api_route(CALL_ORIGIN_PATH, methods=READ_METHODS, openapi_extra=excluded(Exclusion.CALL_FRAME))
    def call_origin_of_the_frame() -> CallOrigin:
        return CallOrigin(origin=call_origin)

    @router.get(
        TABLES_PATH + "/{table_id}" + TABLE_PERSON_KEYS_SUFFIX,
        responses={404: {"description": "No live table has this id."}},
        openapi_extra=excluded(Exclusion.CALL_FRAME),
    )
    async def read_person_keys(table_id: TableIdInPath, response: Response) -> PersonKeysAnswer:
        """The version of the live table and the person key of the account in each occupied chair, in seat order. A
        free chair has no entry, and no account is named.
        """
        response.headers["Cache-Control"] = "no-store"
        seated = await run_in_threadpool(tables.seated_accounts, table_id)
        if seated is None:
            raise HTTPException(status_code=404, detail="table not found")
        return PersonKeysAnswer(
            version=seated.version,
            keys=[
                PersonKeyAnswer(seat=seat, key=person_key(issuer, account_id, table_id))
                for seat, account_id in sorted(seated.account_by_seat.items())
            ],
        )

    return router
