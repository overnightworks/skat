import re

from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.tables import sit_in

YOU = text(SOURCE_LANGUAGE, "result.sideYou")
WON = text(SOURCE_LANGUAGE, "result.won")
LOST = text(SOURCE_LANGUAGE, "result.lost")
OVERBID = text(SOURCE_LANGUAGE, "result.overbid")
MINUS = chr(0x2212)
WAITING_FOR_PLAYERS = text(SOURCE_LANGUAGE, "table.waitingForPlayers")
TIMES = chr(0x00D7)
CARD = old_surface.RESULT_CARD
SERIES_GONE = text(SOURCE_LANGUAGE, "table.seriesGone")


def loosely(*parts: str) -> re.Pattern[str]:
    """The parts in order, whatever whitespace the page puts between its elements."""
    return re.compile(r"^\s*" + r"\s*".join(re.escape(part) for part in parts) + r"\s*$")


def listed(names: list[str]) -> str:
    """The names as the page's German list format writes them: "Anna", "Anna und Ben", "Anna, Ben und Cleo"."""
    if len(names) < 2:
        return "".join(names)
    return ", ".join(names[:-1]) + " und " + names[-1]


def waiting_for(names: list[str]) -> str:
    return text(SOURCE_LANGUAGE, "table.waitingFor", names=listed(names))


def expect_a_new_sitter_reads_the_leaver_as_gone(sitter: Page, seat: int, leaver_name: str) -> None:
    """The person who took the leaver's chair after the hand reads the card as a watcher does, with no „Du“."""
    sit_in(sitter, seat)
    old_surface.expect_the_own_chair_at(sitter, seat)
    expect(old_surface.reckoning_name(sitter, seat)).to_contain_text(leaver_name)
    expect(old_surface.gone_note(sitter, seat)).to_have_text(SERIES_GONE)
    expect(old_surface.reckoning_names(sitter).filter(has_text=YOU)).to_have_count(0)


def signed(number: int) -> str:
    return f"{MINUS}{-number}" if number < 0 else f"+{number}"


def expect_the_page_around_the_card(people: list[Page]) -> None:
    for person in people:
        expect(old_surface.card_faces(person)).to_have_count(0)
        expect(person.locator("body")).not_to_contain_text(WAITING_FOR_PLAYERS)
        measures = old_surface.page_around_the_result_card(person)
        assert not measures["scrolls"]
        bar = measures["bar"]
        card = measures["card"]
        last_row = measures["lastRow"]
        assert bar is not None
        assert last_row is not None
        assert card["y"] >= 0
        assert card["y"] + card["height"] <= bar["y"]
        assert bar["y"] + bar["height"] <= measures["viewportHeight"]
        assert last_row["y"] >= card["y"]
        assert last_row["y"] + last_row["height"] <= card["y"] + card["height"]


def expect_the_seat_tiles_inside_the_card(people: list[Page]) -> None:
    """Every seat tile of the declared result lies whole inside its card, with the card unscrolled."""
    for person in people:
        card = old_surface.result_card(person).bounding_box()
        assert card is not None
        tiles = old_surface.reckoning_tiles(person)
        expect(tiles).to_have_count(3)
        for tile in tiles.all():
            box = tile.bounding_box()
            assert box is not None
            assert box["x"] >= card["x"]
            assert box["x"] + box["width"] <= card["x"] + card["width"]
            assert box["y"] >= card["y"]
            assert box["y"] + box["height"] <= card["y"] + card["height"]
