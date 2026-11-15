"""The reactions thrown at each table and when each person last threw, kept in this process only.

`Presence` owns the one `ReactionLog`. A table's streams show the reactions thrown within `REACTION_SHOWN_SECONDS`,
the page plays each one it did not show before, and an older one leaves the answer. A restart forgets them all. Only the
event loop's thread touches it.
"""

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from skat.table.reacting import REACTION_WINDOW_SECONDS, REACTIONS_PER_WINDOW, Reaction

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__ = ["REACTION_SHOWN_SECONDS", "ReactionLog", "Thrown"]

REACTION_SHOWN_SECONDS: Final = 4.0
"""How long a reaction stays in the answers of its table: long enough for every stream to read it after its wake."""

SHOWN_AT_MOST: Final = 12
"""How many reactions of one table are kept; a flood of several people shows the latest ones."""


@dataclass(frozen=True)
class Thrown:
    """One reaction: its number at the table, what it is, and who threw it; a watcher is no seat and has no name."""

    number: int
    reaction: Reaction
    by_seat: int | None
    thrown_at: float


class ReactionLog:
    """What each table's streams show of the reactions, and the throws each person made lately."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._tables: dict[str, deque[Thrown]] = {}
        self._numbers: dict[str, int] = {}
        self._people: dict[str, deque[float]] = {}

    def now(self) -> float:
        return self._clock()

    def thrown_by(self, account_id: str) -> Sequence[float]:
        """When the account threw within the window, at whichever table."""
        return tuple(self._people.get(account_id, ()))

    def throw(self, table_id: str, account_id: str, reaction: Reaction, by_seat: int | None) -> None:
        """Records a throw the caller has judged allowed; it counts against the account and shows at the table."""
        now = self._clock()
        self._forget_old_throws(now)
        self._people.setdefault(account_id, deque(maxlen=REACTIONS_PER_WINDOW)).append(now)
        number = self._numbers.get(table_id, 0) + 1
        self._numbers[table_id] = number
        shown = self._tables.setdefault(table_id, deque(maxlen=SHOWN_AT_MOST))
        shown.append(Thrown(number, reaction, by_seat, now))

    def shown(self, table_id: str) -> tuple[Thrown, ...]:
        """The table's reactions that are still shown, the oldest first."""
        now = self._clock()
        return tuple(
            thrown for thrown in self._tables.get(table_id, ()) if now - thrown.thrown_at < REACTION_SHOWN_SECONDS
        )

    def drop(self, table_id: str) -> None:
        self._tables.pop(table_id, None)
        self._numbers.pop(table_id, None)

    def _forget_old_throws(self, now: float) -> None:
        for account_id, moments in list(self._people.items()):
            if now - moments[-1] >= REACTION_WINDOW_SECONDS:
                del self._people[account_id]
