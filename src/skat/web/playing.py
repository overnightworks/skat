from functools import partial
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Request, Response

from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    GiveUpCommand,
    PlayCardCommand,
    PlayOpenCommand,
    ShortenCommand,
    ThrowDownCommand,
)
from skat.web.mcp import (
    AGREE_TO_GIVE_UP_MARK,
    DECLINE_GIVE_UP_MARK,
    GIVE_UP_GAME_MARK,
    PLAY_CARD_MARK,
    PLAY_OPEN_MARK,
    SHORTEN_GAME_MARK,
    THROW_DOWN_CARDS_MARK,
)
from skat.web.tables import (
    ANNOUNCEMENTS_OF_TOKEN,
    COMMAND_RESPONSES,
    TABLES_PATH,
    AnnouncementToken,
    CardChoice,
    CommandId,
    CommandRequest,
    TableAnswer,
    TableIdInPath,
    TableVersion,
    actor_of,
    card_of,
    command_answer,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.table.records import Actor
    from skat.table.service import TableService
    from skat.table.views import CommandResult
    from skat.web.presence import Presence

# A card played on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_CARD_SUFFIX: Final = "/card"
# The declarer's give-up on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_GIVE_UP_SUFFIX: Final = "/give-up"
# The declarer's shortening on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_SHORTEN_SUFFIX: Final = "/shorten"
# An opponent's open play on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_PLAY_OPEN_SUFFIX: Final = "/play-open"
# An opponent's yes to the declarer's give-up: `TABLES_PATH/{table_id}` plus this.
TABLE_GIVE_UP_AGREE_SUFFIX: Final = "/give-up/agree"
# An opponent's no to the declarer's give-up: `TABLES_PATH/{table_id}` plus this.
TABLE_GIVE_UP_DECLINE_SUFFIX: Final = "/give-up/decline"
# A side's throw-down on a table: `TABLES_PATH/{table_id}` plus this.
TABLE_THROW_DOWN_SUFFIX: Final = "/throw-down"


class PlayCardRequest(CardChoice):
    """A client names only the card and the version it saw: its seat and position come from the session."""

    command_id: CommandId
    version: TableVersion


class GiveUpRequest(CommandRequest):
    """A client names only the version it saw: it cannot send consent, and its seat comes from the session."""

    version: TableVersion


class ShortenRequest(CommandRequest):
    """A client names the version it saw and the level it demands, none by default: its seat comes from the session."""

    version: TableVersion
    claim: AnnouncementToken = AnnouncementToken.NONE


class PlayOpenRequest(CommandRequest):
    """A client names only the version it saw: its seat comes from the session, so it cannot play open for another."""

    version: TableVersion


class AgreeToGiveUpRequest(CommandRequest):
    """A client names only the version it saw: its seat comes from the session, so it cannot answer for another."""

    version: TableVersion


class DeclineGiveUpRequest(CommandRequest):
    """A client names only the version it saw: its seat comes from the session, so it cannot answer for another."""

    version: TableVersion


class ThrowDownRequest(CommandRequest):
    """A client names only the version it saw: its seat, and so its side, come from the session."""

    version: TableVersion


def create_playing_router(tables: TableService, presence: Presence) -> APIRouter:
    router = APIRouter()
    _add_play_card(router, tables, presence)
    _add_give_up(router, tables, presence)
    _add_shorten(router, tables, presence)
    _add_play_open(router, tables, presence)
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
        table_id: TableIdInPath, body: PlayCardRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Play one card from the caller's own hand on its turn at a Skat table.

        The card comes from the legal cards of read_table or your table's view. Refused: a stale version, a card that is
        not legal, not the caller's turn, an opponent's give-up waiting for the declarer.
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
        table_id: TableIdInPath, body: GiveUpRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Give up the game for the caller's side, as the declarer or as an opponent; this cannot be undone.

        As the declarer: while the caller's chair holds nine or more cards the game is lost at once, valued as declared.
        With fewer, the opponents are asked: `hand.playing.give_up` in read_table names the asking seat and an
        opponent's seat that said no. The game ends once one opponent agrees, lost as declared, or won as it stands if
        the caller's tricks and the skat already win it. A card played, or a no from both, ends the request and play
        goes on. From an opponent's chair it gives up your side's defence at any moment: the game waits for the
        declarer, who accepts the end or demands play on; meanwhile no card is taken. Use it once a declared game is
        played (`hand.declaring.declaration` is set in the answer of read_table or the state of your table's view), from
        any chair of the table that is marked `is_mine`, on anyone's turn. Refused: a stale version, another request
        waiting.
        """
        command = GiveUpCommand(command_id=body.command_id, table_id=table_id, version=body.version)
        return await command_answer(
            partial(tables.give_up, actor_of(request), command),
            presence,
            table_id,
            response,
        )


def _add_shorten(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_SHORTEN_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=SHORTEN_GAME_MARK,
    )
    async def shorten_game(
        table_id: TableIdInPath, body: ShortenRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Shorten the game as the declarer: ask both opponents to end it now, optionally demanding a level.

        `claim` is "none" or the level "schneider" or "schwarz" the declarer demands on top of his declared game. A
        level the opponents' completed tricks have already put out of reach, and any level in a Null game, is refused
        `claim-out-of-reach` before anyone is asked. Otherwise `hand.playing.shortening` in read_table names the asking
        seat, the level and the opponent who said yes so far; the opponents answer with agree_to_give_up and
        decline_give_up. The game ends once both agree: lost as it stands if it is already lost, won with its real
        result if it is already won and no level is demanded, else won as declared plus the demanded level. One no from
        either opponent ends the attempt: the game plays on, scored by its play alone, and the declarer's remaining
        cards are open to every viewer (`hand.declaring.open_cards`) with `hand.playing.shortening_refused_seat` naming
        the opponent. No card is shown while the opponents decide. A card played ends a request standing. Use it as the
        declarer once a declared game is played (`hand.declaring.declaration` is set in the answer of read_table or the
        state of your table's view). Refused: a stale version, not the declarer, another request waiting, a level out of
        reach.
        """
        command = ShortenCommand(
            command_id=body.command_id,
            table_id=table_id,
            version=body.version,
            claim=ANNOUNCEMENTS_OF_TOKEN[body.claim],
        )
        return await command_answer(
            partial(tables.shorten, actor_of(request), command),
            presence,
            table_id,
            response,
        )


async def _actor_command_answer[Command](
    run: Callable[[Actor, Command, frozenset[str]], CommandResult | None],
    command: Command,
    request: Request,
    presence: Presence,
    table_id: str,
    response: Response,
) -> Response | TableAnswer:
    """`command_answer` for a command the request's session actor gives."""
    return await command_answer(partial(run, actor_of(request), command), presence, table_id, response)


def _add_play_open(router: APIRouter, tables: TableService, presence: Presence) -> None:
    @router.post(
        TABLES_PATH + "/{table_id}" + TABLE_PLAY_OPEN_SUFFIX,
        response_model=TableAnswer,
        responses=COMMAND_RESPONSES,
        openapi_extra=PLAY_OPEN_MARK,
    )
    async def play_open(
        table_id: TableIdInPath, body: PlayOpenRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Play open as an opponent: show that the declarer can take no further trick, whatever the two opponents play.

        The engine checks the position from the hidden hands at once. Where the declarer could take no further trick the
        game ends, the rest goes to the opponents and the list entry says it ended by an open play. Otherwise the open
        play was wrong: nothing is shown yet, `hand.playing.open_play_seat` names the opponent and the game waits for
        the declarer, who accepts the end with agree_to_give_up (scored as an opponent's give-up: won as it stands, lost
        as it stands, or won as declared plus the level the bid forces) or demands play on with decline_give_up. That
        the declarer is asked at all tells everyone that he could still take a trick. Use it as an opponent once a
        declared game is played (`hand.declaring.declaration` is set in the answer of read_table or the state of your
        table's view), on anyone's turn. Refused: a stale version, the declarer, another request waiting, not seated.
        """
        return await _actor_command_answer(
            tables.play_open,
            PlayOpenCommand(command_id=body.command_id, table_id=table_id, version=body.version),
            request,
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
        table_id: TableIdInPath, body: AgreeToGiveUpRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Agree to the other side's give-up or shortening: from an opponent's chair that the declarer gives up or
        shortens, from the declarer's chair that the opponents give up; the game ends at once and joins the list.

        When the declarer gave up it is lost for him as declared, or won as it stands if his tricks and the skat already
        win it; one opponent's yes is enough, also after saying no. When the opponents gave up it is won for him as
        declared plus the level the bid forces, unless the game was already decided; the declarer's yes to an opponent's
        wrong open play (`hand.playing.open_play_seat`) ends it the same way. This cannot be undone. Use it while
        `hand.playing.give_up`, `hand.playing.shortening` or `hand.playing.open_play_seat` is set in the answer of
        read_table or the state of your table's view. The declarer's shortening needs the yes of both opponents: the
        first is kept in `hand.playing.shortening`, a second yes of the same opponent is refused as already answered.
        Refused: a stale version, nothing asked, the asking side's own chair, not seated.
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
        table_id: TableIdInPath, body: DeclineGiveUpRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Say no to the other side's give-up or shortening: from an opponent's chair to the declarer's request, from
        the declarer's chair to the opponents' give-up, which demands play on; play goes on and the request counts as
        not made.

        Once both opponents said no to the declarer's give-up it ends, and a second no from the same chair changes
        nothing; the declarer's no ends the opponents' give-up at once. One opponent's no ends the declarer's shortening
        at once and opens the declarer's remaining cards to every viewer. The declarer's no to an opponent's wrong open
        play demands play on and opens that opponent's remaining cards to every viewer (`hand.playing.open_hands`). Use
        it while `hand.playing.give_up`, `hand.playing.shortening` or `hand.playing.open_play_seat` is set in the answer
        of read_table or the state of your table's view. The refusals are as for agree_to_give_up.
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
        table_id: TableIdInPath, body: ThrowDownRequest, request: Request, response: Response
    ) -> Response | TableAnswer:
        """Throw the caller's cards down and end the game at once for the caller's side; this cannot be undone.

        The caller's side keeps the tricks it has completed; every card in no completed trick, the trick in progress
        included, counts for the other side, and the skat for the declarer. No card is shown. Use it from the caller's
        chair once a declared game is played (`hand.declaring.declaration` is set in the answer of read_table or the
        state of your table's view), on anyone's turn, as declarer or as opponent. Refused: a stale version, no game in
        play, not seated, an opponent's give-up waiting for the declarer.
        """
        command = ThrowDownCommand(command_id=body.command_id, table_id=table_id, version=body.version)
        return await command_answer(
            partial(tables.throw_down, actor_of(request), command),
            presence,
            table_id,
            response,
        )
