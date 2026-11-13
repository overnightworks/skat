from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.web.seating import TABLE_STAND_SUFFIX
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.name_lists import listed
from tests.e2e.support.people import PHONE, WIDTHS
from tests.e2e.support.ramsch import RamschTable
from tests.e2e.support.result_card import CARD, LOST, MINUS, WON, expect_the_page_around_the_card, signed

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

WEITER = text(SOURCE_LANGUAGE, "table.weiter")
SEAT_FREE = text(SOURCE_LANGUAGE, "result.seatFree")


def with_minus(number: int) -> str:
    return f"{MINUS}{-number}" if number < 0 else str(number)


def expected_head(table: RamschTable, result: dict[str, Any], seat: int | None) -> str:
    sweeper = result["durchmarsch_seat"]
    if sweeper is not None:
        return WON if seat == sweeper else text(SOURCE_LANGUAGE, "result.durchmarsch")
    losers = [each["seat"] for each in result["seats"] if each["score"] < 0]
    if seat in losers:
        return LOST
    names = listed([table.names[loser] for loser in losers])
    key = "result.loses" if len(losers) == 1 else "result.losesTogether"
    return text(SOURCE_LANGUAGE, key, **{"name" if len(losers) == 1 else "names": names})


def expected_eye_counts(table: RamschTable, result: dict[str, Any], seat: int | None) -> list[str]:
    """The eyes row names the viewer's own seat first as "Du" and every other seat by its name."""
    eyes = {each["seat"]: each["points"] for each in result["seats"]}
    order = sorted(eyes, key=lambda each: (each != seat, each))
    you = text(SOURCE_LANGUAGE, "result.sideYou")
    return [f"{you if each == seat else table.names[each]} {eyes[each]}" for each in order]


def expect_the_card(table: RamschTable) -> None:
    """Every viewer, a watcher included, reads the head, the eyes and the value of the answer, from their own side."""
    result = table.result()
    leader = next(
        each
        for each in result["seats"]
        if each["seat"] == result["durchmarsch_seat"] or (result["durchmarsch_seat"] is None and each["score"] < 0)
    )
    seats = {page: seat for seat, page in table.pages.items()}
    for person in table.everyone:
        card: Locator = person.locator(CARD)
        expect(card).to_have_count(1)
        expect(card.locator("h3")).to_have_text(expected_head(table, result, seats.get(person)))
        expect(card.locator(".sub")).to_have_text(text(SOURCE_LANGUAGE, "game.ramsch"))
        expect(card.locator(".eq")).to_have_text(text(SOURCE_LANGUAGE, "result.eyes", points=str(leader["points"])))
        expect(card.locator(".value")).to_have_text(signed(leader["score"]))
        expect(card.locator(".list span")).to_have_text(expected_eye_counts(table, result, seats.get(person)))
        expect(card.locator(".reck")).to_have_count(3)
        for each in result["seats"]:
            expect(card.locator(f".reck[data-seat='{each['seat']}'] .dl")).to_have_text(
                signed(each["score"]) if each["score"] > 0 else with_minus(each["score"])
            )


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_everyone_reads_the_ramsch_result_card_and_weiter_works(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, form_factor)
    table.pass_all()
    table.play_out()

    expect_the_card(table)
    expect_the_page_around_the_card(table.everyone)
    table.pages[1].locator(".actions").get_by_role("button", name=WEITER).click()
    for person in table.everyone:
        expect(person.locator(".chair[data-seat='1'] .mark.ready")).to_have_count(1)
    assert page_errors == []


def test_a_seat_that_stood_up_after_the_hand_reads_as_free_on_the_card(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> None:
    table = RamschTable(open_person, e2e_server, member_of, page_errors, PHONE)
    table.pass_all()
    table.play_out()
    leaver_seat = 2

    table.sessions[leaver_seat].post(
        f"{table.api_path}{TABLE_STAND_SUFFIX}", {"command_id": f"ramsch-stand-{uuid4().hex}"}
    )

    for person in table.everyone:
        expect(person.locator(CARD).locator(f".reck[data-seat='{leaver_seat}'] .nm")).to_have_text(SEAT_FREE)
    assert page_errors == []
