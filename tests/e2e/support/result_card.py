import re

from playwright.sync_api import Page, expect

from tests.e2e.support.words import catalog_text

YOU = catalog_text("sideYou")
WON = catalog_text("resultWon")
LOST = catalog_text("resultLost")
WINS = catalog_text("resultWins")
LOSES = catalog_text("resultLoses")
OVERBID = catalog_text("overbid")
SPIEL = catalog_text("levelSpiel")
LIST_BONUS = catalog_text("listBonus")
EACH = catalog_text("each")
WORTH = catalog_text("gameWorth")
BID_VALUE = catalog_text("bidValue")
MINUS = chr(0x2212)
WAITING_FOR_PLAYERS = catalog_text("waitingForPlayers")
TIMES = chr(0x00D7)
CARD = ".result"


def loosely(*parts: str) -> re.Pattern[str]:
    """The parts in order, whatever whitespace the page puts between its elements."""
    return re.compile(r"^\s*" + r"\s*".join(re.escape(part) for part in parts) + r"\s*$")


def expect_the_page_around_the_card(people: list[Page]) -> None:
    for person in people:
        expect(person.locator(".card-face")).to_have_count(0)
        expect(person.locator("body")).not_to_contain_text(WAITING_FOR_PLAYERS)
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        bar = person.locator(".actions").bounding_box()
        card = person.locator(CARD).bounding_box()
        assert bar is not None
        assert card is not None
        assert card["y"] >= 0
        assert card["y"] + card["height"] <= bar["y"]
        viewport = person.viewport_size
        assert viewport is not None
        assert bar["y"] + bar["height"] <= viewport["height"]
        person.locator(CARD).evaluate("card => { card.scrollTop = card.scrollHeight; }")
        last_row = person.locator(f"{CARD} > :last-child").bounding_box()
        assert last_row is not None
        assert last_row["y"] >= card["y"]
        assert last_row["y"] + last_row["height"] <= card["y"] + card["height"]
