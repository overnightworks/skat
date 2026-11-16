"""A person's reaction at the table: thrown from the tray or set off by a tap on an object of the table.

The reaction changes nothing stored and moves no table version; the table's streams are woken so that every page at the
table, a watcher's included, reads it in its answer's `reactions` and plays it. The reactions live in the `ReactionLog`
of the presence; the rules are `skat.table.reacting`.
"""

from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from skat.table.reacting import Reaction, ReactionRefusal, reaction_refusal, throwing_seat
from skat.web.mcp import THROW_REACTION_MARK
from skat.web.tables import TABLES_PATH, RefusalAnswer, TableIdInPath, actor_of

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# A reaction thrown at a table: `TABLES_PATH/{table_id}` plus this.
TABLE_REACTION_SUFFIX: Final = "/reaction"

TOO_MANY_REQUESTS: Final = 429

REACTION_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    404: {"description": "No table has this id."},
    409: {"model": RefusalAnswer, "description": "The caller neither sits at the table nor has it open."},
    TOO_MANY_REQUESTS: {"model": RefusalAnswer, "description": "The caller threw too many reactions lately."},
}

_REFUSAL_STATUS: Final = {ReactionRefusal.NOT_AT_THE_TABLE: 409, ReactionRefusal.TOO_FAST: TOO_MANY_REQUESTS}


class ReactionBody(BaseModel):
    """What a person throws; who throws it comes from the session."""

    model_config = ConfigDict(extra="forbid")

    reaction: Reaction


class ReactionThrownAnswer(BaseModel):
    """The throw's number at the table, as the table's `reactions` carry it."""

    number: int


def create_reacting_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_REACTION_SUFFIX,
        response_model=ReactionThrownAnswer,
        responses=REACTION_RESPONSES,
        openapi_extra=THROW_REACTION_MARK,
    )
    async def throw_reaction(
        table_id: TableIdInPath, body: ReactionBody, request: Request, response: Response
    ) -> Response | ReactionThrownAnswer:
        """Throw a reaction at the table, for everyone at it to see and hear; it changes nothing at the table.

        Send the table's `table_id` and one `reaction` of the set: the emotes `clap`, `laugh`, `gasp`, `fire`, `cheers`
        and `knock`, or a tap on an object of the table, `cocktail`, `shell`, `coaster` or `lamp`. You may throw it when
        you sit at the table; the pages of everyone at it show and play it. A throw is refused with `too-fast` when you
        threw too many lately, at any table, and with `not-at-the-table` when you do not sit at it.
        """
        response.headers["Cache-Control"] = "no-store"
        actor = actor_of(request)
        view = await run_in_threadpool(tables.view, actor, table_id, presence.connected(table_id))
        if view is None:
            raise HTTPException(status_code=404, detail="table not found")
        log = presence.reactions
        # The decision and the record follow each other on the event loop with no await between them.
        refusal = reaction_refusal(
            view,
            watching=actor.account_id in presence.connected(table_id),
            thrown_at=log.thrown_by(actor.account_id),
            now=log.now(),
        )
        if refusal is not None:
            answer = RefusalAnswer(reason=refusal, holder_name=None)
            return JSONResponse(
                answer.model_dump(mode="json"),
                status_code=_REFUSAL_STATUS[refusal],
                headers={"Cache-Control": "no-store"},
            )
        number = log.throw(table_id, actor.account_id, body.reaction, throwing_seat(view))
        presence.wake_table(table_id)
        return ReactionThrownAnswer(number=number)

    return router
