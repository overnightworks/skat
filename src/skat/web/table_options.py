from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from skat.engine.bock import BockOptions, BockOverlap, BockTrigger
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.table.records import RamschOccasion, RamschSetting, TableOptions


class KontraOptionsRequest(BaseModel):
    """The opener names all three Kontra choices or none: the program defaults none of them. The table accepts the
    deadline of the player's own next card only.
    """

    model_config = ConfigDict(extra="forbid")

    sayer: KontraSayer
    reach: KontraReach
    deadline: Literal[KontraDeadline.OWN_CARD]


class BockOptionsRequest(BaseModel):
    """The opener names the triggers, at least one and none twice, and what a trigger does inside a Bock round."""

    model_config = ConfigDict(extra="forbid")

    triggers: Annotated[list[BockTrigger], Field(min_length=1)]
    overlap: BockOverlap

    @field_validator("triggers")
    @classmethod
    def _names_each_trigger_once(cls, triggers: list[BockTrigger]) -> list[BockTrigger]:
        if len(set(triggers)) != len(triggers):
            message = "a trigger is named once"
            raise ValueError(message)
        return triggers


class RamschOptionsRequest(BaseModel):
    """The opener names all four Ramsch choices or none: the program defaults none of them. The table plays a Ramsch
    for a hand all three pass only.
    """

    model_config = ConfigDict(extra="forbid")

    occasion: Literal[RamschOccasion.PASSED_IN]
    scoring: RamschScoring
    jungfrau: JungfrauRule
    durchmarsch: DurchmarschRule


class OptionsRequest(BaseModel):
    """The rule options an opener sets; every later option joins this record.

    A table cannot play Ramsch and Bock rounds together: a Ramsch would have to use up a Bock game.
    """

    model_config = ConfigDict(extra="forbid")

    show_running_points: Annotated[bool, Field(strict=True)] = TableOptions().show_running_points
    kontra: KontraOptionsRequest | None = None
    bock: BockOptionsRequest | None = None
    ramsch: RamschOptionsRequest | None = None

    @model_validator(mode="after")
    def _plays_no_ramsch_with_bock(self) -> Self:
        if self.ramsch is not None and self.bock is not None:
            message = "a table plays no Ramsch and Bock rounds together"
            raise ValueError(message)
        return self


class KontraOptionsAnswer(BaseModel):
    sayer: KontraSayer
    reach: KontraReach
    deadline: KontraDeadline


class BockOptionsAnswer(BaseModel):
    triggers: list[BockTrigger]
    overlap: BockOverlap


class RamschOptionsAnswer(BaseModel):
    occasion: RamschOccasion
    scoring: RamschScoring
    jungfrau: JungfrauRule
    durchmarsch: DurchmarschRule


class OptionsAnswer(BaseModel):
    show_running_points: bool
    kontra: KontraOptionsAnswer | None
    bock: BockOptionsAnswer | None
    ramsch: RamschOptionsAnswer | None


def options_answer_of(options: TableOptions) -> OptionsAnswer:
    kontra, bock, ramsch = options.kontra, options.bock, options.ramsch
    return OptionsAnswer(
        show_running_points=options.show_running_points,
        kontra=None
        if kontra is None
        else KontraOptionsAnswer(sayer=kontra.sayer, reach=kontra.reach, deadline=kontra.deadline),
        bock=None if bock is None else BockOptionsAnswer(triggers=sorted(bock.triggers), overlap=bock.overlap),
        ramsch=None
        if ramsch is None
        else RamschOptionsAnswer(
            occasion=ramsch.occasion,
            scoring=ramsch.reckoning.scoring,
            jungfrau=ramsch.reckoning.jungfrau,
            durchmarsch=ramsch.reckoning.durchmarsch,
        ),
    )


def table_options_of(requested: OptionsRequest | None) -> TableOptions:
    if requested is None:
        return TableOptions()
    kontra, bock, ramsch = requested.kontra, requested.bock, requested.ramsch
    return TableOptions(
        show_running_points=requested.show_running_points,
        kontra=None if kontra is None else KontraOptions(kontra.sayer, kontra.reach, kontra.deadline),
        bock=None if bock is None else BockOptions(frozenset(bock.triggers), bock.overlap),
        ramsch=None
        if ramsch is None
        else RamschSetting(ramsch.occasion, RamschOptions(ramsch.scoring, ramsch.jungfrau, ramsch.durchmarsch)),
    )
