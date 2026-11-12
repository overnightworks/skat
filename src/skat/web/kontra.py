from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.engine.kontra import Word  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.kontra import KontraCommand
from skat.web.mcp import SAY_KONTRA_MARK, SAY_NO_WORD_MARK
from skat.web.tables import COMMAND_RESPONSES, TABLES_PATH, CommandRequest, TableAnswer, actor_of, command_answer

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# A word said on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_KONTRA_SUFFIX: Final = "/kontra"
# The answer that a seat says no word now: `TABLES_PATH/{table_id}` plus this.
TABLE_NO_WORD_SUFFIX: Final = TABLE_KONTRA_SUFFIX + "/no-word"


class KontraRequest(CommandRequest):
    """A client names the word and the version it saw: its seat and position come from the session."""

    version: Annotated[int, Field(strict=True)]
    word: Word


class NoWordRequest(CommandRequest):
    """A client names the version it saw: its seat and position come from the session."""

    version: Annotated[int, Field(strict=True)]


def create_kontra_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_KONTRA_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=SAY_KONTRA_MARK,
    )
    async def say_kontra(
        table_id: str, body: KontraRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say Kontra, Re, Supra or Hirsch at a Skat table that plays Kontra; each word doubles the game's list score
        once more.

        An opponent says Kontra, the declarer answers with Re, the opponent who said Kontra with Supra and the declarer
        with Hirsch, as far as the table's `options.kontra.reach` allows. Send the word `hand.playing.kontra.my_word`
        names in the answer of read_table or the state of your table's view; a word stays open until the caller plays
        his next card, and play never waits for it. The table id and the version come from that answer. The command id
        names this step: the same id with the same word and the same version is a retry that changes nothing twice. A
        refusal (a stale version, not the caller's word, too late, beyond the table's reach, an opponent who did not bid
        where the table asks it, a table without Kontra, an opponent's give-up waiting for the declarer) comes back as a
        failed result with its reason, leaves the table as it was and spends the command id: the next attempt takes a
        new command id.
        """
        command = KontraCommand(command_id=body.command_id, table_id=table_id, version=body.version, word=body.word)
        return await command_answer(
            partial(tables.say_kontra, actor_of(request), command), presence, table_id, response
        )

    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_NO_WORD_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=SAY_NO_WORD_MARK,
    )
    async def say_no_word(
        table_id: str, body: NoWordRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say that the caller's seat says no word now: it answers the word `hand.playing.kontra.my_word` names, so
        that the table stops asking for it, and the answer shows in `my_word_answered` of the caller's own view.

        The word stays open: the caller may still say it until he plays his next card, and play never waits for it.
        Answering a second time changes nothing. The table id and the version come from the answer of read_table or
        the state of your table's view. The command id names this step: the same id with the same version is a retry
        that changes nothing twice. A refusal (a stale version, not the caller's word, too late, beyond the table's
        reach, an opponent who did not bid where the table asks it, a table without Kontra, an opponent's give-up
        waiting for the declarer) comes back as a failed result with its reason, leaves the table as it was and spends
        the command id: the next attempt takes a new command id.
        """
        command = KontraCommand(command_id=body.command_id, table_id=table_id, version=body.version, word=None)
        return await command_answer(
            partial(tables.say_kontra, actor_of(request), command), presence, table_id, response
        )

    return router
