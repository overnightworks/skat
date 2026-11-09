from dataclasses import dataclass
from itertools import takewhile
from typing import TYPE_CHECKING

from skat.engine.cards import DECK
from skat.engine.declaration import Announcement
from skat.engine.games import NULL_VALUES, GameKind, Trump

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
    """The game's value: the matadors and level are empty for Null, which has a fixed value.

    Schneider and Schwarz are the levels the value counts, whichever side suffered them and whether announced or
    reached; both are false in Null.
    """

    won: bool
    matadors: Matadors | None
    level: int | None
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


@dataclass(frozen=True)
class _Levels:
    schneider: bool
    schwarz: bool


def _levels(declaration: Declaration, played: PlayedOut) -> _Levels:
    """Schneider and Schwarz count when the losing side suffered them or the declarer announced them."""
    if played.won_by_play:
        schneider, schwarz = played.opponents_schneider, played.opponents_schwarz
    else:
        schneider, schwarz = played.declarer_schneider, played.declarer_schwarz
    return _Levels(
        schneider=schneider or declaration.announcement is not Announcement.NONE,
        schwarz=schwarz or declaration.announcement is Announcement.SCHWARZ,
    )


def _level(declaration: Declaration, levels: _Levels) -> int:
    """One step each: Spiel, Hand, Schneider, Schneider angesagt, Schwarz, Schwarz angesagt, ouvert."""
    return sum(
        (
            True,
            declaration.hand,
            levels.schneider,
            declaration.announcement is not Announcement.NONE,
            levels.schwarz,
            declaration.announcement is Announcement.SCHWARZ,
            declaration.ouvert,
        )
    )


def _announcements_reached(declaration: Declaration, played: PlayedOut) -> bool:
    if declaration.announcement is Announcement.NONE:
        return True
    if declaration.announcement is Announcement.SCHNEIDER:
        return played.opponents_schneider
    return played.opponents_schwarz


def value_of(played: PlayedOut) -> Valuation:
    declaration = played.declared.declaration
    assert declaration is not None  # noqa: S101 - narrows the type; a played-out game is declared
    null_levels = declaration.null_levels
    if null_levels is not None:
        return Valuation(
            won=played.won_by_play,
            matadors=None,
            level=None,
            value=NULL_VALUES[null_levels],
            schneider=False,
            schwarz=False,
        )
    held = matadors((*played.declared.hand, *played.declared.skat), declaration.kind)
    base = declaration.kind.base_value
    assert held is not None  # noqa: S101 - narrows the type; only Null has no matadors
    assert base is not None  # noqa: S101 - narrows the type; only Null has no base value
    levels = _levels(declaration, played)
    level = _level(declaration, levels)
    return Valuation(
        won=played.won_by_play and _announcements_reached(declaration, played),
        matadors=held,
        level=level,
        value=(held.count + level) * base,
        schneider=levels.schneider,
        schwarz=levels.schwarz,
    )
