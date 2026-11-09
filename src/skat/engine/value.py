from dataclasses import dataclass
from enum import StrEnum
from itertools import takewhile
from typing import TYPE_CHECKING

from skat.engine.cards import DECK
from skat.engine.declaration import Announcement
from skat.engine.games import NULL_VALUES, GameKind, Trump
from skat.engine.tricks import Ending

if TYPE_CHECKING:
    from collections.abc import Collection

    from skat.engine.cards import Card
    from skat.engine.declaration import Declaration
    from skat.engine.tricks import PlayedOut


@dataclass(frozen=True)
class Matadors:
    """„Mit n“ (the declarer holds the top trumps) or „ohne n“ (he lacks them)."""

    mit: bool
    count: int


@dataclass(frozen=True)
class Valuation:
    """The game's value: the matadors are empty for Null, which has a fixed value.

    Schneider and Schwarz are the levels the value counts, whichever side suffered them and whether announced or
    reached; both are false in Null.
    """

    won: bool
    matadors: Matadors | None
    value: int
    schneider: bool
    schwarz: bool


def matadors(twelve: Collection[Card], kind: GameKind) -> Matadors | None:
    """The run of top trumps held, or missing, counted over the ten cards plus the skat."""
    if kind is GameKind.NULL:
        return None
    trumps = sorted((card for card in DECK if kind.playing_suit(card) is Trump.TRUMP), key=kind.strength, reverse=True)
    mit = trumps[0] in twelve
    return Matadors(mit=mit, count=len(list(takewhile(lambda card: (card in twelve) is mit, trumps))))


class Level(StrEnum):
    """One step of the game value, in the order the rules count them."""

    SPIEL = "spiel"
    HAND = "hand"
    SCHNEIDER = "schneider"
    SCHNEIDER_ANNOUNCED = "schneider_announced"
    SCHWARZ = "schwarz"
    SCHWARZ_ANNOUNCED = "schwarz_announced"
    OUVERT = "ouvert"


def _suffered(declaration: Declaration, played: PlayedOut) -> tuple[bool, bool]:
    """Schneider and Schwarz as the losing side suffered them or the declarer announced them.

    A given-up game counts only the announced ones: no cards were played to reach more.
    """
    if played.ending is Ending.GIVEN_UP:
        schneider, schwarz = False, False
    elif played.won_by_play:
        schneider, schwarz = played.opponents_schneider, played.opponents_schwarz
    else:
        schneider, schwarz = played.declarer_schneider, played.declarer_schwarz
    return (
        schneider or declaration.announcement is not Announcement.NONE,
        schwarz or declaration.announcement is Announcement.SCHWARZ,
    )


def levels_of(declaration: Declaration, *, schneider: bool, schwarz: bool) -> tuple[Level, ...]:
    """The levels a suit or Grand game counts; Null has none."""
    if declaration.null_levels is not None:
        return ()
    counted = (
        (Level.SPIEL, True),
        (Level.HAND, declaration.hand),
        (Level.SCHNEIDER, schneider),
        (Level.SCHNEIDER_ANNOUNCED, declaration.announcement is not Announcement.NONE),
        (Level.SCHWARZ, schwarz),
        (Level.SCHWARZ_ANNOUNCED, declaration.announcement is Announcement.SCHWARZ),
        (Level.OUVERT, declaration.ouvert),
    )
    return tuple(level for level, reached in counted if reached)


@dataclass(frozen=True)
class Breakdown:
    """What a game value is made of besides the matadors: its base value and its levels; Null has neither."""

    base_value: int | None
    levels: tuple[Level, ...]


def breakdown_of(declaration: Declaration, *, schneider: bool, schwarz: bool) -> Breakdown:
    """The breakdown of what a list entry stores: the declaration and the Schneider and Schwarz the value counted."""
    return Breakdown(
        base_value=declaration.kind.base_value,
        levels=levels_of(declaration, schneider=schneider, schwarz=schwarz),
    )


def value_reached_by_levels(matador_count: int, levels: tuple[Level, ...], base_value: int) -> int:
    """The one value formula: the matadors and the levels, multiplied by the base value."""
    return (matador_count + len(levels)) * base_value


def _announcements_reached(declaration: Declaration, played: PlayedOut) -> bool:
    if declaration.announcement is Announcement.NONE:
        return True
    if declaration.announcement is Announcement.SCHNEIDER:
        return played.opponents_schneider
    return played.opponents_schwarz


def _conceded_valuation(played: PlayedOut, bid: int, declaration: Declaration) -> Valuation:
    """The declared game with the cheapest levels that meet the bid: declared, then Schneider, then Schwarz too."""
    held = matadors((*played.declared.hand, *played.declared.skat), declaration.kind)
    base = declaration.kind.base_value
    assert held is not None  # noqa: S101 - narrows the type; Null is valued before this
    assert base is not None  # noqa: S101 - narrows the type; Null is valued before this
    announced_schwarz = declaration.announcement is Announcement.SCHWARZ
    for schneider, schwarz in (
        (declaration.announcement is not Announcement.NONE, announced_schwarz),
        (True, announced_schwarz),
    ):
        levels = levels_of(declaration, schneider=schneider, schwarz=schwarz)
        value = value_reached_by_levels(held.count, levels, base)
        if value >= bid:
            return Valuation(won=True, matadors=held, value=value, schneider=schneider, schwarz=schwarz)
    levels = levels_of(declaration, schneider=True, schwarz=True)
    value = value_reached_by_levels(held.count, levels, base)
    return Valuation(won=True, matadors=held, value=value, schneider=True, schwarz=True)


def value_of(played: PlayedOut, bid: int | None = None) -> Valuation:
    """The game's valuation; a conceded game is valued by declaration and bid, so only it needs the bid."""
    declaration = played.declared.declaration
    assert declaration is not None  # noqa: S101 - narrows the type; a played-out game is declared
    null_levels = declaration.null_levels
    if null_levels is not None:
        return Valuation(
            won=played.won_by_play,
            matadors=None,
            value=NULL_VALUES[null_levels],
            schneider=False,
            schwarz=False,
        )
    if played.ending is Ending.CONCEDED:
        assert bid is not None  # noqa: S101 - narrows the type; a conceded game is valued against its bid
        return _conceded_valuation(played, bid, declaration)
    held = matadors((*played.declared.hand, *played.declared.skat), declaration.kind)
    base = declaration.kind.base_value
    assert held is not None  # noqa: S101 - narrows the type; only Null has no matadors
    assert base is not None  # noqa: S101 - narrows the type; only Null has no base value
    schneider, schwarz = _suffered(declaration, played)
    levels = levels_of(declaration, schneider=schneider, schwarz=schwarz)
    return Valuation(
        won=played.won_by_play and _announcements_reached(declaration, played),
        matadors=held,
        value=value_reached_by_levels(held.count, levels, base),
        schneider=schneider,
        schwarz=schwarz,
    )
