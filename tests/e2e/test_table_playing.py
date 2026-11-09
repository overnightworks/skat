import itertools
import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from skat.web.playing import TABLE_CARD_SUFFIX
from tests.e2e.support.words import catalog_text
from tests.e2e.test_table_declaring import WIDTHS, DeclaringTable

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

WE = catalog_text("sideUs")
THEY = catalog_text("sideThem")
COMMAND_FAILED = catalog_text("commandFailed")
NULL_GAME = catalog_text("gameNull")
KREUZ = catalog_text("gameKreuz")
HAND_CARD = ".own-hand .card"
LEGAL_CARD = f"{HAND_CARD}.ok"
LIFTED_CARD = f"{HAND_CARD}.touch"
DIMMED_CARD = f"{HAND_CARD}.no"
PLAYABLE_CARD = f"{HAND_CARD} button"
FELT_CARD = ".trick .laid"
TURN_CHAIR = ".chair.turn"
CARDS_IN_A_HAND = 10
CARDS_IN_A_TRICK = 3
CARDS_IN_PLAY = 30
# The fan shows each card's left strip, and the next card covers its middle, where a plain click lands.
INSIDE_THE_VISIBLE_STRIP = {"x": 8, "y": 40}
# A card on the felt lies toward its player: seen from the trick's middle, it points at that player's chair
# more closely than at any other chair.
TOWARD_CHAIR = """(play) => {
    const middle = (element) => {
        const box = element.getBoundingClientRect();
        return [box.left + box.width / 2, box.top + box.height / 2];
    };
    const [tx, ty] = middle(play.closest('.trick'));
    const [x, y] = middle(play);
    const toward = Math.atan2(y - ty, x - tx);
    const apart = [...document.querySelectorAll('.chair')].map((chair) => {
        const [cx, cy] = middle(chair);
        const angle = Math.abs(Math.atan2(cy - ty, cx - tx) - toward);
        return [Math.min(angle, 2 * Math.PI - angle), Number(chair.dataset.seat)];
    });
    return apart.sort((first, second) => first[0] - second[0])[0][1];
}"""

command_numbers = itertools.count(1)

type WireCard = tuple[str, str]


class PlayingTable:
    """A declared game, Null unless named: the forehand leads, and every card and turn is read by API."""

    def __init__(self, declaring: DeclaringTable, game: str) -> None:
        self.declaring = declaring
        skat = declaring.skat()
        declaring.declare_through_the_api(action="take")
        declaring.declare_through_the_api(
            action="put_back", cards=[{"suit": suit, "rank": rank} for suit, rank in sorted(skat)]
        )
        declaring.declare_through_the_api(action="declare", game=game, hand=False, ouvert=False, announcement="none")
        self.watcher = declaring.watcher
        self.declarer_seat = declaring.declarer_seat
        self.pages = {self.seat_of(person): person for person in (declaring.declarer, *declaring.others)}
        self.everyone = [*self.pages.values(), self.watcher]
        chairs = self.view(self.declarer_seat)["chairs"]
        self.names = {chair["seat"]: chair["occupant_name"] for chair in chairs}
        self.seat_at = {chair["hand"]["position"]: chair["seat"] for chair in chairs}
        for person in self.everyone:
            expect(person.locator(TURN_CHAIR)).to_have_attribute("data-seat", str(self.seat_at["forehand"]))

    @staticmethod
    def seat_of(person: Page) -> int:
        return int(person.locator(".chair.mine").get_attribute("data-seat") or "")

    def view(self, seat: int) -> dict[str, Any]:
        return json.loads(self.declaring.sessions[seat].get(self.declaring.api_path))

    def playing(self) -> dict[str, Any]:
        return self.view(self.declarer_seat)["hand"]["playing"]

    def turn_seat(self) -> int:
        return self.playing()["turn_seat"]

    def own_cards(self, seat: int) -> list[WireCard]:
        return [(card["suit"], card["rank"]) for card in self.view(seat)["hand"]["own_cards"]]

    def legal_cards(self, seat: int) -> set[WireCard]:
        return {(card["suit"], card["rank"]) for card in self.view(seat)["hand"]["playing"]["legal_cards"]}

    def led_card(self) -> WireCard:
        led = self.playing()["current_trick"][0]["card"]
        return led["suit"], led["rank"]

    def _send(self, seat: int, version: int, card: WireCard) -> dict[str, Any]:
        suit, rank = card
        command_id = f"playing-card-{next(command_numbers):04d}"
        body = {"command_id": command_id, "version": version, "suit": suit, "rank": rank}
        return json.loads(self.declaring.sessions[seat].post(f"{self.declaring.api_path}{TABLE_CARD_SUFFIX}", body))

    def play_through_the_api(self, card: WireCard) -> None:
        view = self.view(self.declarer_seat)
        self._send(view["hand"]["playing"]["turn_seat"], view["version"], card)

    def play_out(self, cards: int) -> None:
        """Each seat on turn plays its first legal card, two requests a card: the server's budget is per address."""
        seat = self.turn_seat()
        for _ in range(cards):
            view = self.view(seat)
            legal = sorted((card["suit"], card["rank"]) for card in view["hand"]["playing"]["legal_cards"])
            seat = self._send(seat, view["version"], legal[0])["hand"]["playing"]["turn_seat"]

    def a_lead_the_middlehand_must_follow(self) -> WireCard:
        """A forehand card whose suit the middlehand holds beside another suit: in Null a suit is only its suit."""
        held = {suit for suit, _ in self.own_cards(self.seat_at["middlehand"])}
        for card in self.own_cards(self.seat_at["forehand"]):
            if card[0] in held and len(held) > 1:
                return card
        pytest.fail("the deal gave the forehand no suit the middlehand must follow")

    def side_names_as_seen_by(self, person: Page) -> tuple[str, str]:
        declarer = self.names[self.declarer_seat]
        if person is self.watcher:
            return declarer, THEY
        if person is self.pages[self.declarer_seat]:
            return WE, THEY
        return declarer, WE


@pytest.fixture
def deal_a_playing_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    def deal(form_factor: dict[str, Any], *, console: bool = True, game: str = "null") -> PlayingTable:
        return PlayingTable(
            DeclaringTable(open_person, e2e_server, member_of, page_errors, form_factor, console=console), game
        )

    return deal


def card_in_hand(person: Page, card: WireCard) -> Locator:
    suit, rank = card
    return person.locator(f"{HAND_CARD}:has(.card-face[data-suit='{suit}'][data-rank='{rank}'])")


def faces_of(cards: Locator) -> set[WireCard]:
    drawn = cards.locator(".card-face").evaluate_all(
        "(faces) => faces.map((face) => [face.dataset.suit, face.dataset.rank])"
    )
    return {(suit, rank) for suit, rank in drawn}


def tap(card: Locator) -> None:
    card.click(position=INSIDE_THE_VISIBLE_STRIP)


def card_posts(person: Page) -> list[str]:
    posts: list[str] = []
    person.on(
        "request",
        lambda request: posts.append(request.url) if request.url.endswith(TABLE_CARD_SUFFIX) else None,
    )
    return posts


def reload_and_wait(person: Page) -> None:
    person.reload()
    expect(person.locator(".chair")).to_have_count(3)


def expect_on_the_felt(table: PlayingTable, laid: list[tuple[int, WireCard]]) -> None:
    """Every viewer sees exactly these cards, each at its player's side and tagged with its player's name."""
    for person in table.everyone:
        expect(person.locator(FELT_CARD)).to_have_count(len(laid))
        for seat, card in laid:
            play = person.locator(f"{FELT_CARD}[data-seat='{seat}']")
            expect(play.locator(".tag .name")).to_have_text(table.names[seat])
            assert faces_of(play) == {card}
            assert play.evaluate(TOWARD_CHAIR) == seat


def expect_the_plaque(table: PlayingTable) -> None:
    points = table.playing()["trick_points"]
    for person in table.everyone:
        expect(person.locator(".plaque .game")).to_have_text(NULL_GAME)
        declarer, opponents = table.side_names_as_seen_by(person)
        expect(person.locator(".plaque .sides .declarer")).to_have_text(f"{declarer} {points['declarer']}")
        expect(person.locator(".plaque .sides .opponents")).to_have_text(f"{opponents} {points['opponents']}")


def expect_the_turn(table: PlayingTable, seat: int) -> None:
    for person in table.everyone:
        expect(person.locator(TURN_CHAIR)).to_have_count(1)
        expect(person.locator(TURN_CHAIR)).to_have_attribute("data-seat", str(seat))


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_trick_is_played_on_the_page_and_every_viewer_sees_it(
    deal_a_playing_table: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_playing_table(form_factor)
    forehand_seat, middlehand_seat = table.seat_at["forehand"], table.seat_at["middlehand"]
    forehand, middlehand = table.pages[forehand_seat], table.pages[middlehand_seat]
    expect_the_plaque(table)
    expect_on_the_felt(table, [])

    expect(forehand.locator(LEGAL_CARD)).to_have_count(CARDS_IN_A_HAND)
    expect(forehand.locator(DIMMED_CARD)).to_have_count(0)
    posts = {seat: card_posts(person) for seat, person in table.pages.items()}
    for seat, person in table.pages.items():
        if seat != forehand_seat:
            expect(person.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND)
            expect(person.locator(PLAYABLE_CARD)).to_have_count(0)
            tap(person.locator(HAND_CARD).first)
    lead = table.a_lead_the_middlehand_must_follow()
    other = next(card for card in table.own_cards(forehand_seat) if card != lead)

    tap(card_in_hand(forehand, lead))
    assert faces_of(forehand.locator(LIFTED_CARD)) == {lead}
    tap(card_in_hand(forehand, other))
    assert faces_of(forehand.locator(LIFTED_CARD)) == {other}
    expect(forehand.locator(LEGAL_CARD)).to_have_count(CARDS_IN_A_HAND - 1)
    tap(card_in_hand(forehand, lead))
    expect_on_the_felt(table, [])
    assert all(sent == [] for sent in posts.values())

    tap(card_in_hand(forehand, lead))
    expect_on_the_felt(table, [(forehand_seat, lead)])
    assert len(posts[forehand_seat]) == 1
    expect_the_turn(table, middlehand_seat)
    for person in (forehand, table.watcher):
        reload_and_wait(person)
    expect_on_the_felt(table, [(forehand_seat, lead)])
    expect_the_turn(table, middlehand_seat)
    expect_the_plaque(table)
    expect(forehand.locator(PLAYABLE_CARD)).to_have_count(0)

    legal = table.legal_cards(middlehand_seat)
    held = set(table.own_cards(middlehand_seat))
    assert set() < legal < held
    expect(middlehand.locator(LEGAL_CARD)).to_have_count(len(legal))
    assert faces_of(middlehand.locator(LEGAL_CARD)) == legal
    assert faces_of(middlehand.locator(DIMMED_CARD)) == held - legal
    expect(middlehand.locator(f"{DIMMED_CARD} button")).to_have_count(0)
    tap(card_in_hand(middlehand, sorted(held - legal)[0]))
    expect(middlehand.locator(LIFTED_CARD)).to_have_count(0)
    follow = sorted(legal)[0]
    tap(card_in_hand(middlehand, follow))
    expect(middlehand.locator(LIFTED_CARD)).to_have_count(1)
    card_in_hand(middlehand, follow).dblclick(position=INSIDE_THE_VISIBLE_STRIP)
    expect_on_the_felt(table, [(forehand_seat, lead), (middlehand_seat, follow)])
    assert len(posts[middlehand_seat]) == 1

    third = sorted(table.legal_cards(table.seat_at["rearhand"]))[0]
    table.play_through_the_api(third)
    trick = [(forehand_seat, lead), (middlehand_seat, follow), (table.seat_at["rearhand"], third)]
    expect_on_the_felt(table, trick)
    taker = table.playing()["last_trick"]["taker_seat"]
    expect_the_turn(table, taker)
    expect_the_plaque(table)

    table.play_out(1)
    expect_on_the_felt(table, [(taker, table.led_card())])
    expect(table.watcher.locator(".own-hand")).to_have_count(0)
    expect(table.watcher.locator(".card-face")).to_have_count(1)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_stale_page_shows_the_refusal_and_the_stream_corrects_it(
    deal_a_playing_table: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    # The browser logs the refused card as a console error; that refusal is the point of this test.
    table = deal_a_playing_table(form_factor, console=False)
    forehand_seat = table.seat_at["forehand"]
    forehand = table.pages[forehand_seat]
    shown, played_elsewhere = sorted(table.legal_cards(forehand_seat))[:2]

    def play_through_the_api_first(route: Route) -> None:
        table.play_through_the_api(played_elsewhere)
        route.continue_()

    forehand.route(f"**{table.declaring.api_path}{TABLE_CARD_SUFFIX}", play_through_the_api_first)
    tap(card_in_hand(forehand, shown))
    tap(card_in_hand(forehand, shown))

    expect(forehand.locator(".note")).to_have_text(COMMAND_FAILED)
    expect_on_the_felt(table, [(forehand_seat, played_elsewhere)])
    expect(forehand.locator(HAND_CARD)).to_have_count(CARDS_IN_A_HAND - 1)
    assert faces_of(forehand.locator(HAND_CARD)) >= {shown}
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_keyboard_reaches_only_the_legal_cards_and_plays_with_two_presses(
    deal_a_playing_table: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_playing_table(form_factor)
    forehand_seat, middlehand_seat = table.seat_at["forehand"], table.seat_at["middlehand"]
    lead = table.a_lead_the_middlehand_must_follow()
    table.play_through_the_api(lead)
    middlehand = table.pages[middlehand_seat]
    legal = table.legal_cards(middlehand_seat)
    buttons = middlehand.locator(PLAYABLE_CARD)
    expect(buttons).to_have_count(len(legal))
    posts = card_posts(middlehand)

    buttons.first.focus()
    for index in range(1, len(legal)):
        middlehand.keyboard.press("Tab")
        expect(buttons.nth(index)).to_be_focused()
    middlehand.keyboard.press("Enter")
    expect(middlehand.locator(LIFTED_CARD)).to_have_count(1)
    lifted = faces_of(middlehand.locator(LIFTED_CARD))
    assert lifted <= legal
    assert posts == []
    middlehand.keyboard.press("Enter")

    expect_on_the_felt(table, [(forehand_seat, lead), (middlehand_seat, next(iter(lifted)))])
    assert len(posts) == 1
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_after_the_thirtieth_card_no_card_can_be_tapped_and_nothing_breathes(
    deal_a_playing_table: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_playing_table(form_factor, game="kreuz")
    for person in table.everyone:
        expect(person.locator(".plaque .game")).to_have_text(KREUZ)
        expect(person.locator(".plaque .game .suit.kreuz")).to_be_visible()
    table.play_out(CARDS_IN_PLAY - 1)
    last_player = table.pages[table.turn_seat()]
    expect(last_player.locator(PLAYABLE_CARD)).to_have_count(1)

    tap(last_player.locator(HAND_CARD))
    tap(last_player.locator(HAND_CARD))

    for person in table.everyone:
        expect(person.locator(HAND_CARD)).to_have_count(0)
        expect(person.locator(TURN_CHAIR)).to_have_count(0)
    assert page_errors == []
