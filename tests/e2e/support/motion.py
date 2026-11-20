from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

# A laid card's slot as the scenes draw it, turned and in its place. The card itself lies off it by its own lie, so what
# the layout promises about a card's place is measured on the slot.
FELT_SLOT = ".trick .laid .hang"
# Keeps every animation the page starts through the Web Animations API on window.motionPlayed, as the piece it moves,
# the seat of the laid card the piece belongs to, the frames and the length. Takt plays a moment as such animations.
RECORDING_MOTION = """(() => {
    if (window.motionPlayed !== undefined) return;
    window.motionPlayed = [];
    const animate = Element.prototype.animate;
    Element.prototype.animate = function recordingAnimate(frames, milliseconds) {
        const laid = this.closest('.laid');
        window.motionPlayed.push({
            piece: this.classList[0],
            seat: laid === null ? null : Number(laid.dataset.seat),
            frames,
            milliseconds,
        });
        return animate.call(this, frames, milliseconds);
    };
})()"""
# How each laid card rests, by the name of its face: how far its middle lies off the middle of its slot, in card widths
# across and down the page, and the degrees it is turned on top of its slot's turn.
LIES = """() => Object.fromEntries([...document.querySelectorAll('.trick .laid')].map((slot) => {
    const middleOf = (element) => {
        const box = element.getBoundingClientRect();
        return [box.left + box.width / 2, box.top + box.height / 2];
    };
    const face = slot.querySelector('.face');
    const [slotX, slotY] = middleOf(slot);
    const [x, y] = middleOf(face);
    const turned = new DOMMatrixReadOnly(getComputedStyle(slot.querySelector('.lying')).transform);
    const slotTurned = new DOMMatrixReadOnly(getComputedStyle(slot.querySelector('.hang')).transform);
    const degrees = (matrix) => Math.atan2(matrix.b, matrix.a) * 180 / Math.PI;
    return [face.getAttribute('aria-label'), {
        x: (x - slotX) / slot.offsetWidth,
        y: (y - slotY) / slot.offsetWidth,
        turn: degrees(turned) - degrees(slotTurned),
    }];
}))"""
# The points of a name tag's straight middle part, where its rounded ends hide nothing, that something else than the tag
# paints; the trick answers for what it paints while its pointer events are on.
NAMES_UNDER_SOMETHING = """() => {
    const trick = document.querySelector('.trick');
    trick.style.pointerEvents = 'auto';
    const covered = [...trick.querySelectorAll('.laid .tag')].flatMap((tag) => {
        const box = tag.getBoundingClientRect();
        const found = [];
        for (let x = box.left + box.height / 2; x <= box.right - box.height / 2; x += 2) {
            for (let y = box.top + 1; y < box.bottom; y += 2) {
                const painted = document.elementFromPoint(x, y);
                if (!tag.contains(painted)) found.push(`${painted?.className} over ${tag.textContent.trim()}`);
            }
        }
        return [...new Set(found)];
    });
    trick.style.pointerEvents = '';
    return covered;
}"""
TURNS_OVER = "turns over"
FADES_IN = "fades in"
FLIES_FACE_UP = "flies face up"
LIES_AT_ONCE = "lies at once"


def watch_the_motion(page: Page) -> None:
    """Keeps what `page` plays from now on, also after it loads again."""
    page.add_init_script(RECORDING_MOTION)
    page.evaluate(RECORDING_MOTION)


def motion_played(page: Page) -> list[dict[str, Any]]:
    """The animations `page` started since it was watched or last loaded, in the order they started."""
    return page.evaluate("window.motionPlayed")


def wait_for_the_motion_to_end(page: Page) -> None:
    page.wait_for_function("() => document.querySelector('.trick').getAnimations({ subtree: true }).length === 0")


def arrival_of(played: list[dict[str, Any]]) -> str:
    """How the one card these animations move came onto the felt."""
    if not played:
        return LIES_AT_ONCE
    frames = {piece["piece"]: piece["frames"] for piece in played}
    if any(frame["opacity"] == 1 for frame in frames["rear"]):
        return TURNS_OVER
    return FADES_IN if frames["face"][0]["opacity"] == 0 else FLIES_FACE_UP


def last_seconds_in_the_air(played: list[dict[str, Any]]) -> float:
    """The last instant the frames of the one card these animations move show it above its shade.

    The card touches the felt within the frame that follows, and lies on its shade from then on.
    """
    pieces = {piece["piece"]: piece for piece in played}
    face, shade = pieces["face"]["frames"], pieces["shade"]["frames"]
    in_the_air = [index for index, frame in enumerate(face) if frame["transform"] != shade[index]["transform"]]
    return in_the_air[-1] / (len(face) - 1) * pieces["face"]["milliseconds"] / 1000


def lies_on_the_felt(page: Page) -> dict[str, dict[str, float]]:
    """How each card on `page`'s felt rests off its slot, by the card's name."""
    return page.evaluate(LIES)


def names_under_something(page: Page) -> list[str]:
    """The name tags of the trick that something on `page` covers, each with what covers it."""
    return page.evaluate(NAMES_UNDER_SOMETHING)
