from functools import partial
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Request, Response
from pydantic import Field

from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    GiveUpCommand,
    PlayCardCommand,
    ThrowDownCommand,
)
from skat.web.mcp import (
    AGREE_TO_GIVE_UP_MARK,
    DECLINE_GIVE_UP_MARK,
    GIVE_UP_GAME_MARK,
    PLAY_CARD_MARK,
    THROW_DOWN_CARDS_MARK,
)
from skat.web.tables import (
    COMMAND_ID_PATTERN,
    COMMAND_RESPONSES,
    TABLES_PATH,
    CardChoice,
    CommandRequest,
    TableAnswer,
    actor_of,
    card_of,
    command_answer,
)

if TYPE_CHECKING:
    from skat.table.service import TableService
    from skat.web.presence import Presence

# A card played on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_CARD_SUFFIX: Final = "/card"
# The declarer's give-up on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_GIVE_UP_SUFFIX: Final = "/give-up"
# An opponent's yes to the declarer's give-up: `TABLES_PATH/{table_id}` plus this.
TABLE_GIVE_UP_AGREE_SUFFIX: Final = "/give-up/agree"
# An opponent's no to the declarer's give-up: `TABLES_PATH/{table_id}` plus this.
TABLE_GIVE_UP_DECLINE_SUFFIX: Final = "/give-up/decline"
# A side's throw-down on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_THROW_DOWN_SUFFIX: Final = "/throw-down"


class PlayCardRequest(CardChoice):
    """A client names only the card and the version it saw: its seat and position come from the session."""

    command_id: Annotated[str, Field(pattern=COMMAND_ID_PATTERN)]
    version: Annotated[int, Field(strict=True)]


class GiveUpRequest(CommandRequest):
    """A client names only the version it saw: it cannot send consent, and its seat comes from the session."""

    version: Annotated[int, Field(strict=True)]


class AgreeToGiveUpRequest(CommandRequest):
    """A client names only the version it saw: its seat comes from the session, so it cannot answer for another."""

    version: Annotated[int, Field(strict=True)]


class DeclineGiveUpRequest(CommandRequest):
    """A client names only the version it saw: its seat comes from the session, so it cannot answer for another."""

    version: Annotated[int, Field(strict=True)]


class ThrowDownRequest(CommandRequest):
    """A client names only the version it saw: its seat, and so its side, come from the session."""

    version: Annotated[int, Field(strict=True)]


def create_playing_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()
    _add_play_card(router, tables, presence)
    _add_give_up(router, tables, presence)
    _add_agree_to_give_up(router, tables, presence)
    _add_decline_give_up(router, tables, presence)
    _add_throw_down(router, tables, presence)
    return router


def _add_play_card(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_CARD_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=PLAY_CARD_MARK,
    )
    async def play_card(
        table_id: str, body: PlayCardRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Play one card from the caller's own hand on its turn at a Skat table.

        The table id and the version come from the answer of read_table or the state of your table's view, and the card
        from its legal cards. The command id names this move: the same id with the same card and the same version is a
        retry that changes nothing twice. A refusal (a stale version, a card that is not legal, not the caller's turn,
        an opponent's give-up waiting for the declarer) comes back as a failed result with its reason, leaves the table
        as it was and spends the command id: the next attempt takes a new command id.
        """
        command = PlayCardCommand(
            command_id=body.command_id, table_id=table_id, version=body.version, card=card_of(body)
        )
        return await command_answer(
            partial(tables.play_card, actor_of(request), command),
            presence,
            table_id,
            response,
        )


def _add_give_up(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_GIVE_UP_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=GIVE_UP_GAME_MARK,
    )
    async def give_up_game(
        table_id: str, body: GiveUpRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Give up the game for the caller's side, as the declarer or as an opponent; this cannot be undone.

        As the declarer: while the caller's chair holds nine or more cards the game is lost at once, valued as declared.
        With fewer, the opponents are asked: `hand.playing.give_up` in read_table names the asking seat and an
        opponent's seat that said no. The game ends once one opponent agrees, lost as declared, or won as it stands if
        the caller's tricks and the skat already win it. A card played, or a no from both, ends the request and play
        goes on. From an opponent's chair it gives up your side's defence at any moment: the game waits for the
        declarer, who accepts the end or demands play on; meanwhile no card is taken. Use it once a declared game is
        played (`hand.declaring.declaration` is set in the answer of read_table or the state of your table's view),
        from any chair of the table that is marked `is_mine`, on anyone's turn. The table id and the version come from
        that answer. The command id names this step: the same id with the same version is a retry that changes nothing
        twice. A refusal (a stale version, another request waiting) comes back as a failed result with its reason,
        leaves the table as it was and spends the command id: the next attempt takes a new command id.
        """
        command = GiveUpCommand(command_id=body.command_id, table_id=table_id, version=body.version)
        return await command_answer(
            partial(tables.give_up, actor_of(request), command),
            presence,
            table_id,
            response,
        )


def _add_agree_to_give_up(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_GIVE_UP_AGREE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=AGREE_TO_GIVE_UP_MARK,
    )
    async def agree_to_give_up(
        table_id: str, body: AgreeToGiveUpRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Agree to the other side's give-up: from an opponent's chair that the declarer gives up, from the declarer's
        chair that the opponents give up; the game ends at once and joins the list.

        When the declarer gave up it is lost for him as declared, or won as it stands if his tricks and the skat already
        win it; one opponent's yes is enough, also after saying no. When the opponents gave up it is won for him as
        declared plus the level the bid forces, unless the game was already decided. This cannot be undone. Use it while
        `hand.playing.give_up` is set in the answer of read_table or the state of your table's view. The table id and
        the version come from that answer. The command id names this step: the same id with the same version is a retry
        that changes nothing twice. A refusal (a stale version, nothing asked, the asking side's own chair, not seated)
        comes back as a failed result with its reason, leaves the table as it was and spends the command id: the next
        attempt takes a new command id.
        """
        command = AgreeToGiveUpCommand(command_id=body.command_id, table_id=table_id, version=body.version)
        return await command_answer(
            partial(tables.agree_to_give_up, actor_of(request), command),
            presence,
            table_id,
            response,
        )


def _add_decline_give_up(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_GIVE_UP_DECLINE_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=DECLINE_GIVE_UP_MARK,
    )
    async def decline_give_up(
        table_id: str, body: DeclineGiveUpRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say no to the other side's give-up: from an opponent's chair to the declarer's request, from the declarer's
        chair to the opponents' give-up, which demands play on; play goes on and the give-up counts as not made.

        Once both opponents said no to the declarer's request it ends, and a second no from the same chair changes
        nothing; the declarer's no ends the opponents' give-up at once. Use it while
        `hand.playing.give_up` is set in the answer of read_table or the state of your table's view. The table id, the
        version, the retry and the refusals are as for agree_to_give_up.
        """
        command = DeclineGiveUpCommand(command_id=body.command_id, table_id=table_id, version=body.version)
        return await command_answer(
            partial(tables.decline_give_up, actor_of(request), command),
            presence,
            table_id,
            response,
        )


def _add_throw_down(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_THROW_DOWN_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=THROW_DOWN_CARDS_MARK,
    )
    async def throw_down_cards(
        table_id: str, body: ThrowDownRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Throw the caller's cards down and end the game at once for the caller's side; this cannot be undone.

        The caller's side keeps the tricks it has completed; every card in no completed trick, the trick in progress
        included, counts for the other side, and the skat for the declarer. No card is shown. Use it from the
        caller's chair once a declared game is played (`hand.declaring.declaration` is set in the answer of
        read_table or the state of your table's view), on anyone's turn, as declarer or as opponent. The table id and
        the version come from that answer. The command id names this step: the same id with the same version is a
        retry that changes nothing twice. A refusal (a stale version, no game in play, not seated, an opponent's
        give-up waiting for the declarer) comes back as a failed result with its reason, leaves the table as it was and
        spends the command id: the next attempt takes a new command id.
        """
        command = ThrowDownCommand(command_id=body.command_id, table_id=table_id, version=body.version)
        return await command_answer(
            partial(tables.throw_down, actor_of(request), command),
            presence,
            table_id,
            response,
        )
