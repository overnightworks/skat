from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from skat.table.records import TableStyle
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.table_menu import menu_button

if TYPE_CHECKING:
    from collections.abc import Iterable

STYLE_KEY = text(SOURCE_LANGUAGE, "table.style")
ROOM = ".room"
TABLE_SCENES = Path(__file__).parents[3] / "docs" / "mockups" / "table.html"
STYLES = [pytest.param(TableStyle.KLASSIK, id="klassik"), pytest.param(TableStyle.STRANDBAR, id="strandbar")]
# The furniture each style adds as elements: the Strandbar's cocktail and shell, the Klassik's brass lamp.
DECORATIONS = {TableStyle.STRANDBAR: 2, TableStyle.KLASSIK: 1}

# The cocktail and the shell lie under everything the people at the table read and touch: no sampled point of a card,
# tag, key, chair, plaque or the result is painted by one of them (their pointer events are switched on so the page
# can say what it paints there), and the page gains no sideways scroll from the rim round the felt. A chair's stool is
# drawn behind its chair and the cards, as the scenes draw it, and covers nothing.
FURNITURE_CLEAR = """() => {
    const all = (selector) => [...document.querySelectorAll(selector)];
    const decor = all('.decor');
    for (const element of decor) element.style.pointerEvents = 'auto';
    const covered = all(
        '.own-hand .card, .chair .fan, .chair .tile, .chair .plate, .chair .coaster, .trick .face, .trick .tag, '
        + '.actions > *, .plaque, .result, .skat-card, .ladder'
    ).flatMap((element) => {
        const box = element.getBoundingClientRect();
        const points = [0.1, 0.5, 0.9].flatMap((across) =>
            [0.1, 0.5, 0.9].map((down) => [box.left + box.width * across, box.top + box.height * down])
        );
        return points
            .map(([x, y]) => document.elementFromPoint(x, y)?.closest('.decor'))
            .filter((found) => found)
            .map((found) => `${found.classList[1]} covers ${element.className}`);
    });
    for (const element of decor) element.style.pointerEvents = '';
    if (document.documentElement.scrollWidth > window.innerWidth) covered.push('the page scrolls sideways');
    return [...new Set(covered)];
}"""


def choose_style(person: Page, style: TableStyle) -> None:
    """A seated person picks the table's style through the menu's row and its panel."""
    menu_button(person, STYLE_KEY).click()
    person.locator(f".style-tile.style-{style.value}").click()
    person.keyboard.press("Escape")


def give_the_table_its_style(chooser: Page, everyone: Iterable[Page], style: TableStyle) -> None:
    """The table has `style` on every page; a new table has Klassik, so that style needs no choosing."""
    if style is TableStyle.KLASSIK:
        return
    choose_style(chooser, style)
    for person in everyone:
        expect(person.locator(ROOM)).to_have_attribute("data-style", style.value)


def expect_the_furniture_clear(everyone: Iterable[Page], style: TableStyle) -> None:
    """The style's furniture is on the page and covers no card, tag or key, wherever the scene is now."""
    for person in everyone:
        expect(person.locator(".decor")).to_have_count(DECORATIONS[style])
        assert person.evaluate(FURNITURE_CLEAR) == []


PAINT = """(element, properties) => {
    const painted = getComputedStyle(element);
    return Object.fromEntries(properties.map((property) => [property, painted[property]]));
}"""


def expect_painted_as_the_scene(person: Page, scene: str, live: str, drawn: str, properties: list[str]) -> None:
    """`live` has the computed `properties` that `drawn` has in the blessed scene at this width."""
    viewport = person.viewport_size
    assert viewport is not None
    frame = f"{scene}-{viewport['width']}"
    page_of_scenes = person.context.new_page()
    try:
        page_of_scenes.goto(f"{TABLE_SCENES.as_uri()}?f={frame}")
        in_scene = page_of_scenes.locator(f"[id='{frame}'] {drawn}").first.evaluate(PAINT, properties)
    finally:
        page_of_scenes.close()
    assert person.locator(live).first.evaluate(PAINT, properties) == in_scene
