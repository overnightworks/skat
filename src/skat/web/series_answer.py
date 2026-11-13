from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from skat.table.game_list import Standing
    from skat.table.views import SeriesView


class StandingAnswer(BaseModel):
    display_name: str | None
    total: int
    won: int
    lost: int
    place: int


class SeriesEndProposalAnswer(BaseModel):
    proposer_seat: int
    accepter_seat: int | None


class SeriesAnswer(BaseModel):
    number: int
    game_number: int
    game_count: int
    over: bool
    standings: list[StandingAnswer] | None
    end_proposal: SeriesEndProposalAnswer | None


def standing_answer_of(standing: Standing) -> StandingAnswer:
    return StandingAnswer(
        display_name=standing.display_name,
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
            proposer_seat=series.end_proposal.proposer, accepter_seat=series.end_proposal.accepter
        ),
    )
