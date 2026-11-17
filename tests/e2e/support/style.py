from pathlib import Path
from typing import TYPE_CHECKING, Any

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


def in_the_scene(person: Page, scene: str, script: str, argument: object) -> Any:
    """What `script` returns for the frame of the blessed `scene` at the width of `person`'s page, and `argument`."""
    viewport = person.viewport_size
    assert viewport is not None
    frame = f"{scene}-{viewport['width']}"
    page_of_scenes = person.context.new_page()
    try:
        page_of_scenes.goto(f"{TABLE_SCENES.as_uri()}?f={frame}")
        return page_of_scenes.locator(f"[id='{frame}']").evaluate(script, argument)
    finally:
        page_of_scenes.close()


def expect_painted_as_the_scene(person: Page, scene: str, live: str, drawn: str, properties: list[str]) -> None:
    """`live` has the computed `properties` that `drawn` has in the blessed scene at this width."""
    in_scene = in_the_scene(
        person, scene, f"(frame, properties) => ({PAINT})(frame.querySelector({drawn!r}), properties)", properties
    )
    assert person.locator(live).first.evaluate(PAINT, properties) == in_scene


# The boxes of everything `selector` finds, left to right, measured from the frame's top left corner, with the radii
# its top left corner is drawn with, after the browser shrinks radii too long for the box; the page measures from the
# window's, which a scene's frame stands for.
BOXES = """(frame, selector) => {
    const origin = frame === document.documentElement ? { left: 0, top: 0 } : frame.getBoundingClientRect();
    const length = (value, whole) => (value.endsWith('%') ? (parseFloat(value) / 100) * whole : parseFloat(value));
    return [...frame.querySelectorAll(selector)]
        .map((element) => {
            const box = element.getBoundingClientRect();
            const [across, down = across] = getComputedStyle(element).borderTopLeftRadius.split(' ');
            const [x, y] = [length(across, box.width), length(down, box.height)];
            const shrink = Math.min(1, box.width / (2 * x), box.height / (2 * y));
            return {
                left: box.left - origin.left,
                top: box.top - origin.top,
                width: box.width,
                height: box.height,
                cornerWidth: x * shrink,
                cornerHeight: y * shrink,
            };
        })
        .sort((first, second) => first.left - second.left);
}"""


def boxes_in_the_scene(person: Page, scene: str, selector: str) -> list[dict[str, Any]]:
    """The boxes the blessed `scene` draws for `selector` at the width of `person`'s page."""
    return in_the_scene(person, scene, BOXES, selector)


def boxes_on_the_page(person: Page, selector: str) -> list[dict[str, Any]]:
    """The boxes `person`'s page draws for `selector`, measured as `boxes_in_the_scene` measures the scene's."""
    return person.locator(":root").evaluate(BOXES, selector)
