from enum import StrEnum
from typing import Final

from skat.engine.declaration import Announcement
from skat.engine.games import GameKind


class GameToken(StrEnum):
    KARO = "karo"
    HERZ = "herz"
    PIK = "pik"
    KREUZ = "kreuz"
    GRAND = "grand"
    NULL = "null"


class AnnouncementToken(StrEnum):
    NONE = "none"
    SCHNEIDER = "schneider"
    SCHWARZ = "schwarz"


GAME_TOKENS: Final = {
    GameKind.KARO: GameToken.KARO,
    GameKind.HERZ: GameToken.HERZ,
    GameKind.PIK: GameToken.PIK,
    GameKind.KREUZ: GameToken.KREUZ,
    GameKind.GRAND: GameToken.GRAND,
    GameKind.NULL: GameToken.NULL,
}
ANNOUNCEMENT_TOKENS: Final = {
    Announcement.NONE: AnnouncementToken.NONE,
    Announcement.SCHNEIDER: AnnouncementToken.SCHNEIDER,
    Announcement.SCHWARZ: AnnouncementToken.SCHWARZ,
}
