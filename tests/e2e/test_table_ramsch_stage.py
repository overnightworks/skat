from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.people import DESKTOP, PHONE, SMALL_PHONE, WIDTHS, McpAgent
from tests.e2e.support.ramsch_stage import AGENT_SEAT, BIDDING, BUBBLE, PLAQUE, TURN_CHAIR, RamschStageTable, deal

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

SKAT_CARDS = ".skat-spot .skat-card"
LAID_CARDS = ".trick .laid"
DECLARER_MARK = ".mark.declarer"
RAMSCH = text(SOURCE_LANGUAGE, "table.ramsch")
PUSH_WORD = text(SOURCE_LANGUAGE, "table.push")
WAITING_FOR_PLAYERS = text(SOURCE_LANGUAGE, "table.waitingForPlayers")
THINKS = text(SOURCE_LANGUAGE, "table.thinks")
CARDS_AFTER_A_TAKE = 12
POSITIONS = ("forehand", "middlehand", "rearhand")


def pushes(count: int) -> str:
    return text(SOURCE_LANGUAGE, "table.pushCount", count=count)


def factor(value: int) -> str:
    return text(SOURCE_LANGUAGE, "table.pushFactor", factor=str(value))


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_everyone_sees_who_acts_and_the_pushes_with_their_factor_and_a_reload_changes_nothing(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, form_factor)
    forehand = table.name_of("forehand")
    on_turn = table.pages[table.seat_of("forehand")]

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(RAMSCH)
        expect(person.locator(PLAQUE)).not_to_contain_text(BIDDING)
        expect(person.locator(SKAT_CARDS)).to_have_count(2)
        expect(person.locator(DECLARER_MARK)).to_have_count(0)
        if person is not on_turn:
            expect(person.locator(PLAQUE)).to_contain_text(text(SOURCE_LANGUAGE, "table.chooses", name=forehand))
    expect(on_turn.locator(PLAQUE)).not_to_contain_text(text(SOURCE_LANGUAGE, "table.chooses", name=forehand))
    table.expect_the_turn_at("forehand")
    table.expect_nothing_to_overflow()

    table.take("forehand")

    for person in table.everyone:
        if person is not on_turn:
            expect(person.locator(PLAQUE)).to_contain_text(text(SOURCE_LANGUAGE, "table.discards", name=forehand))
            expect(table.chair(person, "forehand").locator(".count-tag")).to_contain_text(str(CARDS_AFTER_A_TAKE))
        expect(person.locator(SKAT_CARDS)).to_have_count(0)

    table.put_back_two_cards_that_are_no_jack("forehand")
    table.push("middlehand")

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(pushes(1))
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_text(factor(2))
        expect(table.chair(person, "middlehand").locator(".bubble.word")).to_contain_text(PUSH_WORD)
        expect(person.locator(BUBBLE)).to_have_count(1)
        expect(person.locator(SKAT_CARDS)).to_have_count(2)
    table.expect_the_turn_at("rearhand")
    for person in table.everyone:
        if person is not table.pages[table.seat_of("rearhand")]:
            expect(person.locator(PLAQUE)).to_contain_text(
                text(SOURCE_LANGUAGE, "table.chooses", name=table.name_of("rearhand"))
            )
    table.expect_nothing_to_overflow()
    if form_factor != SMALL_PHONE:
        table.expect_the_plaque_lines_to_read_alike(
            [person for person in table.everyone if person is not table.pages[table.seat_of("rearhand")]]
        )

    table.reload_everyone()

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(pushes(1))
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_text(factor(2))
        expect(table.chair(person, "middlehand").locator(".bubble.word")).to_contain_text(PUSH_WORD)
    table.expect_the_turn_at("rearhand")


def test_a_table_that_does_not_double_counts_the_pushes_without_a_factor(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, PHONE, rule="no-doubling")

    table.push("forehand")
    table.push("middlehand")

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(pushes(2))
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_count(0)
        expect(person.locator(BUBBLE)).to_have_count(2)


@pytest.mark.parametrize("form_factor", [WIDTHS[0], WIDTHS[2]])
def test_the_play_keeps_the_count_and_draws_the_trick_without_a_declarer(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, form_factor)
    table.push("forehand")
    table.push("middlehand")
    table.take("rearhand")
    table.put_back_two_cards_that_are_no_jack("rearhand")

    for person in table.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(pushes(2))
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_text(factor(4))
        expect(person.locator(PLAQUE)).not_to_contain_text(BIDDING)
        expect(person.locator(BUBBLE)).to_have_count(0)
        expect(person.locator(SKAT_CARDS)).to_have_count(0)
    table.expect_the_turn_at("forehand")

    table.lead_a_card("forehand")

    for person in table.everyone:
        expect(person.locator(LAID_CARDS)).to_have_count(1)
        expect(person.locator(DECLARER_MARK)).to_have_count(0)
        expect(person.locator(PLAQUE)).to_contain_text(pushes(2))
    table.expect_the_turn_at("middlehand")
    table.expect_nothing_to_overflow()

    table.reload_everyone()

    for person in table.everyone:
        expect(person.locator(PLAQUE).locator(".pushes b")).to_have_text(factor(4))
        expect(person.locator(LAID_CARDS)).to_have_count(1)
    table.expect_the_turn_at("middlehand")


def test_an_open_chair_makes_the_plaque_wait_and_leaves_nobody_on_turn(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = deal(open_person, e2e_server, member_of, page_errors, PHONE)
    left = table.seat_of("rearhand")
    still_seated = [person for seat, person in table.pages.items() if seat != left]

    table.stand_up("rearhand")

    for person in (*still_seated, table.watcher):
        expect(person.locator(PLAQUE)).to_contain_text(WAITING_FOR_PLAYERS)
        expect(person.locator(PLAQUE)).not_to_contain_text(
            text(SOURCE_LANGUAGE, "table.chooses", name=table.name_of("forehand"))
        )
        expect(person.locator(TURN_CHAIR)).to_have_count(0)
    table.expect_nothing_to_overflow([*still_seated, table.watcher])


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_an_agent_on_turn_wears_denkt_over_the_turn_mark_for_everyone(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschStageTable(
        open_person,
        e2e_server,
        member_of,
        page_errors,
        form_factor,
        rule="jacks-stay",
        agent=McpAgent(e2e_server, "agent-subject-ramsch-thinker"),
    )
    agent_position = next(position for position in POSITIONS if table.seat_of(position) == AGENT_SEAT)
    for position in POSITIONS[: POSITIONS.index(agent_position)]:
        table.push(position)

    table.expect_the_turn_at(agent_position)
    for person in table.everyone:
        chair = table.chair(person, agent_position)
        thinks = chair.locator(".mark.think")
        expect(person.locator(".mark.think")).to_have_count(1)
        expect(thinks).to_be_visible()
        think_box = thinks.bounding_box()
        turn_box = chair.locator(".mark.turn").bounding_box()
        chair_box = chair.bounding_box()
        assert think_box is not None
        assert turn_box is not None
        assert chair_box is not None
        assert chair_box["x"] <= think_box["x"]
        assert think_box["x"] + think_box["width"] <= chair_box["x"] + chair_box["width"]
        assert think_box["x"] <= turn_box["x"]
        assert think_box["y"] <= turn_box["y"]
        assert turn_box["x"] + turn_box["width"] <= think_box["x"] + think_box["width"]
        assert turn_box["y"] + turn_box["height"] <= think_box["y"] + think_box["height"]
        assert thinks.evaluate(
            "think => { const box = think.closest('.chair').querySelector('.mark.turn').getBoundingClientRect(); "
            "const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2); "
            "return top?.closest('.mark') === think }"
        )
        if form_factor is DESKTOP:
            expect(thinks).to_contain_text(THINKS)
            assert thinks.evaluate("mark => getComputedStyle(mark).fontSize") != "0px"
    table.expect_nothing_to_overflow()

    table.reload_everyone()

    for person in table.everyone:
        expect(table.chair(person, agent_position).locator(".mark.think")).to_be_visible()
