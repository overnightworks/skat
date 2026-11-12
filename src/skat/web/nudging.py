"""A seated player's nudge of the seat the table waits for.

The nudge changes nothing stored and moves no table version; the table's streams are woken so that every page reads
the chair's new state, and an agent in the nudged seat is told on its view's URI at once. The nudges live in the
`AskClock` of the presence; the rules are `skat.table.nudging`.
"""

from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from skat.table.nudging import NUDGES_PER_VERSION, NudgeRefusal, NudgeRequest, is_retry, nudge_refusal
from skat.table.rules import CHAIRS_PER_TABLE
from skat.web.mcp import NUDGE_SEAT_MARK
from skat.web.tables import TABLES_PATH, RefusalAnswer, TableAnswer, actor_of, answer_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.table.service import TableService
    from skat.web.presence import Presence

# A nudge of a seat the table waits for: `TABLES_PATH/{table_id}` plus this.
TABLE_NUDGE_SUFFIX: Final = "/nudge"

NUDGE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    404: {"description": "No table has this id."},
    409: {"model": RefusalAnswer, "description": "The nudge changed nothing; the reason says why."},
}


class NudgeBody(BaseModel):
    """What a nudger read: the table's version, the seat it nudges and how many nudges that seat had then."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[int, Field(strict=True)]
    seat: Annotated[int, Field(strict=True, ge=1, le=CHAIRS_PER_TABLE)]
    nudges: Annotated[int, Field(strict=True, ge=0, le=NUDGES_PER_VERSION)]


def create_nudging_router(
    tables: TableService, presence: Presence, tell_agent: Callable[[str, str], None]
) -> APIRouter:
    """The nudge route; `tell_agent(table_id, account_id)` tells an agent its view changed, on the event loop."""
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_NUDGE_SUFFIX,
        response_model=TableAnswer,
        responses=NUDGE_RESPONSES,
        openapi_extra=NUDGE_SEAT_MARK,
    )
    async def nudge_seat(
        table_id: str, body: NudgeBody, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Nudge a seat the table is waiting for, to ask it to act; it changes nothing at the table.

        Nudge a chair whose `nudge.may_nudge` is true in the answer of read_table or your table's view, when you sit at
        the table and the chair is not yours. Send the table's `version`, the chair's `seat` and `nudges`, the count
        `nudge.nudges` showed. A nudge is accepted one minute after the table began to wait at that version, and a
        second one a minute after the first; at most two per chair and version. Earlier it is refused with
        `too-early` and changes nothing; no wake tells you when the minute is over. The same request again is a retry
        that changes nothing twice. A refusal (`not-seated`, `stale-version`, `seat-open`, `not-waiting`, `own-seat`,
        `away`, `too-early`, `already-nudged`) leaves the table as it was. The answer is the table as read_table
        gives it. A nudged agent is woken to read its view again; a nudged person sees the nudge on the page.
        """
        response.headers["Cache-Control"] = "no-store"
        waits = presence.waits
        # The standing, the decision and the record follow each other on the event loop with no await between them.
        with waits.reading(table_id):
            view = await run_in_threadpool(tables.view, actor_of(request), table_id, presence.connected(table_id))
            if view is None:
                raise HTTPException(status_code=404, detail="table not found")
            standing = waits.standing(view)
            asked = NudgeRequest(version=body.version, seat=body.seat, nudges=body.nudges)
            if standing is None:
                return _refused(NudgeRefusal.STALE_VERSION)
            waited, nudged = standing
            refusal = nudge_refusal(view, asked, waited, nudged)
            if refusal is not None:
                return _refused(refusal)
            if not is_retry(view, asked, nudged):
                nudger = next(chair.seat for chair in view.chairs if chair.is_mine)
                waits.nudge(table_id, body.seat, nudger, waited)
                presence.wake_table(table_id)
                agent = waits.agent_at(table_id, view.version, body.seat)
                if agent is not None:
                    tell_agent(table_id, agent)
            return answer_of(view, waits.nudges_of(view))

    return router


def _refused(refusal: NudgeRefusal) -> JSONResponse:
    answer = RefusalAnswer(reason=refusal, holder_name=None)
    return JSONResponse(answer.model_dump(mode="json"), status_code=409, headers={"Cache-Control": "no-store"})
