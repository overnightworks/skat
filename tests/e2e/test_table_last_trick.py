import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.support.audio import voices_started
from tests.e2e.support.browser import record_page_errors
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import WIDTHS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

FELT_CARD = ".trick .laid"
SWEEPING = ".trick.sweeping"
PILE = ".pile"
RIMMED_PILE = ".pile.last"
LAST_TRICK_SHOWN = ".lastshow"
SETTINGS_KEY = "skat.settings"
CARDS_IN_A_TRICK = 3
# The page owns how long a trick rests and glides; the clock is stepped this far at a time until a phase shows.
CLOCK_STEP_MILLISECONDS = 50
# Further than any set rests and glides together, so a trick still on the felt after it is meant to lie there.
FAR_PAST_ANY_SWEEP_MILLISECONDS = 5000
# A sweep sounds one noise voice in the set „Leise“.
VOICES_OF_ONE_SWEEP = 1
# A card sounds as one noise burst and one tone.
VOICES_OF_THREE_CARDS = 6
HAND_CARD = ".own-hand .card"
# An installed clock keeps ticking until paused, and pausing only moves time forward, so it stops this far ahead.
CLOCK_HOLD_LEAD = timedelta(seconds=5)


@pytest.fixture
def table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> PlayingTable:
    return deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor)


def open_watcher(
    open_person: Callable[..., Page],
    page_errors: list[str],
    table: PlayingTable,
    form_factor: dict[str, Any],
    *,
    stored: dict[str, Any] | None = None,
    moving: bool = True,
    clock: bool = True,
) -> Page:
    """The table's watcher page, moving unless the device asks for less, with a clock only the test moves."""
    watcher = record_page_errors(
        open_person(reduced_motion="no-preference" if moving else "reduce", **form_factor), page_errors
    )
    if stored is not None:
        watcher.add_init_script(f"localStorage.setItem({SETTINGS_KEY!r}, {json.dumps(json.dumps(stored))})")
    if clock:
        watcher.clock.install()
        watcher.clock.pause_at(datetime.now(UTC) + CLOCK_HOLD_LEAD)
    watcher.goto(table.watcher.url)
    expect(watcher.locator(".chair")).to_have_count(3)
    # The first key press wakes the sound.
    watcher.keyboard.press("Shift")
    return watcher


def hide_the_tab(page: Page, *, hidden: bool) -> None:
    page.evaluate(
        """hidden => {
            Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
            document.dispatchEvent(new Event("visibilitychange"));
        }""",
        hidden,
    )


def run_until(page: Page, phase: str, count: int) -> int:
    """Steps the held clock until `count` elements show `phase`, and returns the milliseconds that took."""
    elapsed = 0
    while page.locator(phase).count() != count:
        assert elapsed < FAR_PAST_ANY_SWEEP_MILLISECONDS, f"{phase} never showed {count} elements"
        page.clock.run_for(CLOCK_STEP_MILLISECONDS)
        elapsed += CLOCK_STEP_MILLISECONDS
    return elapsed


def rest_and_sweep(page: Page) -> tuple[int, int]:
    """Runs a finished trick through its rest and its sweep; the milliseconds each took."""
    rest = run_until(page, SWEEPING, 1)
    return rest, run_until(page, FELT_CARD, 0)


def taker_of_the_last_trick(table: PlayingTable) -> int:
    return table.playing()["last_trick"]["taker_seat"]


def expect_the_piles(page: Page, table: PlayingTable) -> None:
    """Every seat's pile holds one back for each trick it has taken, and no seat that took none has a pile."""
    for taken in table.playing()["taken"]:
        pile = page.locator(f"{PILE}[data-seat='{taken['seat']}']")
        expect(pile).to_have_count(1 if taken["tricks"] else 0)
        if taken["tricks"]:
            expect(pile.locator(".card")).to_have_count(taken["tricks"])


def expect_the_rim_on(page: Page, seat: int | None) -> None:
    rim = page.locator(RIMMED_PILE)
    expect(rim).to_have_count(0 if seat is None else 1)
    if seat is not None:
        expect(rim).to_have_attribute("data-seat", str(seat))
        assert rim.evaluate("pile => pile.tagName") == "BUTTON"


def expect_nobody_on_turn(page: Page) -> None:
    expect(page.locator(".chair.turn")).to_have_count(0)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_finished_trick_rests_then_sweeps_to_its_winner_with_one_sweep_sound_and_rests_on_the_pile(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    watcher = open_watcher(open_person, page_errors, table, form_factor)
    table.play_out(CARDS_IN_A_TRICK)

    expect(watcher.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK)
    first_taker = taker_of_the_last_trick(table)
    expect_nobody_on_turn(watcher)
    expect(watcher.locator(PILE)).to_have_count(0)
    expect(watcher.locator(SWEEPING)).to_have_count(0)
    sounded_before = len(voices_started(watcher))

    assert run_until(watcher, SWEEPING, 1) > 0

    expect(watcher.locator(SWEEPING)).to_have_count(1)
    expect(watcher.locator(f".chair.got[data-seat='{first_taker}']")).to_have_count(1)
    names = watcher.locator(FELT_CARD).first.evaluate("card => card.getAnimations().map(each => each.animationName)")
    assert "sweep-verspielt" in names
    assert len(voices_started(watcher)) == sounded_before + VOICES_OF_ONE_SWEEP
    expect(watcher.locator(f"{PILE}[data-seat='{first_taker}'] .card.landing")).to_have_count(1)

    run_until(watcher, FELT_CARD, 0)

    expect(watcher.locator(FELT_CARD)).to_have_count(0)
    expect(watcher.locator(".chair.got")).to_have_count(0)
    expect_the_piles(watcher, table)
    expect_the_rim_on(watcher, first_taker)
    expect(watcher.locator(f".chair.turn[data-seat='{table.turn_seat()}']")).to_have_count(1)

    sounded_after_first_sweep = len(voices_started(watcher))
    table.play_out(CARDS_IN_A_TRICK)

    expect(watcher.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK)
    expect_nobody_on_turn(watcher)
    expect_the_rim_on(watcher, first_taker)
    second_taker = taker_of_the_last_trick(table)
    rest_and_sweep(watcher)
    expect(watcher.locator(FELT_CARD)).to_have_count(0)
    expect_the_piles(watcher, table)
    expect_the_rim_on(watcher, second_taker)
    assert len(voices_started(watcher)) == sounded_after_first_sweep + VOICES_OF_THREE_CARDS + VOICES_OF_ONE_SWEEP
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_quiet_set_rests_shorter_and_glides_straight(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    quiet = open_watcher(open_person, page_errors, table, form_factor, stored={"motionSet": "dezent"})
    playful = open_watcher(open_person, page_errors, table, form_factor)
    table.play_out(CARDS_IN_A_TRICK)
    expect(quiet.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK)
    expect(playful.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK)

    quiet_rest = run_until(quiet, SWEEPING, 1)

    names = quiet.locator(FELT_CARD).first.evaluate("card => card.getAnimations().map(each => each.animationName)")
    assert "sweep-dezent" in names
    quiet_sweep = run_until(quiet, FELT_CARD, 0)
    expect_the_piles(quiet, table)
    playful_rest, playful_sweep = rest_and_sweep(playful)
    assert quiet_rest < playful_rest
    assert quiet_sweep < playful_sweep
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_tap_on_the_winners_pile_shows_the_last_trick_and_any_tap_or_the_next_card_closes_it(
    table: PlayingTable, page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table.play_out(CARDS_IN_A_TRICK)
    taker = taker_of_the_last_trick(table)
    last = table.playing()["last_trick"]
    seated = table.pages[taker]
    expect_the_piles(seated, table)
    expect_the_rim_on(seated, taker)
    posts: list[str] = []
    seated.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)

    seated.locator(RIMMED_PILE).click()

    shown = seated.locator(LAST_TRICK_SHOWN)
    expect(shown).to_have_count(1)
    faces = shown.locator(".card-face")
    expect(faces).to_have_count(CARDS_IN_A_TRICK)
    drawn = faces.evaluate_all("faces => faces.map(face => [face.dataset.suit, face.dataset.rank])")
    assert [tuple(card) for card in drawn] == [(card["suit"], card["rank"]) for card in last["cards"]]
    expect(shown.locator(".lt-card.took")).to_have_count(1)

    seated.locator(f"{HAND_CARD} button").first.click()

    expect(shown).to_have_count(0)
    expect(seated.locator(f"{HAND_CARD}.touch")).to_have_count(0)
    assert posts == []

    seated.locator(RIMMED_PILE).click()
    expect(shown).to_have_count(1)
    seated.keyboard.press("Escape")
    expect(shown).to_have_count(0)

    seated.locator(RIMMED_PILE).click()
    expect(shown).to_have_count(1)
    table.play_out(1)
    expect(shown).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_with_liegen_lassen_the_trick_lies_until_the_next_lead_also_after_a_reload_and_no_pile_is_rimmed(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    watcher = open_watcher(open_person, page_errors, table, form_factor, stored={"lastTrick": "stay"})
    table.play_out(CARDS_IN_A_TRICK)

    expect(watcher.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK)
    expect(watcher.locator(RIMMED_PILE)).to_have_count(0)
    expect(watcher.locator(PILE)).to_have_count(0)
    watcher.clock.run_for(FAR_PAST_ANY_SWEEP_MILLISECONDS)
    expect(watcher.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK)

    watcher.reload()
    expect(watcher.locator(".chair")).to_have_count(3)
    expect(watcher.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK)
    expect(watcher.locator(RIMMED_PILE)).to_have_count(0)

    table.play_out(1)

    expect(watcher.locator(FELT_CARD)).to_have_count(1)
    expect_the_piles(watcher, table)
    expect_the_rim_on(watcher, taker_of_the_last_trick(table))
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_with_reduced_motion_the_trick_is_piled_at_once_and_still_sounds(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    watcher = open_watcher(open_person, page_errors, table, form_factor, moving=False)
    table.play_out(CARDS_IN_A_TRICK - 1)
    expect(watcher.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK - 1)
    sounded_before = len(voices_started(watcher))

    table.play_out(1)

    expect(watcher.locator(FELT_CARD)).to_have_count(0)
    expect_the_piles(watcher, table)
    expect_the_rim_on(watcher, taker_of_the_last_trick(table))
    expect(watcher.locator(f".chair.turn[data-seat='{table.turn_seat()}']")).to_have_count(1)
    assert len(voices_started(watcher)) == sounded_before + 2 + VOICES_OF_ONE_SWEEP
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_reload_and_a_window_that_turns_hidden_show_the_trick_piled(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    watcher = open_watcher(open_person, page_errors, table, form_factor)
    table.play_out(CARDS_IN_A_TRICK)
    expect(watcher.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK)

    hide_the_tab(watcher, hidden=True)

    expect(watcher.locator(FELT_CARD)).to_have_count(0)
    expect_the_piles(watcher, table)

    watcher.reload()
    expect(watcher.locator(".chair")).to_have_count(3)
    expect(watcher.locator(FELT_CARD)).to_have_count(0)
    expect_the_piles(watcher, table)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_muted_page_sweeps_without_a_sound(
    table: PlayingTable,
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    watcher = open_watcher(open_person, page_errors, table, form_factor, stored={"muted": True})
    table.play_out(CARDS_IN_A_TRICK)
    expect(watcher.locator(FELT_CARD)).to_have_count(CARDS_IN_A_TRICK)

    rest_and_sweep(watcher)

    expect(watcher.locator(FELT_CARD)).to_have_count(0)
    assert voices_started(watcher) == []
    assert page_errors == []
