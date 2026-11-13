from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.engine.tricks import CARDS_IN_A_GAME
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.result_card import CARD, MINUS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

# The count starts after this delay and runs this long, as the blessed scene draws it.
COUNT_DELAY_MILLISECONDS = 300
COUNT_MILLISECONDS = 1100

ANIMATION_NAME = "(dl) => getComputedStyle(dl).animationName"
COUNTER_CONTENT = "(dl) => getComputedStyle(dl, '::after').content"
# The registered counter at one moment of the paused count, read without waiting for it.
COUNTER_AT = """
    (dl, milliseconds) => {
        const [count] = dl.getAnimations().filter((animation) => animation.animationName === "count");
        count.pause();
        count.currentTime = milliseconds;
        return Number(getComputedStyle(dl).getPropertyValue("--n"));
    }
"""
START_OF_THE_COUNT = """
    async (dl) => {
        const [count] = dl.getAnimations().filter((animation) => animation.animationName === "count");
        await count.ready;
        return count.startTime;
    }
"""


def deal_a_finished_hand(
    open_person: Callable[..., Page],
    server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> PlayingTable:
    table = deal_playing_table(open_person, server, member_of, page_errors, form_factor)
    table.play_out(CARDS_IN_A_GAME)
    return table


def shown(gain: int) -> str:
    return f"+{gain}" if gain > 0 else str(gain).replace("-", MINUS)


def gain_cell(person: Page, seat: int) -> Locator:
    return person.locator(f"{CARD} .reck[data-seat='{seat}'] .dl")


def gains_of(table: PlayingTable) -> dict[int, int]:
    return {one["seat"]: one["gain"] for one in table.result()["gains"]}


def expect_every_gain_to_stand(table: PlayingTable) -> None:
    for person in table.everyone:
        for seat in table.names:
            cell = gain_cell(person, seat)
            expect(cell).to_be_visible()
            expect(cell).not_to_have_class("count")
            assert cell.evaluate(ANIMATION_NAME) == "none"
            assert cell.evaluate(COUNTER_CONTENT) == "none"


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_won_gain_counts_up_through_its_frames_and_the_final_text_stands_from_the_first_frame(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_finished_hand(
        open_person, e2e_server, member_of, page_errors, {**form_factor, "reduced_motion": "no-preference"}
    )
    gains = gains_of(table)

    for person in table.everyone:
        for seat, gain in gains.items():
            cell = gain_cell(person, seat)
            expect(cell).to_be_visible()
            if gain <= 0:
                expect(cell).not_to_have_class("count")
                assert cell.evaluate(ANIMATION_NAME) == "none"
                continue
            expect(cell).to_have_text(shown(gain))
            expect(cell).to_have_class("dl count")
            assert cell.evaluate(ANIMATION_NAME) == "count"
            assert cell.evaluate(COUNTER_CONTENT) != "none"
            assert cell.evaluate(COUNTER_AT, 0) == 0
            assert cell.evaluate(COUNTER_AT, COUNT_DELAY_MILLISECONDS) == 0
            midway = cell.evaluate(COUNTER_AT, COUNT_DELAY_MILLISECONDS + COUNT_MILLISECONDS / 2)
            assert 0 < midway < gain
            assert cell.evaluate(COUNTER_AT, COUNT_DELAY_MILLISECONDS + COUNT_MILLISECONDS) == gain
            expect(cell).to_have_text(shown(gain))
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_card_update_while_the_count_runs_neither_restarts_it_nor_moves_the_coaster(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_finished_hand(
        open_person, e2e_server, member_of, page_errors, {**form_factor, "reduced_motion": "no-preference"}
    )
    won_seat = next(seat for seat, gain in gains_of(table).items() if gain > 0)
    cell = gain_cell(table.watcher, won_seat)
    expect(cell).to_have_class("dl count")
    started = cell.evaluate(START_OF_THE_COUNT)
    width = (cell.bounding_box() or {})["width"]

    table.ready_through_the_api(won_seat)

    expect(table.watcher.locator(f"{CARD} .reck[data-seat='{won_seat}']")).to_be_visible()
    expect(table.watcher.locator(f".chair[data-seat='{won_seat}'] .mark.ready")).to_have_count(1)
    assert cell.evaluate(START_OF_THE_COUNT) == started
    assert (cell.bounding_box() or {})["width"] == width
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_reload_shows_the_final_numbers_without_a_count(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_finished_hand(
        open_person, e2e_server, member_of, page_errors, {**form_factor, "reduced_motion": "no-preference"}
    )
    gains = gains_of(table)
    for person in table.everyone:
        person.reload()
        expect(person.locator(".chair")).to_have_count(3)

    expect_every_gain_to_stand(table)
    for person in table.everyone:
        for seat, gain in gains.items():
            expect(gain_cell(person, seat)).to_have_text(shown(gain))
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_with_reduced_motion_every_number_stands_at_once(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_finished_hand(
        open_person, e2e_server, member_of, page_errors, {**form_factor, "reduced_motion": "reduce"}
    )

    expect_every_gain_to_stand(table)
    assert page_errors == []
