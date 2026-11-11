import re

from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text

YOU = text(SOURCE_LANGUAGE, "result.sideYou")
WON = text(SOURCE_LANGUAGE, "result.won")
LOST = text(SOURCE_LANGUAGE, "result.lost")
WINS = text(SOURCE_LANGUAGE, "result.wins")
LOSES = text(SOURCE_LANGUAGE, "result.loses")
OVERBID = text(SOURCE_LANGUAGE, "result.overbid")
SPIEL = text(SOURCE_LANGUAGE, "result.levelSpiel")
LIST_BONUS = text(SOURCE_LANGUAGE, "result.listBonus")
EACH = text(SOURCE_LANGUAGE, "result.each")
WORTH = text(SOURCE_LANGUAGE, "result.gameWorth")
BID_VALUE = text(SOURCE_LANGUAGE, "result.bidValue")
MINUS = chr(0x2212)
WAITING_FOR_PLAYERS = text(SOURCE_LANGUAGE, "table.waitingForPlayers")
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
