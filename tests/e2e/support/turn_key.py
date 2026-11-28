import json
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.e2e.support import old_surface

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

SETTINGS_KEY = "skat.settings"
# The key the table waits on from the viewer, while it can be pressed.
POPS_RINGS_AND_SHINES = frozenset({"pop", "ring", "sheen"})


def let_it_move(person: Page, motion_set: str = "verspielt") -> Page:
    """The page moves in `motion_set` although its device asks for less, from the reload this makes on."""
    stored = {"replayMotion": True, "motionSet": motion_set}
    person.add_init_script(f"localStorage.setItem({SETTINGS_KEY!r}, {json.dumps(json.dumps(stored))})")
    person.reload()
    expect(old_surface.chairs(person)).to_have_count(3)
    return person


def motion_of(key: Locator) -> frozenset[str]:
    """What of the key moves or holds where its motion ended; a key the table does not wait on has none."""
    return frozenset(old_surface.motion_of_a_key(key))
