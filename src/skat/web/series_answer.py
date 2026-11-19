from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel

from skat.table.records import OccupantKind  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.series_end import END_ANSWER_SECONDS

if TYPE_CHECKING:
    from skat.table.game_list import Standing
    from skat.table.views import SeriesView


class StandingAnswer(BaseModel):
    display_name: str | None
    seat: int
    kind: OccupantKind | None
    total: int
    won: int
    lost: int
    place: int


class SeriesEndProposalAnswer(BaseModel):
    proposer_seat: int
    agreed_seats: list[int]
    answer_by: datetime


class SeriesAnswer(BaseModel):
    number: int
    game_number: int
    game_count: int
    over: bool
    standings: list[StandingAnswer] | None
    end_proposal: SeriesEndProposalAnswer | None
    end_refused_seats: list[int]


def standing_answer_of(standing: Standing) -> StandingAnswer:
    return StandingAnswer(
        display_name=standing.display_name,
        seat=standing.seat,
        kind=standing.kind,
        total=standing.total,
        won=standing.won,
        lost=standing.lost,
        place=standing.place,
    )


def series_answer_of(series: SeriesView | None) -> SeriesAnswer | None:
    if series is None:
        return None
    return SeriesAnswer(
        number=series.number,
        game_number=series.game_number,
        game_count=series.game_count,
        over=series.over,
        standings=None if series.standings is None else [standing_answer_of(each) for each in series.standings],
        end_proposal=None
        if series.end_proposal is None
        else SeriesEndProposalAnswer(
            proposer_seat=series.end_proposal.proposer,
            agreed_seats=sorted(series.end_proposal.agreed),
            answer_by=series.end_proposal.asked_at + timedelta(seconds=END_ANSWER_SECONDS),
        ),
        end_refused_seats=sorted(series.end_refused_by),
    )
