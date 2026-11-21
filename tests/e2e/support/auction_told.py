from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Keeps on window.auctionShown what the page shows of its auction each time that changes, from now on: the digits on
# the counter's drums and, by seat, the word in each chair's bubble and whether the chair is out. Names are left out,
# since each seat reads its own as „Du“. Beside each entry window.auctionHeard keeps how many recordings the page's
# voice had started by then.
WATCHING_THE_AUCTION = """() => {
    const shown = () => JSON.stringify({
        counter: [...document.querySelectorAll('.counter .drum')].map((drum) => drum.textContent.trim()).join(''),
        chairs: Object.fromEntries([...document.querySelectorAll('.chair[data-seat]')].map((chair) => [
            chair.dataset.seat,
            { says: chair.querySelector('.bubble .said')?.textContent ?? null, out: chair.classList.contains('out') },
        ])),
    });
    window.auctionShown = [shown()];
    window.auctionHeard = [window.recordingsStarted.length];
    new MutationObserver(() => {
        const now = shown();
        if (now === window.auctionShown.at(-1)) return;
        window.auctionShown.push(now);
        window.auctionHeard.push(window.recordingsStarted.length);
    }).observe(document.querySelector('.stage'), {
        subtree: true, childList: true, characterData: true, attributes: true,
    });
}"""


def watch_the_auction(page: Page) -> None:
    """Keeps what `page` shows of its auction from now on, each time it changes."""
    page.evaluate(WATCHING_THE_AUCTION)


def auction_shown(page: Page) -> list[dict[str, Any]]:
    """What `page` showed of its auction since it was watched, one entry per change, in order."""
    return page.evaluate("window.auctionShown.map((shown) => JSON.parse(shown))")


def words_heard(page: Page) -> list[int]:
    """How many recordings the voice of `page` had started at each entry of what the page showed."""
    return page.evaluate("window.auctionHeard")


def shown(counter: str, chairs: dict[int, tuple[str | None, bool]]) -> dict[str, Any]:
    """One entry of what a page shows: the counter's digits and, by seat, the chair's word and whether it is out."""
    return {
        "counter": counter,
        "chairs": {str(seat): {"says": says, "out": out} for seat, (says, out) in chairs.items()},
    }
