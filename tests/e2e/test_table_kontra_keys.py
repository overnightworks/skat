import re
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import button_of
from tests.e2e.support.hands import deal_playing_table
from tests.e2e.support.kontra import ContestedTable, FirstCardTable
from tests.e2e.support.people import DESKTOP, PHONE, SMALL_PHONE

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

KONTRA = text(SOURCE_LANGUAGE, "kontra.kontra")
RE = text(SOURCE_LANGUAGE, "kontra.re")
TABLE_SCENES = Path(__file__).parents[2] / "docs" / "mockups" / "table.html"
# The scenes frame the narrowest phone at 360 x 780.
NARROW_PHONE = {**SMALL_PHONE, "viewport": {"width": 360, "height": 780}}
FRAME_WIDTHS = [pytest.param(NARROW_PHONE, id="360"), pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1280")]
SCENE_KEY = ".cb.wide"
PAGE_KEYS = ".actions .copy"
ONE_PIXEL = 1
CENTRED_WITHIN = 2
# A key's size, its mark and its word, read where it is drawn.
KEY_GEOMETRY = """key => {
    const box = key.getBoundingClientRect();
    const mark = key.querySelector("svg");
    return {
        width: box.width,
        height: box.height,
        left: box.left,
        right: box.right,
        mark: mark !== null && getComputedStyle(mark).display !== "none",
        word: key.textContent.trim(),
    };
}"""
BOXES = """keys => keys.map(key => {
    const box = key.getBoundingClientRect();
    return {left: box.left, right: box.right, top: box.top, bottom: box.bottom};
})"""

TABLES = [
    pytest.param(ContestedTable, "kontra-offer", "kontra-re", id="own-card"),
    pytest.param(FirstCardTable, "kontra-first-wait", "kontra-first-re", id="first-card"),
]


def decline_of(word: str) -> str:
    return text(SOURCE_LANGUAGE, "kontra.decline", word=word)


def exactly(label: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*{re.escape(label)}\s*$")


def the_scene_draws(person: Page, frame: str, word: str, *, declines: bool) -> dict[str, Any]:
    """The geometry of the key that says `word` and, where the table asks both, of the key declining it, in a scene."""
    viewport = person.viewport_size
    assert viewport is not None
    scene = person.context.new_page()
    try:
        scene.goto(f"{TABLE_SCENES.as_uri()}?f={frame}-{viewport['width']}")
        keys = scene.locator(f"[id='{frame}-{viewport['width']}'] {SCENE_KEY}")
        drawn = {"word": keys.filter(has_text=exactly(word)).evaluate(KEY_GEOMETRY)}
        if declines:
            drawn["decline"] = keys.filter(has_text=exactly(decline_of(word))).evaluate(KEY_GEOMETRY)
        return drawn
    finally:
        scene.close()


def the_page_draws(person: Page, word: str, *, declines: bool) -> dict[str, Any]:
    drawn = {"word": button_of(person, word).evaluate(KEY_GEOMETRY)}
    if declines:
        drawn["decline"] = button_of(person, decline_of(word)).evaluate(KEY_GEOMETRY)
    return drawn


def expect_the_keys_to_match_the_scene(person: Page, frame: str, word: str, *, declines: bool) -> None:
    drawn = the_page_draws(person, word, declines=declines)
    viewport = person.viewport_size
    assert viewport is not None
    on_a_phone = viewport["width"] < DESKTOP["viewport"]["width"]
    # The opener's close key is the sixth key of a phone's strip, which the scenes do not draw: the word loses its mark.
    if on_a_phone and not declines and person.locator(".actions > .copy.close").count() == 1:
        assert not drawn["word"]["mark"]
        return
    scene = the_scene_draws(person, frame, word, declines=declines)
    for name, key in scene.items():
        assert drawn[name]["word"] == key["word"]
        assert drawn[name]["mark"] == key["mark"], (name, drawn[name], key)
        assert abs(drawn[name]["width"] - key["width"]) <= ONE_PIXEL, (name, drawn[name], key)
        assert abs(drawn[name]["height"] - key["height"]) <= ONE_PIXEL, (name, drawn[name], key)
    if declines:
        assert abs(gap_between(drawn) - gap_between(scene)) <= ONE_PIXEL, (drawn, scene)
        if on_a_phone:
            assert abs(centre_of(drawn) - centre_of(scene)) <= CENTRED_WITHIN, (drawn, scene)


def gap_between(keys: dict[str, Any]) -> float:
    return keys["decline"]["left"] - keys["word"]["right"]


def centre_of(keys: dict[str, Any]) -> float:
    return (keys["word"]["left"] + keys["decline"]["right"]) / 2


def expect_the_rows_to_fit(person: Page) -> None:
    """Every key lies inside the screen and clear of the others, and the stage that holds them ends on the screen."""
    viewport = person.viewport_size
    assert viewport is not None
    assert person.locator(".stage").evaluate("stage => stage.getBoundingClientRect().bottom") <= viewport["height"]
    boxes = person.locator(PAGE_KEYS).evaluate_all(BOXES)
    for box in boxes:
        assert box["left"] >= 0, box
        assert box["right"] <= viewport["width"], box
        assert box["bottom"] <= viewport["height"], box
    for first, second in combinations(boxes, 2):
        apart_across = first["right"] <= second["left"] or second["right"] <= first["left"]
        apart_down = first["bottom"] <= second["top"] or second["bottom"] <= first["top"]
        assert apart_across or apart_down, (first, second)


@pytest.mark.parametrize("form_factor", FRAME_WIDTHS)
@pytest.mark.parametrize(("table_kind", "word_frame", "re_frame"), TABLES)
def test_the_kontra_and_re_keys_have_the_scenes_size_mark_and_word_and_every_key_stays_on_the_screen(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
    table_kind: type[ContestedTable],
    word_frame: str,
    re_frame: str,
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, declaring=table_kind)
    asks_both = table_kind is FirstCardTable
    sayer = table.pages[table.seat_at["forehand"]]
    declarer = table.pages[table.declarer_seat]
    expect(button_of(sayer, KONTRA)).to_be_visible()

    expect_the_keys_to_match_the_scene(sayer, word_frame, KONTRA, declines=asks_both)
    expect_the_rows_to_fit(sayer)

    button_of(sayer, KONTRA).click()
    expect(button_of(declarer, RE)).to_be_visible()

    expect_the_keys_to_match_the_scene(declarer, re_frame, RE, declines=asks_both)
    for person in table.everyone:
        expect_the_rows_to_fit(person)
    assert page_errors == []
