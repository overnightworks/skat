import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.engine.cards import Card, Rank, Suit
from skat.engine.games import GameKind
from skat.engine.play import legal_cards, trick_winner
from skat.web.declaring import TABLE_DECLARING_DECLARE_SUFFIX
from skat.web.playing import TABLE_CARD_SUFFIX, TABLE_GIVE_UP_SUFFIX
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import button_of, reload_and_wait
from tests.e2e.support.hands import PlayingTable
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.server import AlwaysTheSameDeal, skat_on_new_database

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from tests.e2e.support.declaring import DeclaringTable
    from tests.e2e.support.server import RunningServer

pytestmark = pytest.mark.e2e

CARDS_IN_A_HAND = 10
WINNING_DEAL_SEED = 1
NARROW_BELOW = 900
GRAND_OUVERT = text(SOURCE_LANGUAGE, "game.ouvertName", game=text(SOURCE_LANGUAGE, "game.grand"))
TOKEN_SUITS: dict[str, Suit] = {token: suit for suit, token in SUIT_TOKENS.items()}
TOKEN_RANKS: dict[str, Rank] = {token: rank for rank, token in RANK_TOKENS.items()}
OPEN_TAG = text(SOURCE_LANGUAGE, "table.open")
NULL_GAME = text(SOURCE_LANGUAGE, "game.null")
NULL_OUVERT = text(SOURCE_LANGUAGE, "game.ouvertName", game=NULL_GAME)
NULL_OUVERT_HAND = text(SOURCE_LANGUAGE, "game.ouvertHandName", game=NULL_GAME)
OUVERT_RUNG = text(SOURCE_LANGUAGE, "declare.levelOuvert")
SCHNEIDER = text(SOURCE_LANGUAGE, "declare.levelSchneider")
SCHWARZ = text(SOURCE_LANGUAGE, "declare.levelSchwarz")
HAND = text(SOURCE_LANGUAGE, "declare.hand")
TAKE_SKAT = text(SOURCE_LANGUAGE, "declare.takeSkat")
PUT_BACK = text(SOURCE_LANGUAGE, "declare.putBack")
ANNOUNCE = text(SOURCE_LANGUAGE, "declare.announceGame")
ANNOUNCED_MARK = ".plaque .announced"
LADDER = ".declare .ladder"
RESULT_CARD = ".result"
PRESSED = "aria-pressed"
SUIT_TILES = 4
OTHER_TILES = 3
NULL_OUVERT_VALUE = 46
NULL_OUVERT_HAND_VALUE = 59
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


@pytest.fixture(scope="module")
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """This module's Skat, which deals every hand as one in which the declarer can win a first trick of Grand."""
    with skat_on_new_database(tmp_path_factory, random_source=AlwaysTheSameDeal(WINNING_DEAL_SEED)) as server:
        yield server


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
        rows = chair.locator(".open").element_handle()
        for lower in person.locator(".controls, footer.legal").all():
            assert not person.evaluate(BOXES_OVERLAP, [lower.element_handle(), rows])
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_declarer_keeps_the_own_hand_and_wears_the_tag_instead_of_open_rows(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declare_grand_ouvert(table)

    expect(table.declarer.locator(".own-hand .card")).to_have_count(CARDS_IN_A_HAND)
    expect(table.declarer.locator(OPEN_TAG_SELECTOR)).to_contain_text(OPEN_TAG)
    expect(table.declarer.locator(OPEN_TAG_SELECTOR)).to_have_attribute(
        "title", text(SOURCE_LANGUAGE, "table.openForAll")
    )
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
            rows = chair.locator(".open").element_handle()
            for laid in person.locator(".trick .laid, .trick .laid .tag").all():
                assert not person.evaluate(BOXES_OVERLAP, [laid.element_handle(), rows])

    for person in onlookers(table):
        chair = declarer_chair(person, table)
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
        expect(person.locator(PLAQUE)).to_contain_text(text(SOURCE_LANGUAGE, "game.grand"))
        expect(person.locator(".open")).to_have_count(0)
        expect(person.locator(OPEN_TAG_SELECTOR)).to_have_count(0)
    for person in onlookers(table):
        expect(declarer_chair(person, table).locator(FAN)).to_have_count(1)
    assert page_errors == []


def put_the_skat_back(table: DeclaringTable) -> None:
    table.declare_through_the_api(action="take")
    skat = sorted(table.skat())
    table.declare_through_the_api(action="put_back", cards=[{"suit": suit, "rank": rank} for suit, rank in skat])


def expect_open_cards_without_the_skat(table: DeclaringTable, skat: set[tuple[str, str]]) -> None:
    held = {(card["suit"], card["rank"]) for card in the_view(table, table.declarer_seat)["hand"]["own_cards"]}
    assert not held & skat
    for person in onlookers(table):
        chair = declarer_chair(person, table)
        expect(chair.locator(OPEN_CARD)).to_have_count(CARDS_IN_A_HAND)
        assert faces_of(chair.locator(OPEN_FACE)) == held
        assert not faces_of(person.locator(".card-face")) & skat
    for seat in range(1, 4):
        if seat != table.declarer_seat:
            view = the_view(table, seat)["hand"]
            assert not {(c["suit"], c["rank"]) for c in view.get("open_cards", [])} & skat
            assert not {(c["suit"], c["rank"]) for c in view.get("own_cards", [])} & skat


def give_up_and_read_the_result(table: DeclaringTable, label: str, value: int) -> None:
    table.step(table.declarer_seat, TABLE_GIVE_UP_SUFFIX)
    for person in (table.declarer, *onlookers(table)):
        expect(person.locator(RESULT_CARD)).to_contain_text(label)
        expect(person.locator(".open")).to_have_count(0)
    assert the_view(table, table.declarer_seat)["result"]["game_value"] == value


def expect_the_tiles_on_two_rows_of_four_and_three(person: Page) -> None:
    tiles = person.locator(".declare .game")
    expect(tiles).to_have_count(SUIT_TILES + OTHER_TILES)
    rows = [round(box["y"]) for box in (tile.bounding_box() for tile in tiles.all()) if box is not None]
    assert len(set(rows[:SUIT_TILES])) == 1
    assert len(set(rows[SUIT_TILES:])) == 1
    assert rows[SUIT_TILES] > rows[0]


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_null_ouvert_after_the_take_is_offered_without_levels_and_declared_with_one_command(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    posts: list[str] = []
    declarer.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
    button_of(declarer, TAKE_SKAT).click()
    cards = declarer.locator(".own-hand .card button")
    expect(cards).to_have_count(CARDS_IN_A_HAND + 2)
    taken = faces_of(declarer.locator(".own-hand .card-face"))
    for index in range(2):
        cards.nth(index).click(position={"x": 8, "y": 40})
    button_of(declarer, PUT_BACK).click()

    expect(button_of(declarer, NULL_OUVERT)).to_be_visible()
    expect_the_tiles_on_two_rows_of_four_and_three(declarer)
    for level in (SCHNEIDER, SCHWARZ, OUVERT_RUNG):
        expect(button_of(declarer, level)).to_have_count(0)
    reload_and_wait(declarer)
    expect(button_of(declarer, NULL_OUVERT)).to_have_attribute(PRESSED, "false")
    expect(button_of(declarer, ANNOUNCE)).to_be_disabled()

    button_of(declarer, NULL_OUVERT).click()
    expect(button_of(declarer, NULL_OUVERT)).to_have_attribute(PRESSED, "true")
    posts.clear()
    button_of(declarer, ANNOUNCE).dblclick()
    expect(declarer.locator(OPEN_TAG_SELECTOR)).to_contain_text(OPEN_TAG)
    sent = [url for url in posts if url.endswith(f"{table.api_path}{TABLE_DECLARING_DECLARE_SUFFIX}")]
    assert len(sent) == 1
    declaration = table.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": "null", "hand": False, "ouvert": True, "announcement": "none"}
    cards_put_back = taken - {
        (card["suit"], card["rank"]) for card in the_view(table, table.declarer_seat)["hand"]["own_cards"]
    }
    assert len(cards_put_back) == 2
    expect_open_cards_without_the_skat(table, cards_put_back)
    for person in (*onlookers(table), declarer):
        reload_and_wait(person)
        expect(person.locator(PLAQUE)).to_contain_text(NULL_OUVERT)
        expect(person.locator(PLAQUE)).not_to_contain_text(NULL_OUVERT_HAND)
        expect(person.locator(ANNOUNCED_MARK)).to_have_count(0)
    expect_open_cards_without_the_skat(table, cards_put_back)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_given_up_null_ouvert_game_is_valued_and_named_on_every_result_card(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    put_the_skat_back(table)
    table.declare_through_the_api(action="declare", game="null", hand=False, ouvert=True, announcement="none")

    give_up_and_read_the_result(table, NULL_OUVERT, NULL_OUVERT_VALUE)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_null_ouvert_in_the_hand_panel_hides_the_levels_and_is_named_null_ouvert_hand(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    skat = table.skat()
    posts: list[str] = []
    declarer.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
    button_of(declarer, HAND).click()
    expect(declarer.locator(LADDER)).to_contain_text(OUVERT_RUNG)
    expect_the_tiles_on_two_rows_of_four_and_three(declarer)
    button_of(declarer, SCHWARZ).click()
    button_of(declarer, OUVERT_RUNG).click()
    button_of(declarer, NULL_OUVERT).click()
    for level in (SCHNEIDER, SCHWARZ, OUVERT_RUNG):
        expect(button_of(declarer, level)).to_have_count(0)
    assert posts == []

    button_of(declarer, ANNOUNCE).click()
    expect(declarer.locator(OPEN_TAG_SELECTOR)).to_contain_text(OPEN_TAG)
    declaration = table.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": "null", "hand": True, "ouvert": True, "announcement": "none"}
    for person in (*onlookers(table), declarer):
        expect(person.locator(PLAQUE)).to_contain_text(NULL_OUVERT_HAND)
        reload_and_wait(person)
        expect(person.locator(PLAQUE)).to_contain_text(NULL_OUVERT_HAND)
    for person in onlookers(table):
        assert not faces_of(person.locator(".card-face")) & skat
        expect(declarer_chair(person, table).locator(OPEN_CARD)).to_have_count(CARDS_IN_A_HAND)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_given_up_null_ouvert_hand_game_is_valued_and_named_on_every_result_card(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    table.declare_through_the_api(action="declare", game="null", hand=True, ouvert=True, announcement="none")

    give_up_and_read_the_result(table, NULL_OUVERT_HAND, NULL_OUVERT_HAND_VALUE)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
@pytest.mark.parametrize(("game", "word_key"), [("herz", "game.herz"), ("grand", "game.grand")])
def test_the_ouvert_rung_releases_a_level_and_declares_an_ouvert_game_named_without_an_announcement(
    deal_a_declaring_table: Callable[..., DeclaringTable],
    page_errors: list[str],
    form_factor: dict[str, Any],
    game: str,
    word_key: str,
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    posts: list[tuple[str, str | None]] = []
    declarer.on(
        "request", lambda request: posts.append((request.url, request.post_data)) if request.method == "POST" else None
    )
    button_of(declarer, HAND).click()
    button_of(declarer, text(SOURCE_LANGUAGE, word_key)).click()
    button_of(declarer, SCHNEIDER).click()
    button_of(declarer, OUVERT_RUNG).click()
    expect(button_of(declarer, OUVERT_RUNG)).to_have_attribute(PRESSED, "true")
    expect(button_of(declarer, SCHNEIDER)).to_have_attribute(PRESSED, "false")
    assert posts == []
    button_of(declarer, ANNOUNCE).dblclick()
    expect(declarer.locator(OPEN_TAG_SELECTOR)).to_contain_text(OPEN_TAG)

    sent = [body for url, body in posts if url.endswith(f"{table.api_path}{TABLE_DECLARING_DECLARE_SUFFIX}")]
    assert len(sent) == 1
    body = json.loads(sent[0] or "")
    assert body["ouvert"] is True
    assert body["announcement"] == "none"
    declaration = table.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": game, "hand": True, "ouvert": True, "announcement": "schwarz"}
    playing = PlayingTable(table, None)
    ouvert_name = text(SOURCE_LANGUAGE, "game.ouvertName", game=text(SOURCE_LANGUAGE, word_key))
    for person in playing.everyone:
        expect(person.locator(PLAQUE)).to_contain_text(ouvert_name)
        expect(person.locator(ANNOUNCED_MARK)).to_have_count(0)
        plaque = person.locator(PLAQUE).element_handle()
        for covered in (*person.locator(".fan-spot").all(), *person.locator(".own-hand").all()):
            assert not person.evaluate(BOXES_OVERLAP, [plaque, covered.element_handle()])
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    reload_and_wait(table.watcher)
    expect(table.watcher.locator(PLAQUE)).to_contain_text(ouvert_name)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_ouvert_rung_clears_on_a_second_tap_and_the_levels_return_after_null(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    button_of(declarer, HAND).click()
    button_of(declarer, text(SOURCE_LANGUAGE, "game.grand")).click()
    button_of(declarer, OUVERT_RUNG).click()
    button_of(declarer, OUVERT_RUNG).click()
    expect(button_of(declarer, OUVERT_RUNG)).to_have_attribute(PRESSED, "false")
    button_of(declarer, OUVERT_RUNG).click()
    button_of(declarer, NULL_GAME).click()
    for level in (SCHNEIDER, SCHWARZ, OUVERT_RUNG):
        expect(button_of(declarer, level)).to_have_count(0)
    button_of(declarer, text(SOURCE_LANGUAGE, "game.grand")).click()
    for level in (SCHNEIDER, SCHWARZ, OUVERT_RUNG):
        expect(button_of(declarer, level)).to_have_attribute(PRESSED, "false")

    button_of(declarer, OUVERT_RUNG).click()
    reload_and_wait(declarer)
    expect(button_of(declarer, TAKE_SKAT)).to_be_enabled()
    button_of(declarer, HAND).click()
    button_of(declarer, NULL_OUVERT).click()
    reload_and_wait(declarer)
    expect(button_of(declarer, TAKE_SKAT)).to_be_enabled()
    button_of(declarer, HAND).click()
    button_of(declarer, text(SOURCE_LANGUAGE, "game.grand")).click()
    button_of(declarer, OUVERT_RUNG).click()
    button_of(declarer, ANNOUNCE).click()
    expect(declarer.locator(OPEN_TAG_SELECTOR)).to_contain_text(OPEN_TAG)
    declaration = table.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": "grand", "hand": True, "ouvert": True, "announcement": "schwarz"}
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_keyboard_reaches_the_ouvert_rung_and_the_null_ouvert_tile(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    declarer = deal_a_declaring_table(form_factor).declarer
    button_of(declarer, HAND).focus()
    declarer.keyboard.press("Enter")
    for name in (NULL_OUVERT, text(SOURCE_LANGUAGE, "game.grand"), OUVERT_RUNG):
        control = button_of(declarer, name)
        control.focus()
        declarer.keyboard.press("Space")
        expect(control).to_have_attribute(PRESSED, "true")
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_hand_panel_causes_no_sideways_scroll_and_covers_no_far_fan_skat_back_or_own_chair(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    declarer = deal_a_declaring_table(form_factor).declarer
    button_of(declarer, HAND).click()
    button_of(declarer, text(SOURCE_LANGUAGE, "game.grand")).click()
    panel = declarer.locator(".declare").element_handle()
    assert declarer.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert declarer.locator(".declare").evaluate(INSIDE_THE_VIEWPORT)
    # The wide felt puts the panel in a row through the middle, beside the skat.
    narrow = form_factor["viewport"]["width"] < NARROW_BELOW
    covered_by_the_panel = f"{FAN}, .own-hand, .skat-spot .skat-card" if narrow else f"{FAN}, .own-hand"
    for covered in declarer.locator(covered_by_the_panel).all():
        assert not declarer.evaluate(BOXES_OVERLAP, [panel, covered.element_handle()])
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_game_without_ouvert_is_stored_with_ouvert_false_and_plaque_as_before(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declarer = table.declarer
    button_of(declarer, HAND).click()
    button_of(declarer, text(SOURCE_LANGUAGE, "game.herz")).click()
    button_of(declarer, SCHNEIDER).click()
    button_of(declarer, ANNOUNCE).click()
    expect(declarer.locator(PLAQUE)).to_contain_text(
        text(SOURCE_LANGUAGE, "game.handName", game=text(SOURCE_LANGUAGE, "game.herz"))
    )
    expect(declarer.locator(ANNOUNCED_MARK)).to_have_count(1)
    declaration = table.declaring_as_the_declarer_sees_it()["declaration"]
    assert declaration == {"game": "herz", "hand": True, "ouvert": False, "announcement": "schneider"}
    for person in onlookers(table):
        expect(declarer_chair(person, table).locator(FAN)).to_have_count(1)
        expect(person.locator(".open")).to_have_count(0)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_opponents_see_the_open_rows_on_the_side_the_declarer_sits(
    deal_a_declaring_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declaring_table(form_factor)
    declare_grand_ouvert(table)
    for person in table.others:
        chair = declarer_chair(person, table)
        expect(chair.locator(OPEN_CARD)).to_have_count(CARDS_IN_A_HAND)
        stage = person.locator(".stage").bounding_box()
        rows = chair.locator(".open").bounding_box()
        assert stage is not None
        assert rows is not None
        middle = stage["x"] + stage["width"] / 2
        position = chair.evaluate("(chair) => [...chair.parentElement.children].indexOf(chair)")
        rows_centre = rows["x"] + rows["width"] / 2
        assert (rows_centre < middle) is (position == 0)
    assert page_errors == []
