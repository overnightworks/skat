"""Today's table surface as the end-to-end helpers read it.

Every selector, class and attribute of the table page's markup that a helper of this package uses stands here, and the
helpers reach the page only through this module. A function gives the part of the page a helper acts on, or runs the
script that names markup. A constant is a selector or an in-page reader for a helper's script that takes one, and a
selector for a test module that locates by it.
"""

import json
from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import FrameLocator, Locator, Page

type Scope = Page | FrameLocator


CHAIR = ".chair"
TURN_CHAIR = ".chair.turn"
DECLINED_MARK = ".mark.declined"
OPEN_CARDS = ".open"
OPEN_TAG = ".open-tag"
SEAT_NOTICE = ".notice.seat"
PUSH_BUBBLE = ".chair .bubble.word"
WATCHERS = ".watchers span"
_SEAT = "data-seat"


def _chair_of(seat: int) -> str:
    return f"{CHAIR}[{_SEAT}='{seat}']"


def chairs(scope: Scope) -> Locator:
    return scope.locator(CHAIR)


def chair(scope: Scope, seat: int) -> Locator:
    return scope.locator(_chair_of(seat))


def in_chair(scope: Scope, seat: int, selector: str) -> Locator:
    """What `selector` finds inside the chair of `seat`."""
    return scope.locator(f"{_chair_of(seat)} {selector}")


def plate(scope: Scope, seat: int) -> Locator:
    return in_chair(scope, seat, ".plate")


def own_chair(scope: Scope) -> Locator:
    return scope.locator(".chair.mine")


def own_seat(scope: Scope) -> int:
    return int(own_chair(scope).get_attribute(_SEAT) or "")


def expect_the_own_chair_at(scope: Scope, seat: int) -> None:
    expect(own_chair(scope)).to_have_attribute(_SEAT, str(seat))


def turn_chair(scope: Scope) -> Locator:
    return scope.locator(TURN_CHAIR)


def expect_the_turn_at(scope: Scope, seat: int) -> None:
    expect(turn_chair(scope)).to_have_attribute(_SEAT, str(seat))


def position_marks(scope: Scope) -> Locator:
    return scope.locator(".mark.pos")


def count_tags(scope: Scope) -> Locator:
    return scope.locator(".count-tag")


def push_bubbles(scope: Scope) -> Locator:
    return scope.locator(PUSH_BUBBLE)


def watchers(scope: Scope) -> Locator:
    return scope.locator(WATCHERS)


# A JS function giving how many square pixels of a mark's box lie in the top-left quarter of a tile's box.
QUARTER_OVERLAP_JS = """(mark, tile) =>
    Math.max(0, Math.min(mark.right, tile.left + tile.width / 2) - Math.max(mark.left, tile.left))
    * Math.max(0, Math.min(mark.bottom, tile.top + tile.height / 2) - Math.max(mark.top, tile.top))"""

# What the page's chairs draw, read in the frame: which marks lie in a tile's top-left quarter or under its position
# label, whether an own-seat bar shows its glass, whether any tile rim lies inside its box, and how the dashed
# agent rim lies against its box (the probe gives each tile the agent class).
_CHAIR_LOOK_PROBE = """chairs => {
    const quarterOverlap = QUARTER_OVERLAP;
    const look = {
        marks: 0, marksInTopLeftQuarter: 0, positionedMarks: 0, marksOverPositionLabel: 0, barPillsShown: 0,
        rimsInsideTile: 0, agentRimInsideTile: 0, mostMarksOnAChair: 0,
    };
    for (const chair of chairs) {
        const tile = chair.querySelector(".tile");
        if (!tile) continue;
        const box = tile.getBoundingClientRect();
        const label = chair.querySelector(".mark.pos");
        const labelBox = label && label.getBoundingClientRect();
        const pill = chair.querySelector(".bar-pill");
        if (pill && getComputedStyle(pill).display !== "none") look.barPillsShown += 1;
        const chairMarks = chair.querySelectorAll(".mark:not(.pos)");
        look.mostMarksOnAChair = Math.max(look.mostMarksOnAChair, chairMarks.length);
        for (const mark of chairMarks) {
            look.marks += 1;
            const at = mark.getBoundingClientRect();
            if (labelBox && at.right > labelBox.left && at.left < labelBox.right
                && at.bottom > labelBox.top && at.top < labelBox.bottom) look.marksOverPositionLabel += 1;
            if (quarterOverlap(at, box) > 0) look.marksInTopLeftQuarter += 1;
            if (getComputedStyle(mark).position === "absolute") look.positionedMarks += 1;
        }
        if (getComputedStyle(tile).boxShadow.includes("inset")) look.rimsInsideTile += 1;
        tile.classList.add("agent");
        const rim = getComputedStyle(tile, "::before");
        if (parseFloat(rim.top) + parseFloat(rim.borderTopWidth) > 0
            || parseFloat(rim.left) + parseFloat(rim.borderLeftWidth) > 0) look.agentRimInsideTile += 1;
        tile.classList.remove("agent");
    }
    return look;
}""".replace("QUARTER_OVERLAP", QUARTER_OVERLAP_JS)


def chair_look(scope: Scope) -> dict[str, int]:
    """Counts of the chairs' marks and rims as `_CHAIR_LOOK_PROBE` reads them in `scope`."""
    look: dict[str, int] = chairs(scope).evaluate_all(_CHAIR_LOOK_PROBE)
    return look


FELT_FACE = ".trick .laid .face"
SKAT_CARD = ".skat-card"
# The fan shows each card's left strip, and the next card covers its middle, where a plain click lands. A touch within
# a few pixels of a card's edge reaches the neighbouring card although the point lies on the aimed one, so a tap
# aims at the strip's middle, where a finger lands too.
INSIDE_THE_VISIBLE_STRIP = {"x": 15, "y": 40}


def tap_card(card: Locator) -> None:
    card.click(position=INSIDE_THE_VISIBLE_STRIP)


def skat_cards(scope: Scope) -> Locator:
    return scope.locator(SKAT_CARD)


def own_cards(scope: Scope) -> Locator:
    return scope.locator(".own-hand .card")


def card_faces(scope: Scope) -> Locator:
    return scope.locator(".card-face")


BID_BAR = ".bid"
BID_STEP_KEY = ".bid-keys .button-stage"
BID_LIMIT_KEY = ".bid-keys .button-brass"
BID_PASS_KEY = ".bid-chips .button-glass"
BID_CHIPS = ".bid-chip:not(.more)"
BID_MORE_CHIP = ".bid-chip.more"
BID_SCALE = ".scale"
BID_LIMIT_VALUE = ".bid-line .bis b"
# The part of the page every change of the auction happens in.
STAGE = ".stage"
# A JS function giving what the page shows of its auction, as text two moments compare by: the digits on the counter's
# drums and, by seat, the word in each chair's bubble and whether the chair is out. Names are left out, since each seat
# reads its own as „Du“.
AUCTION_AS_SHOWN = """() => JSON.stringify({
    counter: [...document.querySelectorAll('.counter .drum')].map((drum) => drum.textContent.trim()).join(''),
    chairs: Object.fromEntries([...document.querySelectorAll('.chair[data-seat]')].map((chair) => [
        chair.dataset.seat,
        { says: chair.querySelector('.bubble .said')?.textContent ?? null, out: chair.classList.contains('out') },
    ])),
})"""


def bid_bar(scope: Scope) -> Locator:
    return scope.locator(BID_BAR)


def bid_chip_row(scope: Scope) -> Locator:
    return scope.locator(".bid-chips")


def bid_scale(scope: Scope) -> Locator:
    return scope.locator(BID_SCALE)


def counter_word(scope: Scope) -> Locator:
    return scope.locator(".counter .word")


ACTIONS = ".actions"
REQUEST = ".plaque.ask"
REQUEST_AND_NOTICE = f"{REQUEST}, {SEAT_NOTICE}"
KONTRA_KEY = ".copy.kontra"
CALLOUT = ".callout"
KONTRA_KEY_CALLOUT_AND_KEYS = f"{KONTRA_KEY}, {CALLOUT}, {ACTIONS} > :not(.anchored-overlay)"
# What of a key moves: the key itself pops, the ring around it grows and fades, the sheen inside it runs.
_MOTION_OF_A_KEY = """key => key.getAnimations({ subtree: true }).map(each => {
    if (each.effect.target !== key) return "sheen";
    return each.effect.pseudoElement === "::after" ? "ring" : "pop";
})"""


def requests(scope: Scope) -> Locator:
    return scope.locator(REQUEST)


def note(scope: Scope) -> Locator:
    return scope.locator(".note")


def own_hand_and_actions(scope: Scope) -> Locator:
    return scope.locator(f".own-hand, {ACTIONS}")


def motion_of_a_key(key: Locator) -> list[str]:
    """What of the key moves or holds where its motion ended, one word per animation."""
    return key.evaluate(_MOTION_OF_A_KEY)


RAMSCH_PLAQUE = ".plaque.ramsch"
# What the push bubble shares a box with: any other bubble and every key on the page, as the names of their classes.
_COVERED_BY_THE_PUSH_BUBBLE = """() => {
    const inside = (box, other) => box.left < other.right && box.right > other.left
        && box.top < other.bottom && box.bottom > other.top;
    return [...document.querySelectorAll(PUSH_BUBBLE)].flatMap((push) => {
        const box = push.getBoundingClientRect();
        return [...document.querySelectorAll('.bubble, button')]
            .filter((other) => other !== push && other.getClientRects().length > 0
                && inside(box, other.getBoundingClientRect()))
            .map((other) => other.textContent.trim() || other.className);
    });
}""".replace("PUSH_BUBBLE", json.dumps(PUSH_BUBBLE))


def ramsch_plaque(scope: Scope) -> Locator:
    return scope.locator(RAMSCH_PLAQUE)


def ramsch_plaque_lines(scope: Scope) -> Locator:
    return scope.locator(f"{RAMSCH_PLAQUE} .game:not(.pushes)")


def covered_by_the_push_bubble(page: Page) -> list[str]:
    return page.evaluate(_COVERED_BY_THE_PUSH_BUBBLE)


RESULT_CARD = ".result"
SERIES_COUNT = ".series-count"
NEXT_SERIES_LINE = ".result.standing .nextline"
NEXT_SERIES_SHEET = ".sheet.next-series"


def result_card(scope: Scope) -> Locator:
    return scope.locator(RESULT_CARD)


def result_stamp(scope: Scope) -> Locator:
    return scope.locator(f"{RESULT_CARD} .stamp")


def result_stamp_author(scope: Scope) -> Locator:
    return result_stamp(scope).locator(".by")


def reckoning_tiles(scope: Scope) -> Locator:
    return scope.locator(f"{RESULT_CARD} .reck")


def reckoning_names(scope: Scope) -> Locator:
    return result_card(scope).locator(".nm")


def reckoning_name(scope: Scope, seat: int) -> Locator:
    return result_card(scope).locator(f".reck[{_SEAT}='{seat}'] .nm")


def gone_note(scope: Scope, seat: int) -> Locator:
    """The note in the seat's reckoning name that its person left the series."""
    return reckoning_name(scope, seat).locator("em")


def series_count(scope: Scope) -> Locator:
    return scope.locator(SERIES_COUNT)


MENU_KEY = ".menu-key"
TABLE_MENU = ".anchored-panel:has(.table-menu)"
GIVE_UP_ROW = ".row.give-up"
SHORTEN_ROW = ".row.shorten"
PLAY_OPEN_ROW = ".row.play-open"
AGENTS_PANEL = ".anchored-panel:has(.agents-list)"
ACCOUNT_PANEL = ".anchored-panel:has(nav.legal)"


def menu_key(scope: Scope) -> Locator:
    return scope.locator(MENU_KEY)


def table_menu(scope: Scope) -> Locator:
    return scope.locator(TABLE_MENU)


def agents_panel(scope: Scope) -> Locator:
    return scope.locator(AGENTS_PANEL)


def account_panel(scope: Scope) -> Locator:
    return scope.locator(ACCOUNT_PANEL)


ROOM = ".room"
# The cocktail and the shell lie under everything the people at the table read and touch: no sampled point of a card,
# tag, key, chair, plaque, counter or the result is painted by one of them (their pointer events are switched on so the
# page can say what it paints there), no key of the bid bar paints the middle of one of them, and the page gains no
# sideways scroll from the rim round the felt. A chair's stool is drawn behind its chair and the cards, as the scenes
# draw it, and covers nothing.
_FURNITURE_CLEAR = """() => {
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


def room(scope: Scope) -> Locator:
    return scope.locator(ROOM)


def expect_the_style(scope: Scope, style: str) -> None:
    expect(room(scope)).to_have_attribute("data-style", style)


def style_tile(scope: Scope, style: str) -> Locator:
    return scope.locator(f".style-tile.style-{style}")


def furniture(scope: Scope) -> Locator:
    return scope.locator(".decor")


def furniture_in_the_way(page: Page) -> list[str]:
    """What the style's furniture covers and what hides it, as `_FURNITURE_CLEAR` reads it; nothing when it is clear."""
    return page.evaluate(_FURNITURE_CLEAR)
