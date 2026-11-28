from typing import TYPE_CHECKING, Any, ClassVar

from playwright.sync_api import expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.ramsch import RamschTable

if TYPE_CHECKING:
    from playwright.sync_api import Route

SERIES_LENGTH = 3
COUNT = old_surface.SERIES_COUNT
REFUSED = 409
NEXT_LINE = old_surface.NEXT_SERIES_LINE
CHANGE = text(SOURCE_LANGUAGE, "table.nextSeriesChange")
SAVE = text(SOURCE_LANGUAGE, "table.nextSeriesSave")
COMMAND_FAILED = text(SOURCE_LANGUAGE, "table.commandFailed")
MORE_GAMES = text(SOURCE_LANGUAGE, "start.seriesMore")
NEXT_SHEET = old_surface.NEXT_SERIES_SHEET


def refuse(route: Route) -> None:
    route.fulfill(status=REFUSED, content_type="application/json", body="{}")


def game_count(game: int) -> str:
    return text(SOURCE_LANGUAGE, "table.seriesCount", game=str(game), count=SERIES_LENGTH)


class PassedInTable(RamschTable):
    """The same three people at a table without Ramsch, so a hand all pass is passed in and leaves no entry."""

    options: ClassVar[dict[str, Any]] = {}


def pass_the_series_in(table: RamschTable) -> None:
    """Every game of the series is passed in, so the series ends with the last."""
    for game in range(1, SERIES_LENGTH + 1):
        for person in table.everyone:
            expect(old_surface.series_count(person)).to_have_text(game_count(game))
        table.pass_all()
