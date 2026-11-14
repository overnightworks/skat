from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from skat.engine.kontra import Word  # noqa: TC001 - pydantic reads the field type at runtime
from skat.engine.value import Level  # noqa: TC001 - pydantic reads the field type at runtime
from skat.table.game_list import GameEnding, RamschResultView
from skat.web.declaration_tokens import ANNOUNCEMENT_TOKENS, GAME_TOKENS, AnnouncementToken, GameToken

if TYPE_CHECKING:
    from skat.table.game_list import ResultView


class MatadorsAnswer(BaseModel):
    mit: bool
    count: int


class SeatGainAnswer(BaseModel):
    seat: int
    gain: int
    won: bool


class KontraStepAnswer(BaseModel):
    word: Word
    factor: int


class KontraResultAnswer(BaseModel):
    steps: list[KontraStepAnswer]


class ResultAnswer(BaseModel):
    kind: Literal["declared"]
    ordinal: int
    declarer_seat: int
    game: GameToken
    hand: bool
    ouvert: bool
    announcement: AnnouncementToken
    schneider: bool
    schwarz: bool
    matadors: MatadorsAnswer | None
    base_value: int | None
    levels: list[Level]
    multiplier: int | None
    list_bonus: int
    announcement_missed: bool
    won: bool
    doubled: bool
    overbid: bool
    bid: int
    game_value: int
    settled_value: int
    score: int
    declarer_points: int
    opponents_points: int
    gains: list[SeatGainAnswer]
    kontra: KontraResultAnswer | None
    bock_factor: int
    ending: GameEnding
    ended_by_seat: int | None


class RamschSeatAnswer(BaseModel):
    seat: int
    points: int
    score: int


class RamschResultAnswer(BaseModel):
    kind: Literal["ramsch"]
    ordinal: int
    seats: list[RamschSeatAnswer]
    durchmarsch_seat: int | None
    jungfrau: bool
    bock_factor: int
    pushes: int
    push_factor: int
    divided_by_ten: bool


def result_answer_of(result: ResultView | RamschResultView | None) -> ResultAnswer | RamschResultAnswer | None:
    if result is None:
        return None
    if isinstance(result, RamschResultView):
        return RamschResultAnswer(
            kind="ramsch",
            ordinal=result.ordinal,
            seats=[RamschSeatAnswer(seat=each.seat, points=each.points, score=each.score) for each in result.seats],
            durchmarsch_seat=result.durchmarsch_seat,
            jungfrau=result.jungfrau,
            bock_factor=result.bock_factor,
            pushes=result.pushes,
            push_factor=result.push_factor,
            divided_by_ten=result.divided_by_ten,
        )
    declaration, matadors = result.declaration, result.matadors
    return ResultAnswer(
        kind="declared",
        ordinal=result.ordinal,
        declarer_seat=result.declarer_seat,
        game=GAME_TOKENS[declaration.kind],
        hand=declaration.hand,
        ouvert=declaration.ouvert,
        announcement=ANNOUNCEMENT_TOKENS[declaration.announcement],
        schneider=result.schneider,
        schwarz=result.schwarz,
        matadors=None if matadors is None else MatadorsAnswer(mit=matadors.mit, count=matadors.count),
        base_value=result.base_value,
        levels=list(result.levels),
        multiplier=result.multiplier,
        list_bonus=result.list_bonus,
        announcement_missed=result.announcement_missed,
        won=result.won,
        doubled=result.doubled,
        overbid=result.overbid,
        bid=result.bid,
        game_value=result.game_value,
        settled_value=result.settled_value,
        score=result.score,
        declarer_points=result.declarer_points,
        opponents_points=result.opponents_points,
        gains=[SeatGainAnswer(seat=gain.seat, gain=gain.gain, won=gain.won) for gain in result.gains],
        kontra=None
        if result.kontra is None
        else KontraResultAnswer(
            steps=[KontraStepAnswer(word=step.word, factor=step.factor) for step in result.kontra.steps]
        ),
        bock_factor=result.bock_factor,
        ending=result.ending,
        ended_by_seat=result.ended_by_seat,
    )
