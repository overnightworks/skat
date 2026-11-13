import re

from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text

YOU = text(SOURCE_LANGUAGE, "result.sideYou")
WON = text(SOURCE_LANGUAGE, "result.won")
LOST = text(SOURCE_LANGUAGE, "result.lost")
OVERBID = text(SOURCE_LANGUAGE, "result.overbid")
MINUS = chr(0x2212)
WAITING_FOR_PLAYERS = text(SOURCE_LANGUAGE, "table.waitingForPlayers")
TIMES = chr(0x00D7)
CARD = ".result"


def loosely(*parts: str) -> re.Pattern[str]:
    """The parts in order, whatever whitespace the page puts between its elements."""
    return re.compile(r"^\s*" + r"\s*".join(re.escape(part) for part in parts) + r"\s*$")


def listed(names: list[str]) -> str:
    """The names as the page's list format writes them: "Anna und Ben"."""
    return " und ".join(names)


def waiting_for(names: list[str]) -> str:
    return text(SOURCE_LANGUAGE, "table.waitingFor", names=listed(names))


def signed(number: int) -> str:
    return f"{MINUS}{-number}" if number < 0 else f"+{number}"


# Every measure of the page around the card in one round trip, taken before the card is scrolled to its end and the
# last row after it.
_PAGE_AROUND_THE_CARD = """(card, barSelector) => {
    const root = document.documentElement;
    const box = element => element && element.getBoundingClientRect();
    const bar = box(document.querySelector(barSelector));
    const cardBox = box(card);
    card.scrollTop = card.scrollHeight;
    return {
        scrolls: root.scrollWidth > window.innerWidth || root.scrollHeight > window.innerHeight,
        viewportHeight: window.innerHeight,
        bar,
        card: cardBox,
        lastRow: box(card.lastElementChild),
    };
}"""


def expect_the_page_around_the_card(people: list[Page]) -> None:
    for person in people:
        expect(person.locator(".card-face")).to_have_count(0)
        expect(person.locator("body")).not_to_contain_text(WAITING_FOR_PLAYERS)
        measures = person.locator(CARD).evaluate(_PAGE_AROUND_THE_CARD, ".actions")
        assert not measures["scrolls"]
        bar = measures["bar"]
        card = measures["card"]
        last_row = measures["lastRow"]
        assert bar is not None
        assert card is not None
        assert last_row is not None
        assert card["y"] >= 0
        assert card["y"] + card["height"] <= bar["y"]
        assert bar["y"] + bar["height"] <= measures["viewportHeight"]
        assert last_row["y"] >= card["y"]
        assert last_row["y"] + last_row["height"] <= card["y"] + card["height"]


def expect_the_seat_tiles_inside_the_card(people: list[Page]) -> None:
    """Every seat tile of the declared result lies whole inside its card, with the card unscrolled."""
    for person in people:
        card = person.locator(CARD).bounding_box()
        assert card is not None
        tiles = person.locator(f"{CARD} .reck")
        expect(tiles).to_have_count(3)
        for tile in tiles.all():
            box = tile.bounding_box()
            assert box is not None
            assert box["x"] >= card["x"]
            assert box["x"] + box["width"] <= card["x"] + card["width"]
            assert box["y"] >= card["y"]
            assert box["y"] + box["height"] <= card["y"] + card["height"]
