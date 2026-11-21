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
# tag, key, chair, plaque, counter or the result is painted by one of them (their pointer events are switched on so the
# page can say what it paints there), no key of the bid bar paints the middle of one of them, and the page gains no
# sideways scroll from the rim round the felt. A chair's stool is drawn behind its chair and the cards, as the scenes
# draw it, and covers nothing.
FURNITURE_CLEAR = """() => {
    const all = (selector) => [...document.querySelectorAll(selector)];
    const decor = all('.decor');
    for (const element of decor) element.style.pointerEvents = 'auto';
    const covered = all(
        '.own-hand .card, .chair .fan, .chair .tile, .chair .plate, .chair .coaster, .trick .face, .trick .tag, '
        + '.actions > *, .plaque, .counter, .duel, .result, .skat-card, .ladder, .bid-keys > *, .bid-chips > *, '
        + '.bid-line > *'
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
    for (const element of decor) {
        const box = element.getBoundingClientRect();
        const above = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        if (above?.closest('.bid-keys > *, .bid-chips > *, .bid-line > *, .scale'))
            covered.push(`the bid bar hides the ${element.classList[1]}`);
    }
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
    import time

    from tests.e2e.support.phasing import add

    def read(open_page: Any, label: str) -> Any:
        t0 = time.monotonic()
        page_of_scenes = open_page()
        t1 = time.monotonic()
        try:
            page_of_scenes.goto(f"{TABLE_SCENES.as_uri()}?f={frame}")
            t2 = time.monotonic()
            value = page_of_scenes.locator(f"[id='{frame}']").evaluate(script, argument)
            t3 = time.monotonic()
            return value
        finally:
            page_of_scenes.close()
            add(f"{label}-newpage", t1 - t0)
            add(f"{label}-goto", t2 - t1)
            add(f"{label}-eval", t3 - t2)
            add(f"{label}-close", time.monotonic() - t3)

    mobile = viewport["width"] < 1000
    browser = person.context.browser
    assert browser is not None
    options = {"viewport": viewport, "is_mobile": mobile, "has_touch": mobile, "reduced_motion": "reduce", "locale": "de"}
    bare = browser.new_context(**options)
    value_bare = read(bare.new_page, "bare")
    bare.close()
    traced = browser.new_context(**options)
    traced.tracing.start(screenshots=True, snapshots=True, sources=True)
    value_traced = read(traced.new_page, "traced")
    traced.close()
    covered = browser.new_context(**options)

    def covered_page() -> Any:
        page = covered.new_page()
        session = covered.new_cdp_session(page)
        session.send("Profiler.enable")
        session.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
        return page

    value_covered = read(covered_page, "covered")
    covered.close()
    value = read(person.context.new_page, "scene")
    add("scene-same", float(value == value_bare == value_traced == value_covered))
    return value


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
