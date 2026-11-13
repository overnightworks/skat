import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.web.rule_sets import RULE_SETS_PATH
from skat.web.tables import TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.browser import NEW_TABLE_BUTTON, record_page_errors
from tests.e2e.support.people import DESKTOP, PHONE, SMALL_PHONE, WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.tables import OPEN_TABLE, TABLE_URL, save_rule_set, table_id_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

OFFICIAL = text(SOURCE_LANGUAGE, "start.setOfficial")
RULES = text(SOURCE_LANGUAGE, "start.ruleSets")
KONTRA = text(SOURCE_LANGUAGE, "start.ruleKontra")
RAMSCH = text(SOURCE_LANGUAGE, "start.ruleRamsch")
PUSHING = text(SOURCE_LANGUAGE, "start.rulePushing")
BOCK = text(SOURCE_LANGUAGE, "start.ruleBock")
CANCEL = text(SOURCE_LANGUAGE, "start.cancelNewTable")
SAVE = text(SOURCE_LANGUAGE, "start.saveRules")
SAVE_NAME = text(SOURCE_LANGUAGE, "start.saveName")

HOUSE_SET = "Hausregeln"
HOUSE_OPTIONS = {
    "show_running_points": True,
    "kontra": {"sayer": "any-opponent", "reach": "kontra-re-standings", "deadline": "own-card"},
    "ramsch": {
        "occasion": "passed-in",
        "scoring": "skat-to-loser",
        "jungfrau": "off",
        "durchmarsch": "wins-120-flat",
        "pushing": {"rule": "no-doubling", "grand_hand": "allowed"},
    },
    "bock": {"triggers": ["re", "schneider"], "overlap": "multiply"},
}
EVENING_SET = "Abend"
EVENING_OPTIONS = {"show_running_points": True}


def sheet_of(person: Page, server: RunningServer) -> None:
    person.goto(f"{server.base_url}/")
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()


def set_pill(person: Page, name: str) -> Locator:
    return person.get_by_role("radiogroup", name=RULES).get_by_role("radio", name=name, exact=True)


def switch(person: Page, name: str) -> Locator:
    return person.get_by_role("switch", name=name, exact=True)


def pill(person: Page, question: str, answer: str) -> Locator:
    return person.get_by_role("radiogroup", name=question).get_by_role("radio", name=answer, exact=True)


def save_row(person: Page) -> Locator:
    return person.get_by_role("group", name=SAVE)


def save_name(person: Page) -> Locator:
    return save_row(person).get_by_role("textbox", name=SAVE_NAME)


def box_top(target: Locator) -> float:
    box = target.bounding_box()
    assert box is not None
    return box["y"]


def word(key: str) -> str:
    return text(SOURCE_LANGUAGE, key)


def opened_options(person: Page, server: RunningServer) -> dict[str, Any]:
    expect(person).to_have_url(TABLE_URL)
    answer = person.request.get(f"{server.base_url}{TABLES_PATH}/{table_id_of(urlsplit(person.url).path)}")
    return answer.json()["options"]


@pytest.fixture
def person_with_sets(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., Page]:
    """A signed-in person who saved the house set and the evening set through the API."""

    def open_page(form_factor: dict[str, Any], *, sets: bool = True, console: bool = True) -> Page:
        # Every call is a new account: the server and its database live for the whole session, and a set saved by
        # one test must not be offered to the next.
        person = record_page_errors(open_person(**form_factor), page_errors, console=console)
        if sets:
            session = RawSession(e2e_server, member_of(person))
            save_rule_set(session, HOUSE_SET, HOUSE_OPTIONS)
            save_rule_set(session, EVENING_SET, EVENING_OPTIONS)
        return person

    return open_page


def saved_options(server: RunningServer, member: SeededMember, name: str) -> dict[str, Any]:
    sets = json.loads(RawSession(server, member).get(RULE_SETS_PATH))["sets"]
    return next(each["options"] for each in sets if each["name"] == name)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_person_sees_the_official_rules_picked_and_their_own_sets_and_nobody_else_sees_them(
    person_with_sets: Callable[..., Page],
    e2e_server: RunningServer,
    form_factor: dict[str, Any],
) -> None:
    person = person_with_sets(form_factor)
    other = person_with_sets(form_factor, sets=False)

    sheet_of(person, e2e_server)
    sheet_of(other, e2e_server)

    expect(person.get_by_role("radiogroup", name=RULES).get_by_role("radio")).to_have_count(3)
    expect(set_pill(person, OFFICIAL)).to_be_checked()
    expect(set_pill(person, EVENING_SET)).not_to_be_checked()
    expect(person.get_by_role("switch")).to_have_count(4)
    expect(set_pill(other, OFFICIAL)).to_be_checked()
    expect(other.get_by_role("radiogroup", name=RULES).get_by_role("radio")).to_have_count(1)


def test_a_set_saved_while_the_page_is_open_is_offered_when_the_sheet_opens_again(
    person_with_sets: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
) -> None:
    person = person_with_sets(DESKTOP, sets=False)
    sheet_of(person, e2e_server)
    expect(person.get_by_role("radiogroup", name=RULES).get_by_role("radio")).to_have_count(1)
    person.get_by_role("button", name=CANCEL).click()

    save_rule_set(RawSession(e2e_server, member_of(person)), HOUSE_SET, HOUSE_OPTIONS)
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()

    expect(set_pill(person, HOUSE_SET)).to_be_visible()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_picking_a_set_unfolds_its_rules_and_opens_a_table_with_its_options_in_one_request(
    person_with_sets: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    form_factor: dict[str, Any],
) -> None:
    person = person_with_sets(form_factor)
    requests: list[dict[str, Any]] = []
    person.on(
        "request",
        lambda request: requests.append(json.loads(request.post_data or "{}")) if request.method == "POST" else None,
    )
    sheet_of(person, e2e_server)

    set_pill(person, HOUSE_SET).check()

    for rule in (KONTRA, RAMSCH, PUSHING, BOCK):
        expect(switch(person, rule)).to_have_attribute("aria-checked", "true")
    expect(pill(person, word("start.askKontraSayer"), word("start.pillAnyOpponent"))).to_be_checked()
    expect(pill(person, word("start.askGrandHand"), word("start.pillGrandHandAllowed"))).to_be_checked()
    expect(switch(person, word("start.flagSchneider"))).to_have_attribute("aria-checked", "true")
    expect(switch(person, word("start.flagSixtySixty"))).to_have_attribute("aria-checked", "false")
    person.get_by_role("button", name=OPEN_TABLE).dblclick()

    assert opened_options(person, e2e_server) == saved_options(e2e_server, member_of(person), HOUSE_SET)
    assert len(requests) == 1


def test_a_rule_switched_on_over_the_official_rules_starts_with_the_house_values_and_each_answer_can_change(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = person_with_sets(DESKTOP, sets=False)
    sheet_of(person, e2e_server)

    switch(person, KONTRA).click()

    expect(pill(person, word("start.askKontraSayer"), word("start.pillBiddersOnly"))).to_be_checked()
    expect(pill(person, word("start.askKontraReach"), word("start.pillUpToHirsch"))).to_be_checked()
    pill(person, word("start.askKontraSayer"), word("start.pillAnyOpponent")).check()
    person.get_by_role("button", name=OPEN_TABLE).click()
    assert opened_options(person, e2e_server)["kontra"]["sayer"] == "any-opponent"


def test_bock_switched_on_shows_the_house_triggers_and_a_trigger_turned_on_opens_the_table_with_it(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = person_with_sets(DESKTOP, sets=False)
    sheet_of(person, e2e_server)

    switch(person, BOCK).click()

    for key, on in (("flagSixtySixty", True), ("flagRe", True), ("flagPassedIn", False), ("flagSchneider", False)):
        expect(switch(person, word(f"start.{key}"))).to_have_attribute("aria-checked", str(on).lower())
    triggers_top = box_top(switch(person, word("start.flagRe")))
    overlap_top = box_top(person.get_by_role("radiogroup", name=word("start.askBockOverlap")))
    assert triggers_top < overlap_top
    switch(person, word("start.flagSchneider")).click()
    person.get_by_role("button", name=OPEN_TABLE).click()
    assert "schneider" in opened_options(person, e2e_server)["bock"]["triggers"]


def test_ramsch_unfolds_into_schieberamsch_that_goes_with_it(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = person_with_sets(DESKTOP, sets=False)
    sheet_of(person, e2e_server)
    expect(switch(person, PUSHING)).to_have_count(0)

    switch(person, RAMSCH).click()
    expect(switch(person, PUSHING)).to_have_attribute("aria-checked", "false")
    switch(person, PUSHING).click()
    expect(pill(person, word("start.askPushingRule"), word("start.pillPushingJacksStay"))).to_be_checked()
    pill(person, word("start.askGrandHand"), word("start.pillGrandHandAllowed")).check()
    switch(person, RAMSCH).click()

    expect(switch(person, PUSHING)).to_have_count(0)
    person.get_by_role("button", name=OPEN_TABLE).click()
    assert opened_options(person, e2e_server)["ramsch"] is None


def test_a_rule_switched_off_after_a_lost_answer_opens_a_table_without_it_under_another_command(
    person_with_sets: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{TABLES_PATH}")
    person = person_with_sets(DESKTOP, console=False)
    attempts: list[dict[str, Any]] = []

    def lose_the_first_answer(route: Any) -> None:
        attempts.append(json.loads(route.request.post_data or "{}"))
        if len(attempts) > 1:
            route.continue_()
        else:
            route.fetch()
            route.abort()

    person.route(f"**{TABLES_PATH}", lose_the_first_answer)
    sheet_of(person, e2e_server)
    set_pill(person, HOUSE_SET).check()
    person.get_by_role("button", name=OPEN_TABLE).click()
    expect(person.get_by_role("alert")).to_be_visible()

    switch(person, KONTRA).click()
    person.get_by_role("button", name=OPEN_TABLE).click()

    options = opened_options(person, e2e_server)
    assert options["kontra"] is None
    assert options["ramsch"] is not None
    assert options["bock"] is not None
    assert attempts[1]["command_id"] != attempts[0]["command_id"]
    assert "kontra" not in attempts[1]["options"]


def test_a_sheet_reopened_after_cancelling_has_the_official_rules_picked_again(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = person_with_sets(DESKTOP)
    sheet_of(person, e2e_server)
    set_pill(person, HOUSE_SET).check()
    person.get_by_role("button", name=CANCEL).click()

    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()

    expect(set_pill(person, OFFICIAL)).to_be_checked()
    expect(switch(person, KONTRA)).to_have_attribute("aria-checked", "false")


def test_escape_closes_the_sheet_unless_the_table_is_being_opened(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = person_with_sets(DESKTOP)
    held: list[Any] = []
    person.route(f"**{TABLES_PATH}", lambda route: held.append(route))
    sheet_of(person, e2e_server)
    sheet = person.get_by_role("dialog", name=word("start.newTable"))

    person.keyboard.press("Escape")
    expect(sheet).to_be_hidden()

    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    person.get_by_role("button", name=OPEN_TABLE).click()
    expect(person.get_by_role("button", name=OPEN_TABLE)).to_be_disabled()
    person.keyboard.press("Escape")
    expect(sheet).to_be_visible()

    held[0].continue_()
    expect(person).to_have_url(TABLE_URL)


def test_the_official_rules_stay_offered_with_a_notice_when_the_own_sets_cannot_be_read(
    person_with_sets: Callable[..., Page],
    e2e_server: RunningServer,
    expected_request_failures: list[str],
) -> None:
    expected_request_failures.append(f"{e2e_server.base_url}{RULE_SETS_PATH}")
    person = person_with_sets(DESKTOP, console=False)
    person.route(f"**{RULE_SETS_PATH}", lambda route: route.abort())

    sheet_of(person, e2e_server)

    expect(person.get_by_role("status")).to_have_text(word("start.setsUnreadable"))
    expect(set_pill(person, OFFICIAL)).to_be_checked()
    person.get_by_role("button", name=OPEN_TABLE).click()
    expect(person).to_have_url(TABLE_URL)


@pytest.mark.parametrize("form_factor", [pytest.param(SMALL_PHONE, id="360"), pytest.param(PHONE, id="390")])
def test_only_the_rules_scroll_while_the_title_the_sets_and_the_buttons_stay_in_reach(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    person = person_with_sets(form_factor)
    sheet_of(person, e2e_server)

    set_pill(person, HOUSE_SET).check()

    for visible in (
        person.get_by_role("heading", name=NEW_TABLE_BUTTON),
        set_pill(person, OFFICIAL),
        person.get_by_role("button", name=OPEN_TABLE),
        person.get_by_role("button", name=CANCEL),
    ):
        expect(visible).to_be_in_viewport()
    switch(person, word("start.flagSchneider")).scroll_into_view_if_needed()
    expect(switch(person, word("start.flagSchneider"))).to_be_in_viewport()
    expect(person.get_by_role("button", name=OPEN_TABLE)).to_be_in_viewport()


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_save_row_is_offered_with_a_suggested_name_once_the_sheet_differs_from_the_picked_set(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer, form_factor: dict[str, Any]
) -> None:
    person = person_with_sets(form_factor)
    sheet_of(person, e2e_server)
    expect(save_row(person)).to_have_count(0)

    switch(person, KONTRA).click()
    switch(person, RAMSCH).click()

    expect(save_row(person)).to_be_visible()
    expect(save_name(person)).to_have_value(f"{OFFICIAL}, mit Kontra und Ramsch")
    # The whole name shows: the field grows to its text instead of cutting it off.
    assert save_name(person).evaluate(
        "field => field.scrollWidth <= field.clientWidth && field.scrollHeight <= field.clientHeight"
    )
    expect(person.get_by_role("button", name=OPEN_TABLE)).to_be_in_viewport()
    expect(save_row(person)).to_be_in_viewport()
    switch(person, KONTRA).click()
    expect(save_name(person)).to_have_value(f"{OFFICIAL}, mit Ramsch")
    switch(person, RAMSCH).click()
    expect(save_row(person)).to_have_count(0)


def test_switching_rules_off_over_a_set_suggests_the_set_adjusted_and_a_pick_takes_the_offer_away(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = person_with_sets(DESKTOP)
    sheet_of(person, e2e_server)
    set_pill(person, HOUSE_SET).check()

    switch(person, KONTRA).click()

    expect(save_name(person)).to_have_value(f"{HOUSE_SET}, angepasst")
    set_pill(person, EVENING_SET).check()
    expect(save_row(person)).to_have_count(0)


def test_a_tap_saves_the_sheet_under_the_edited_name_as_the_picked_set_that_only_its_owner_sees(
    person_with_sets: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
) -> None:
    person = person_with_sets(DESKTOP)
    other = person_with_sets(DESKTOP, sets=False)
    sheet_of(person, e2e_server)
    switch(person, KONTRA).click()
    save_name(person).fill("Sonntag")

    save_row(person).get_by_role("button", name=SAVE).click()

    expect(set_pill(person, "Sonntag")).to_be_checked()
    expect(save_row(person)).to_have_count(0)
    expect(switch(person, KONTRA)).to_have_attribute("aria-checked", "true")
    assert saved_options(e2e_server, member_of(person), "Sonntag")["kontra"] is not None
    person.get_by_role("button", name=CANCEL).click()
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    expect(set_pill(person, "Sonntag")).to_be_visible()
    sheet_of(other, e2e_server)
    expect(other.get_by_role("radiogroup", name=RULES).get_by_role("radio")).to_have_count(1)


def test_a_name_taken_by_other_rules_shows_one_line_and_saves_nothing(
    person_with_sets: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
) -> None:
    person = person_with_sets(DESKTOP, console=False)
    sheet_of(person, e2e_server)
    switch(person, KONTRA).click()
    save_name(person).fill(EVENING_SET)

    save_row(person).get_by_role("button", name=SAVE).click()

    expect(person.get_by_role("alert")).to_have_text(word("start.saveNameTaken"))
    expect(set_pill(person, OFFICIAL)).to_be_checked()
    expect(person.get_by_role("radiogroup", name=RULES).get_by_role("radio")).to_have_count(3)
    held = json.loads(RawSession(e2e_server, member_of(person)).get(RULE_SETS_PATH))["sets"]
    assert sorted(each["name"] for each in held) == sorted([HOUSE_SET, EVENING_SET])
    assert saved_options(e2e_server, member_of(person), EVENING_SET)["kontra"] is None


def test_a_save_the_server_refuses_shows_one_line_and_keeps_the_sheet_as_it_was(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = person_with_sets(DESKTOP, console=False)

    def refuse_the_save(route: Any) -> None:
        if route.request.method == "POST":
            route.fulfill(status=422, content_type="application/json", body="{}")
        else:
            route.continue_()

    person.route(f"**{RULE_SETS_PATH}", refuse_the_save)
    sheet_of(person, e2e_server)
    switch(person, KONTRA).click()
    save_name(person).fill("Sonntag")

    save_row(person).get_by_role("button", name=SAVE).click()

    expect(person.get_by_role("alert")).to_have_text(word("start.saveFailed"))
    expect(save_name(person)).to_have_value("Sonntag")
    expect(person.get_by_role("radiogroup", name=RULES).get_by_role("radio")).to_have_count(3)


def test_a_save_answered_after_the_sheet_was_closed_and_opened_again_changes_nothing_on_the_new_sheet(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = person_with_sets(DESKTOP)
    held: list[Any] = []

    def hold_the_save(route: Any) -> None:
        if route.request.method == "POST":
            held.append(route)
        else:
            route.continue_()

    person.route(f"**{RULE_SETS_PATH}", hold_the_save)
    sheet_of(person, e2e_server)
    switch(person, KONTRA).click()
    save_name(person).fill("Sonntag")
    save_row(person).get_by_role("button", name=SAVE).click()
    expect(save_name(person)).to_be_disabled()
    person.get_by_role("button", name=CANCEL).click()
    person.get_by_role("button", name=NEW_TABLE_BUTTON).click()
    expect(set_pill(person, OFFICIAL)).to_be_checked()

    with person.expect_response(lambda answer: answer.request.method == "POST" and answer.url.endswith(RULE_SETS_PATH)):
        held[0].continue_()

    expect(set_pill(person, OFFICIAL)).to_be_checked()
    expect(person.get_by_role("radiogroup", name=RULES).get_by_role("radio")).to_have_count(3)
    expect(switch(person, KONTRA)).to_have_attribute("aria-checked", "false")


def test_a_save_answered_after_the_list_already_holds_the_set_offers_the_set_once(
    person_with_sets: Callable[..., Page], e2e_server: RunningServer
) -> None:
    person = person_with_sets(DESKTOP)
    reads: list[Any] = []
    saves: list[tuple[Any, Any]] = []

    def hold_both_answers(route: Any) -> None:
        if route.request.method == "GET":
            reads.append(route)
            return
        saves.append((route, route.fetch()))
        reads[0].continue_()

    person.route(f"**{RULE_SETS_PATH}", hold_both_answers)
    sheet_of(person, e2e_server)
    switch(person, KONTRA).click()
    save_name(person).fill("Sonntag")
    save_row(person).get_by_role("button", name=SAVE).click()
    expect(set_pill(person, "Sonntag")).to_be_visible()

    held_save, saved_answer = saves[0]
    held_save.fulfill(response=saved_answer)

    expect(set_pill(person, "Sonntag")).to_be_checked()
    expect(person.get_by_role("radiogroup", name=RULES).get_by_role("radio")).to_have_count(4)
