from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel

from skat.table.records import EndReason
from skat.web.series_answer import StandingAnswer, standing_answer_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skat.table.views import EndedView


class EmptyNoGamesAnswer(BaseModel):
    """A table nobody was at for `empty_seconds` whole seconds while no hand was dealt, which finished no game."""

    reason: Literal[EndReason.EMPTY]
    empty_seconds: int
    unplayed_days: None
    closed_by_name: None
    standings: None
    game_count: None


class EmptyWithGamesAnswer(BaseModel):
    """A table nobody was at for `empty_seconds` whole seconds, with the games its last series played and their
    standings.
    """

    reason: Literal[EndReason.EMPTY]
    empty_seconds: int
    unplayed_days: None
    closed_by_name: None
    standings: list[StandingAnswer]
    game_count: int


class UnplayedNoGamesAnswer(BaseModel):
    """A table nobody played at for `unplayed_days` days, which finished no game."""

    reason: Literal[EndReason.UNPLAYED]
    empty_seconds: None
    unplayed_days: int
    closed_by_name: None
    standings: None
    game_count: None


class UnplayedWithGamesAnswer(BaseModel):
    """A table nobody played at for `unplayed_days` days, with the games its last series played and their
    standings.
    """

    reason: Literal[EndReason.UNPLAYED]
    empty_seconds: None
    unplayed_days: int
    closed_by_name: None
    standings: list[StandingAnswer]
    game_count: int


class ClosedNoGamesAnswer(BaseModel):
    """A table that finished no game and was closed: `closed_by_name` is the opener who closed it before „Aufhören“,
    null once the days of the link's reason have passed, and for a table whose series ended by „Aufhören“ or by a
    silent seat, which is a close that names nobody.
    """

    reason: Literal[EndReason.CLOSED]
    empty_seconds: None
    unplayed_days: None
    closed_by_name: str | None
    standings: None
    game_count: None


class ClosedWithGamesAnswer(BaseModel):
    """A table closed after it finished a game: it carries the games its last series played and their standings, and
    names nobody who closed it.
    """

    reason: Literal[EndReason.CLOSED]
    empty_seconds: None
    unplayed_days: None
    closed_by_name: None
    standings: list[StandingAnswer]
    game_count: int


# Why a table ended with the one fact stored when it ended; the six shapes keep every key in this order.
EndedAnswer = (
    EmptyNoGamesAnswer
    | EmptyWithGamesAnswer
    | UnplayedNoGamesAnswer
    | UnplayedWithGamesAnswer
    | ClosedNoGamesAnswer
    | ClosedWithGamesAnswer
)
_ENDED_ANSWER_MODELS: Final[Mapping[tuple[EndReason, bool], type[EndedAnswer]]] = {
    (EndReason.EMPTY, False): EmptyNoGamesAnswer,
    (EndReason.EMPTY, True): EmptyWithGamesAnswer,
    (EndReason.UNPLAYED, False): UnplayedNoGamesAnswer,
    (EndReason.UNPLAYED, True): UnplayedWithGamesAnswer,
    (EndReason.CLOSED, False): ClosedNoGamesAnswer,
    (EndReason.CLOSED, True): ClosedWithGamesAnswer,
}


def ended_answer_of(ended: EndedView | None) -> EndedAnswer | None:
    if ended is None:
        return None
    standings = None if ended.standings is None else [standing_answer_of(each) for each in ended.standings]
    return _ENDED_ANSWER_MODELS[ended.reason, standings is not None].model_validate(
        {
            "reason": ended.reason,
            "empty_seconds": ended.empty_seconds,
            "unplayed_days": ended.unplayed_days,
            "closed_by_name": ended.closed_by_name,
            "standings": standings,
            "game_count": ended.game_count,
        }
    )
