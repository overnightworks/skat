from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

# The boxes are read in the browser in one pass, so a mark that leaves meanwhile is no stale handle that blocks a call.
OVERLAPS = """
    const overlaps = (first, second) =>
        first.x < second.x + second.width && second.x < first.x + first.width
        && first.y < second.y + second.height && second.y < first.y + first.height
    const boxOf = element => element.getClientRects().length ? element.getBoundingClientRect() : null
"""
COVERED_BY = (
    "({covering, covered}) => {"
    + OVERLAPS
    + """
    const offenders = []
    let shown = 0
    for (const own of document.querySelectorAll(covering)) {
        const box = boxOf(own)
        if (box === null) continue
        shown += 1
        for (const selector of covered) {
            for (const other of document.querySelectorAll(selector)) {
                const there = boxOf(other)
                if (there !== null && overlaps(box, there)) offenders.push(selector)
            }
        }
    }
    if (shown === 0) throw new Error(`no shown element of ${covering}`)
    return offenders
}"""
)


def covered_by(page: Page, covering: str, covered: tuple[str, ...]) -> list[str]:
    """The selectors among `covered` whose shown elements overlap a shown element of `covering`, in one browser pass.

    It raises when no element of `covering` is shown, since nothing is then checked.
    """
    return page.evaluate(COVERED_BY, {"covering": covering, "covered": list(covered)})
