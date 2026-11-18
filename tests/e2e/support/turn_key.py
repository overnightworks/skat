import json
from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

SETTINGS_KEY = "skat.settings"
# What of a key moves: the key itself pops, the ring around it grows and fades, the sheen inside it runs.
MOTION_OF_A_KEY = """key => key.getAnimations({ subtree: true }).map(each => {
    if (each.effect.target !== key) return "sheen";
    return each.effect.pseudoElement === "::after" ? "ring" : "pop";
})"""
# The key the table waits on from the viewer, while it can be pressed.
POPS_RINGS_AND_SHINES = frozenset({"pop", "ring", "sheen"})


def let_it_move(person: Page, motion_set: str = "verspielt") -> Page:
    """The page moves in `motion_set` although its device asks for less, from the reload this makes on."""
    stored = {"replayMotion": True, "motionSet": motion_set}
    person.add_init_script(f"localStorage.setItem({SETTINGS_KEY!r}, {json.dumps(json.dumps(stored))})")
    person.reload()
    expect(person.locator(".chair")).to_have_count(3)
    return person


def motion_of(key: Locator) -> frozenset[str]:
    """What of the key moves or holds where its motion ended; a key the table does not wait on has none."""
    return frozenset(key.evaluate(MOTION_OF_A_KEY))
