import time
from typing import TYPE_CHECKING

import pytest

from tests.e2e.support.people import SMALL_PHONE
from tests.e2e.support.result_card import waiting_for
from tests.e2e.support.style import TABLE_SCENES

if TYPE_CHECKING:
    from playwright.sync_api import Page

# The scenes draw a phone at 390 px and a desktop at 1280 px; the desktop layout starts at this width.
PHONE_BREAKPOINT = 900
FONT_SIZE_OF = "element => getComputedStyle(element).fontSize"
SHEET_MARGINS_OF = """sheet => {
    const frame = sheet.closest("[id]").getBoundingClientRect();
    const box = sheet.getBoundingClientRect();
    return {above: box.top - frame.top, below: frame.bottom - box.bottom};
}"""
BOXES_OF = """(args) => {
    const [selector, frame] = args;
    const origin = frame ? document.getElementById(frame).getBoundingClientRect() : {x: 0, y: 0};
    const root = frame ? document.getElementById(frame) : document;
    return Array.from(root.querySelectorAll(selector)).flatMap((element) => {
        const box = element.getBoundingClientRect();
        return [box.x - origin.x, box.y - origin.y, box.width, box.height];
    });
}"""
SCENE_SPACING = 4
SETTLE_SECONDS = 3
SETTLE_POLL_MILLISECONDS = 100


def scene_frame_at(person: Page, scene: str) -> str:
    viewport = person.viewport_size
    assert viewport is not None
    return f"{scene}-{1280 if viewport['width'] >= PHONE_BREAKPOINT else 390}"


def the_scene_draws_the_wait_pill_in(person: Page) -> str:
    """The type size of the pill in the frozen scene series-next at the person's width, read from the scene itself."""
    frame = scene_frame_at(person, "series-next")
    scene = person.context.new_page()
    try:
        scene.goto(f"{TABLE_SCENES.as_uri()}?f={frame}")
        return scene.locator(f"[id='{frame}'] .cb.wide.glass", has_text=waiting_for(["Ben"])).evaluate(FONT_SIZE_OF)
    finally:
        scene.close()


def the_scene_draws_the_settings_sheet_in(person: Page) -> dict[str, float]:
    """The room above and below the sheet of the frozen scene seriesend-settings at the person's width."""
    frame = scene_frame_at(person, "seriesend-settings")
    scene = person.context.new_page()
    try:
        scene.goto(f"{TABLE_SCENES.as_uri()}?f={frame}")
        return scene.locator(f"[id='{frame}'] .setsheet").evaluate(SHEET_MARGINS_OF)
    finally:
        scene.close()


def expect_the_boxes_to_sit_as_the_scene_draws_them(
    person: Page, scene: str, selector: str, scene_selector: str | None = None
) -> None:
    """Each box of the selector settles within a few pixels of the box the frozen scene draws, read from it.

    The scenes draw 390 and 1280 px; the smaller phone keeps its boxes inside the panel by the same rules.
    """
    if person.viewport_size == SMALL_PHONE["viewport"]:
        return
    frame = scene_frame_at(person, scene)
    drawn = person.context.new_page()
    try:
        drawn.goto(f"{TABLE_SCENES.as_uri()}?f={frame}")
        wanted = drawn.evaluate(BOXES_OF, [scene_selector or selector, frame])
    finally:
        drawn.close()
    boxes = person.evaluate(BOXES_OF, [selector, None])
    deadline = time.monotonic() + SETTLE_SECONDS
    while boxes != pytest.approx(wanted, abs=SCENE_SPACING) and time.monotonic() < deadline:
        person.wait_for_timeout(SETTLE_POLL_MILLISECONDS)
        boxes = person.evaluate(BOXES_OF, [selector, None])
    assert boxes == pytest.approx(wanted, abs=SCENE_SPACING), selector
