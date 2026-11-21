import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.support.browser import hide_the_tab, record_page_errors
from tests.e2e.support.hands import INSIDE_THE_VISIBLE_STRIP, deal_playing_table
from tests.e2e.support.motion import (
    FADES_IN,
    FLIES_FACE_UP,
    LIES_AT_ONCE,
    TURNS_OVER,
    arrival_of,
    lies_on_the_felt,
    motion_played,
    wait_for_the_motion_to_end,
    watch_the_motion,
)
from tests.e2e.support.people import PHONE, WIDTHS

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

FELT_FACE = ".trick .laid .face"
MOTION = "no-preference"
# The key the player's choices are kept under in the browser.
SETTINGS_KEY = "skat.settings"
# Takt moves a card, its shade, its back and its player's name, and writes nothing but these two properties.
PIECES_OF_A_LANDING = {"face", "shade", "rear", "tag"}
COMPOSED_PROPERTIES = {"transform", "opacity"}
CARDS_IN_A_TRICK = 3
# A lie is told from none, and two lies from each other, beyond a hundredth of a card's width or of a degree.
LIE_SEEN = 0.01


@pytest.fixture
def deal_a_playing_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    # its own settings: this file's constants differ from the other file's, whose closure reads the same
    def deal(form_factor: dict[str, Any]) -> PlayingTable:
        return deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, game="kreuz")

    return deal


def open_watcher_with_motion(
    open_person: Callable[..., Page],
    page_errors: list[str],
    table: PlayingTable,
    form_factor: dict[str, Any],
    *,
    device_motion: str = MOTION,
    stored: dict[str, Any] | None = None,
) -> Page:
    watcher = record_page_errors(open_person(reduced_motion=device_motion, **form_factor), page_errors)
    watch_the_motion(watcher)
    if stored is not None:
        watcher.add_init_script(f"localStorage.setItem({SETTINGS_KEY!r}, {json.dumps(json.dumps(stored))})")
    watcher.goto(table.watcher.url)
    expect(watcher.locator(".chair")).to_have_count(3)
    return watcher


def lies_of(page: Page, cards: int) -> dict[str, dict[str, float]]:
    """How the cards on `page`'s felt rest once all `cards` lie still."""
    expect(page.locator(FELT_FACE)).to_have_count(cards)
    wait_for_the_motion_to_end(page)
    return lies_on_the_felt(page)


def expect_the_same_lies(lies: dict[str, dict[str, float]], others: dict[str, dict[str, float]]) -> None:
    assert lies.keys() == others.keys()
    for card, lie in lies.items():
        assert lie == pytest.approx(others[card], abs=LIE_SEEN), card


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_card_played_while_the_page_watches_lands_on_the_felt(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_playing_table(form_factor)
    watcher = open_watcher_with_motion(open_person, page_errors, table, form_factor)
    watch_the_motion(table.watcher)
    leader = table.turn_seat()

    table.play_out(1)

    expect(watcher.locator(FELT_FACE)).to_have_count(1)
    played = motion_played(watcher)
    assert {piece["piece"] for piece in played} == PIECES_OF_A_LANDING
    assert len(played) == len(PIECES_OF_A_LANDING)
    assert {piece["seat"] for piece in played} == {leader}
    assert len({piece["milliseconds"] for piece in played}) == 1
    assert {written for piece in played for frame in piece["frames"] for written in frame} <= COMPOSED_PROPERTIES
    flight = next(piece["frames"] for piece in played if piece["piece"] == "face")
    assert flight[0]["transform"] != flight[-1]["transform"]
    # The other watcher's device asks for reduced motion: its card lies at once, where the thrown one comes to rest.
    expect(table.watcher.locator(FELT_FACE)).to_have_count(1)
    assert motion_played(table.watcher) == []
    expect_the_same_lies(lies_of(watcher, 1), lies_on_the_felt(table.watcher))
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_cards_a_page_did_not_see_played_lie_at_once_and_the_next_card_lands(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_playing_table(form_factor)
    table.play_out(1)
    joined = open_watcher_with_motion(open_person, page_errors, table, form_factor)
    expect(joined.locator(FELT_FACE)).to_have_count(1)
    assert motion_played(joined) == []

    joined.reload()
    expect(joined.locator(".chair")).to_have_count(3)
    expect(joined.locator(FELT_FACE)).to_have_count(1)
    assert motion_played(joined) == []

    second = table.turn_seat()
    table.play_out(1)

    expect(joined.locator(FELT_FACE)).to_have_count(2)
    assert {piece["seat"] for piece in motion_played(joined)} == {second}
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
@pytest.mark.parametrize(
    ("device_motion", "stored", "arrival"),
    [
        (MOTION, {"motionSet": "dezent"}, FADES_IN),
        (MOTION, {"motionSet": "verspielt"}, TURNS_OVER),
        ("reduce", {"motionSet": "dezent"}, LIES_AT_ONCE),
        ("reduce", {"motionSet": "dezent", "replayMotion": True}, FADES_IN),
        ("reduce", {"replayMotion": True}, TURNS_OVER),
        (MOTION, {"replayMotion": False}, TURNS_OVER),
    ],
    ids=[
        "dezent",
        "verspielt",
        "reduced",
        "reduced-but-overridden-dezent",
        "reduced-but-overridden",
        "moving-no-override",
    ],
)
def test_a_card_lands_in_the_picked_set_and_the_device_asking_for_reduced_motion_stills_it_unless_the_player_overrides(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
    device_motion: str,
    stored: dict[str, Any],
    arrival: str,
) -> None:
    table = deal_a_playing_table(form_factor)
    watcher = open_watcher_with_motion(
        open_person, page_errors, table, form_factor, device_motion=device_motion, stored=stored
    )

    table.play_out(1)

    expect(watcher.locator(FELT_FACE)).to_have_count(1)
    # Out of a fan, which hides its faces, a card of the playful set turns over and a card of the quiet set fades in.
    assert arrival_of(motion_played(watcher)) == arrival
    assert page_errors == []


def test_a_card_played_while_the_window_is_hidden_lies_at_once(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
) -> None:
    table = deal_a_playing_table(PHONE)
    watcher = open_watcher_with_motion(open_person, page_errors, table, PHONE)
    hide_the_tab(watcher, hidden=True)

    table.play_out(1)

    expect(watcher.locator(FELT_FACE)).to_have_count(1)
    assert arrival_of(motion_played(watcher)) == LIES_AT_ONCE
    assert page_errors == []


def test_the_viewers_own_card_flies_face_up_from_the_hand_that_let_it_go(
    deal_a_playing_table: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_playing_table(PHONE)
    own = table.pages[table.turn_seat()]
    own.emulate_media(reduced_motion=MOTION)
    own.reload()
    expect(own.locator(".chair")).to_have_count(3)
    watch_the_motion(own)

    own.locator(".own-hand .card.ok button").first.tap(position=INSIDE_THE_VISIBLE_STRIP)
    own.locator(".own-hand .card.touch button").tap(position=INSIDE_THE_VISIBLE_STRIP)

    expect(own.locator(FELT_FACE)).to_have_count(1)
    # The own chair draws no fan: the card has a place to leave from only because the hand kept where it let it go.
    assert arrival_of(motion_played(own)) == FLIES_FACE_UP
    assert page_errors == []


def test_a_card_the_viewers_seat_played_on_another_device_flies_face_up_out_of_the_own_hand(
    deal_a_playing_table: Callable[..., PlayingTable], page_errors: list[str]
) -> None:
    table = deal_a_playing_table(PHONE)
    own = table.pages[table.turn_seat()]
    own.emulate_media(reduced_motion=MOTION)
    own.reload()
    expect(own.locator(".chair")).to_have_count(3)
    watch_the_motion(own)

    table.play_out(1)

    expect(own.locator(FELT_FACE)).to_have_count(1)
    # This page let no card go, so the card leaves the hand that held it, which shows its faces.
    assert arrival_of(motion_played(own)) == FLIES_FACE_UP
    flight = next(piece["frames"] for piece in motion_played(own) if piece["piece"] == "face")
    assert flight[0]["transform"] != flight[-1]["transform"]
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_card_of_a_trick_rests_with_its_own_lie_the_same_for_every_seat_and_watcher_and_after_a_reload(
    deal_a_playing_table: Callable[..., PlayingTable],
    open_person: Callable[..., Page],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_a_playing_table(form_factor)
    table.leave_the_last_trick_on_the_felt()
    moving = open_watcher_with_motion(open_person, page_errors, table, form_factor, stored={"lastTrick": "stay"})

    table.play_out(CARDS_IN_A_TRICK)

    lies = lies_of(table.watcher, CARDS_IN_A_TRICK)
    assert len({(lie["x"], lie["y"], lie["turn"]) for lie in lies.values()}) == CARDS_IN_A_TRICK
    for lie in lies.values():
        assert abs(lie["x"]) + abs(lie["y"]) + abs(lie["turn"]) > LIE_SEEN
        # A card never lies off its slot downward, where its name hangs.
        assert lie["y"] < LIE_SEEN
    for person in (*table.pages.values(), moving):
        expect_the_same_lies(lies_of(person, CARDS_IN_A_TRICK), lies)
    for person in (table.pages[table.declarer_seat], moving):
        person.reload()
        expect(person.locator(".chair")).to_have_count(3)
        expect_the_same_lies(lies_of(person, CARDS_IN_A_TRICK), lies)
    assert page_errors == []
