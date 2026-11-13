from functools import partial
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request, Response

from skat.table.hand_abort import AbortVoteCommand
from skat.web.mcp import AGREE_TO_ABORT_HAND_MARK, REFUSE_TO_ABORT_HAND_MARK
from skat.web.tables import (
    COMMAND_RESPONSES,
    TABLES_PATH,
    CommandRequest,
    TableAnswer,
    actor_of,
    command_answer,
)

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# A yes to aborting the running hand: `TABLES_PATH/{table_id}` plus this.
TABLE_ABORT_AGREE_SUFFIX: Final = "/abort/agree"
# A no to aborting the running hand: `TABLES_PATH/{table_id}` plus this.
TABLE_ABORT_REFUSE_SUFFIX: Final = "/abort/refuse"


def create_abort_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_ABORT_AGREE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=AGREE_TO_ABORT_HAND_MARK,
    )
    async def agree_to_abort_hand(
        table_id: str, body: CommandRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say yes to aborting the running hand of a Skat table while one of its chairs is open.

        A hand with an open chair (`hand.abortable` true, `hand.waiting_seat` set, whether a send-away or a stand-up
        opened it) stands still and may be aborted by the seated players. The first yes proposes it and `hand.abort`
        names the seats that said yes; once the yeses are more than half of the seated chairs (one of one, two of
        two) the hand ends at once with no game-list entry and no result, counts as a deal and as a Bock game, and
        the answer's `aborted` is set. A chair freed or taken meanwhile counts as it is then. Use it from the
        caller's chair when read_table or your table's view shows `hand.abortable`. The command id names this step:
        the same id is a retry that changes nothing twice. A refusal (not seated, no hand, no open chair) comes back
        as a failed result with its reason and spends the command id.
        """
        command = AbortVoteCommand(command_id=body.command_id, table_id=table_id)
        return await command_answer(
            partial(tables.agree_to_abort_hand, actor_of(request), command), presence, table_id, response
        )

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_ABORT_REFUSE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=REFUSE_TO_ABORT_HAND_MARK,
    )
    async def refuse_to_abort_hand(
        table_id: str, body: CommandRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say no to the proposal to abort the running hand of a Skat table: the proposal goes and the hand keeps
        waiting for a sitter.

        Use it from the caller's chair when read_table or your table's view shows `hand.abort`. The command id names
        this step: the same id is a retry that changes nothing twice. A refusal (not seated, no proposal) comes back
        as a failed result with its reason and spends the command id.
        """
        command = AbortVoteCommand(command_id=body.command_id, table_id=table_id)
        return await command_answer(
            partial(tables.refuse_to_abort_hand, actor_of(request), command), presence, table_id, response
        )

    return router
