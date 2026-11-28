from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.table.records import TableStyle
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support import old_surface
from tests.e2e.support.table_menu import menu_button

if TYPE_CHECKING:
    from collections.abc import Iterable

STYLE_KEY = text(SOURCE_LANGUAGE, "table.style")
ROOM = old_surface.ROOM
TABLE_SCENES = Path(__file__).parents[3] / "docs" / "mockups" / "table.html"
STYLES = [pytest.param(TableStyle.KLASSIK, id="klassik"), pytest.param(TableStyle.STRANDBAR, id="strandbar")]
# The furniture each style adds as elements: the Strandbar's cocktail and shell, the Klassik's brass lamp.
DECORATIONS = {TableStyle.STRANDBAR: 2, TableStyle.KLASSIK: 1}


def choose_style(person: Page, style: TableStyle) -> None:
    """A seated person picks the table's style through the menu's row and its panel."""
    menu_button(person, STYLE_KEY).click()
    old_surface.style_tile(person, style.value).click()
    person.keyboard.press("Escape")


def give_the_table_its_style(chooser: Page, everyone: Iterable[Page], style: TableStyle) -> None:
    """The table has `style` on every page; a new table has Klassik, so that style needs no choosing."""
    if style is TableStyle.KLASSIK:
        return
    choose_style(chooser, style)
    for person in everyone:
        old_surface.expect_the_style(person, style.value)


def expect_the_furniture_clear(everyone: Iterable[Page], style: TableStyle) -> None:
    """The style's furniture is on the page and covers no card, tag or key, wherever the scene is now."""
    for person in everyone:
        expect(old_surface.furniture(person)).to_have_count(DECORATIONS[style])
        assert old_surface.furniture_in_the_way(person) == []


PAINT = """(element, properties) => {
    const painted = getComputedStyle(element);
    return Object.fromEntries(properties.map((property) => [property, painted[property]]));
}"""


PREFERS_REDUCED_MOTION = "matchMedia('(prefers-reduced-motion: reduce)').matches"


def in_the_scene(person: Page, scene: str, script: str, argument: object) -> Any:
    """What `script` returns for the frame of the blessed `scene` at the width of `person`'s page, and `argument`."""
    viewport = person.viewport_size
    assert viewport is not None
    frame = f"{scene}-{viewport['width']}"
    browser = person.context.browser
    assert browser is not None
    # The scenes open in a context of their own with the person's width and motion setting: the person's context is
    # traced, and a trace takes a snapshot of the whole mockup, every scene in it, at each step, which costs
    # several times what the read costs.
    scenes = browser.new_context(
        viewport=viewport,
        reduced_motion="reduce" if person.evaluate(PREFERS_REDUCED_MOTION) else "no-preference",
    )
    try:
        page_of_scenes = scenes.new_page()
        page_of_scenes.goto(f"{TABLE_SCENES.as_uri()}?f={frame}")
        return page_of_scenes.locator(f"[id='{frame}']").evaluate(script, argument)
    finally:
        scenes.close()


def expect_painted_as_the_scene(person: Page, scene: str, live: str, drawn: str, properties: list[str]) -> None:
    """`live` has the computed `properties` that `drawn` has in the blessed scene at this width."""
    expect_everyone_painted_as_the_scene([person], scene, live, drawn, properties)


def expect_everyone_painted_as_the_scene(
    everyone: Iterable[Page], scene: str, live: str, drawn: str, properties: list[str]
) -> None:
    """Like `expect_painted_as_the_scene` for pages of one width, which share one read of the scene."""
    pages = list(everyone)
    in_scene = in_the_scene(
        pages[0], scene, f"(frame, properties) => ({PAINT})(frame.querySelector({drawn!r}), properties)", properties
    )
    for person in pages:
        assert person.locator(live).first.evaluate(PAINT, properties) == in_scene
