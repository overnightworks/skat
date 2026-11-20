from typing import Any, ClassVar

from playwright.sync_api import expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.ramsch import RamschTable

SERIES_LENGTH = 3
COUNT = ".series-count"


def game_count(game: int) -> str:
    return text(SOURCE_LANGUAGE, "table.seriesCount", game=str(game), count=SERIES_LENGTH)


class PassedInTable(RamschTable):
    """The same three people at a table without Ramsch, so a hand all pass is passed in and leaves no entry."""

    options: ClassVar[dict[str, Any]] = {}


def pass_the_series_in(table: RamschTable) -> None:
    """Every game of the series is passed in, so the series ends with the last."""
    for game in range(1, SERIES_LENGTH + 1):
        for person in table.everyone:
            expect(person.locator(COUNT)).to_have_text(game_count(game))
        table.pass_all()
