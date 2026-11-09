import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.engine.cards import Card, Rank, Suit
from skat.engine.games import GameKind
from skat.engine.play import legal_cards, trick_winner
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.words import catalog_text

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.declaring import DeclaringTable

pytestmark = pytest.mark.e2e

CARDS_IN_A_HAND = 10
GRAND_OUVERT = f"{catalog_text('gameGrand')} {catalog_text('ouvert')}"
TOKEN_SUITS: dict[str, Suit] = {token: suit for suit, token in SUIT_TOKENS.items()}
TOKEN_RANKS: dict[str, Rank] = {token: rank for rank, token in RANK_TOKENS.items()}
OPEN_TAG = catalog_text("open")
PLAQUE = ".plaque"
OPEN_CARD = ".open .card"
OPEN_FACE = f"{OPEN_CARD} .card-face"
OPEN_TAG_SELECTOR = ".open-tag"
FAN = ".fan-spot"
# The viewport-independent test of "readable": a card's strip, as wide as the step between two cards of its row.
BOXES_OVERLAP = """([first, second]) => {
    const a = first.getBoundingClientRect();
    const b = second.getBoundingClientRect();
    return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}"""
INSIDE_THE_VIEWPORT = """(element) => {
    const box = element.getBoundingClientRect();
    return box.left >= 0 && box.right <= window.innerWidth && box.top >= 0 && box.bottom <= window.innerHeight;
}"""


def declare_grand_ouvert(table: DeclaringTable) -> None:
    table.declare_through_the_api(action="declare", game="grand", hand=True, ouvert=True, announcement="schwarz")


def declarer_chair(person: Page, table: DeclaringTable) -> Locator:
    return person.locator(f".chair[data-seat='{table.declarer_seat}']")


def faces_of(cards: Locator) -> set[tuple[str, str]]:
    drawn = cards.evaluate_all("(faces) => faces.map((face) => [face.dataset.suit, face.dataset.rank])")
    return {(suit, rank) for suit, rank in drawn}


def the_view(table: DeclaringTable, seat: int) -> dict[str, Any]:
    return json.loads(table.sessions[seat].get(table.api_path))


def engine_card(card: dict[str, str]) -> Card:
    return Card(TOKEN_SUITS[card["suit"]], TOKEN_RANKS[card["rank"]])


def play(table: DeclaringTable, seat: int, card: Card) -> None:
    table.step(seat, TABLE_CARD_SUFFIX, suit=SUIT_TOKENS[card.suit], rank=RANK_TOKENS[card.rank])


def seat_of_position(table: DeclaringTable, position: str) -> int:
    chairs = the_view(table, table.declarer_seat)["chairs"]
    return next(chair["seat"] for chair in chairs if chair["hand"]["position"] == position)


def declarer_cards_while_the_declarer_wins_the_first_trick(table: DeclaringTable) -> Iterator[Card]:
    """Plays until the declarer has led his second card, yielding each card of his after it is played.

    The three hands are known by API, so the first trick is played to a triple the declarer wins: an opponent's
    trick would end the game announced Schwarz at once, and the second card would never be played."""
    forehand, rearhand = seat_of_position(table, "forehand"), seat_of_position(table, "rearhand")
    held = {
        seat: tuple(engine_card(card) for card in the_view(table, seat)["hand"]["own_cards"])
        for seat in (forehand, table.declarer_seat, rearhand)
    }
    kind = GameKind.GRAND
    for lead in held[forehand]:
        for answer in legal_cards(held[table.declarer_seat], lead, kind):
            for last in legal_cards(held[rearhand], lead, kind):
                if trick_winner((lead, answer, last), kind) == 1:
                    play(table, forehand, lead)
                    play(table, table.declarer_seat, answer)
                    yield answer
                    play(table, rearhand, last)
                    second = next(card for card in held[table.declarer_seat] if card != answer)
                    play(table, table.declarer_seat, second)
                    yield second
                    return
    message = "no first trick the declarer wins"
    raise AssertionError(message)


def onlookers(table: DeclaringTable) -> list[Page]:
    return [*table.others, table.watcher]


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_everyone_but_the_declarer_sees_the_open_cards_from_the_declaration_on(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declare_grand_ouvert(table)
    held = {(card["suit"], card["rank"]) for card in the_view(table, table.declarer_seat)["hand"]["own_cards"]}

    for person in onlookers(table):
        chair = declarer_chair(person, table)
        expect(chair.locator(OPEN_CARD)).to_have_count(CARDS_IN_A_HAND)
        assert faces_of(chair.locator(OPEN_FACE)) == held
        expect(chair.locator(FAN)).to_have_count(0)
        expect(chair.locator(OPEN_TAG_SELECTOR)).to_have_count(0)
        expect(person.locator(PLAQUE)).to_contain_text(GRAND_OUVERT)
        top_row = chair.locator(".open-row").first.locator(".card")
        assert top_row.first.evaluate(INSIDE_THE_VIEWPORT)
        assert chair.locator(".open-row").first.evaluate(INSIDE_THE_VIEWPORT)
        plaque_and_rows = [person.locator(PLAQUE).element_handle(), chair.locator(".open").element_handle()]
        assert not person.evaluate(BOXES_OVERLAP, plaque_and_rows)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_declarer_keeps_the_own_hand_and_wears_the_tag_instead_of_open_rows(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declare_grand_ouvert(table)

    expect(table.declarer.locator(".own-hand .card")).to_have_count(CARDS_IN_A_HAND)
    expect(table.declarer.locator(OPEN_TAG_SELECTOR)).to_contain_text(OPEN_TAG)
    expect(table.declarer.locator(OPEN_TAG_SELECTOR)).to_have_attribute("title", catalog_text("openForAll"))
    expect(table.declarer.locator(".open")).to_have_count(0)
    expect(table.declarer.locator(PLAQUE)).to_contain_text(GRAND_OUVERT)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_open_rows_lose_each_card_the_declarer_plays_and_survive_a_reload(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declare_grand_ouvert(table)

    played: set[tuple[str, str]] = set()
    for card in declarer_cards_while_the_declarer_wins_the_first_trick(table):
        played.add((SUIT_TOKENS[card.suit], RANK_TOKENS[card.rank]))
        for person in onlookers(table):
            chair = declarer_chair(person, table)
            expect(chair.locator(OPEN_CARD)).to_have_count(CARDS_IN_A_HAND - len(played))
            assert not faces_of(chair.locator(OPEN_FACE)) & played

    for person in onlookers(table):
        chair = declarer_chair(person, table)
        felt = person.locator(".trick")
        for laid in felt.locator(".laid").all():
            assert not person.evaluate(BOXES_OVERLAP, [laid.element_handle(), chair.locator(".open").element_handle()])
        person.reload()
        chair = declarer_chair(person, table)
        expect(chair.locator(OPEN_CARD)).to_have_count(CARDS_IN_A_HAND - len(played))
        assert not faces_of(chair.locator(OPEN_FACE)) & played
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_game_that_is_not_ouvert_keeps_its_back_fans_and_shows_no_tag(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    table.declare_through_the_api(action="declare", game="grand", hand=True, ouvert=False, announcement="none")

    for person in (*onlookers(table), table.declarer):
        expect(person.locator(PLAQUE)).to_contain_text(catalog_text("gameGrand"))
        expect(person.locator(".open")).to_have_count(0)
        expect(person.locator(OPEN_TAG_SELECTOR)).to_have_count(0)
    for person in onlookers(table):
        expect(declarer_chair(person, table).locator(FAN)).to_have_count(1)
    assert page_errors == []
