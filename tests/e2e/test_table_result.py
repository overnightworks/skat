import json
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, Route, expect

from skat.engine.bidding import VALID_BIDS
from skat.engine.declaration import Announcement, Declaration
from skat.engine.games import GameKind
from skat.engine.value import Matadors
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.ready import TABLE_READY_SUFFIX
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.hands import CARDS_IN_PLAY, THEY, WE, PlayingTable, deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.tables import SIT_DOWN
from tests.e2e.support.words import catalog_text
from tests.support.played_game import an_entry

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.table.game_list import ListEntry
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

YOU = catalog_text("sideYou")
WON = catalog_text("resultWon")
LOST = catalog_text("resultLost")
WINS = catalog_text("resultWins")
LOSES = catalog_text("resultLoses")
OVERBID = catalog_text("overbid")
SPIEL = catalog_text("levelSpiel")
HAND = catalog_text("hand")
SCHNEIDER = catalog_text("levelSchneider")
SCHWARZ = catalog_text("levelSchwarz")
OUVERT_CHIP = catalog_text("levelOuvert")
SCHNEIDER_ANNOUNCED = catalog_text("announcedSchneider")
SCHWARZ_ANNOUNCED = catalog_text("announcedSchwarz")
MIT = catalog_text("matadorsWith")
OHNE = catalog_text("matadorsWithout")
LIST_BONUS = catalog_text("listBonus")
EACH = catalog_text("each")
NOT_REACHED = catalog_text("notReached")
OUVERT = catalog_text("ouvert")
GAME_KARO = catalog_text("gameKaro")
GAME_HERZ = catalog_text("gameHerz")
GAME_KREUZ = catalog_text("gameKreuz")
GAME_GRAND = catalog_text("gameGrand")
GAME_NULL = catalog_text("gameNull")
WORTH = catalog_text("gameWorth")
BID_VALUE = catalog_text("bidValue")
WEITER = catalog_text("weiter")
STAND_UP = catalog_text("standUp")
COPY_LINK = catalog_text("copyLink")
WAITING_FOR = catalog_text("waitingFor")
WAITING_FOR_PLAYERS = catalog_text("waitingForPlayers")
AND = catalog_text("and")
COMMAND_FAILED = catalog_text("commandFailed")
SEAT_AWAY = catalog_text("seatAway")
SEAT_FREE = catalog_text("seatFree")
CARD = ".result"
READY_MARK = ".mark.ready"
OWN_HAND_CARD = ".own-hand .card"
CARDS_IN_A_HAND = 10
MINUS = chr(0x2212)
TIMES = chr(0x00D7)
LONG_NAMES = ("Bartholom\u00e4us-Maximilian-Ferdinand", "Maximiliane-Bartholom\u00e4a-Ferdinande")

PILL_HEIGHTS = (
    "bar => [...bar.children].filter(child => !child.matches('.link'))"
    ".map(child => child.getBoundingClientRect().height)"
)


class ModestBidTable(DeclaringTable):
    """The middlehand bids the lowest value, so the game declared lies above it and is never overbid."""

    def _win_the_auction(self, seat_at: dict[str, int]) -> None:
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[0])
        self.step(seat_at["forehand"], TABLE_AUCTION_PASS_SUFFIX)
        self.step(seat_at["rearhand"], TABLE_AUCTION_PASS_SUFFIX)


HANDS = [pytest.param(DeclaringTable, id="overbid"), pytest.param(ModestBidTable, id="modest")]


@pytest.fixture
def deal_a_finished_hand(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., PlayingTable]:
    def deal(
        form_factor: dict[str, Any],
        *,
        declaring: type[DeclaringTable] = DeclaringTable,
        console: bool = True,
        joiners: tuple[str, str] = ("ben", "cleo"),
    ) -> PlayingTable:
        table = deal_playing_table(
            open_person,
            e2e_server,
            member_of,
            page_errors,
            form_factor,
            console=console,
            game="kreuz",
            declaring=declaring,
            joiners=joiners,
        )
        table.play_out(CARDS_IN_PLAY)
        return table

    return deal


def with_minus(number: int) -> str:
    return f"{MINUS}{-number}" if number < 0 else str(number)


def signed(number: int) -> str:
    return with_minus(number) if number < 0 else f"+{number}"


def awaited(table: PlayingTable, ready: set[int]) -> str:
    return f" {AND} ".join(name for seat, name in table.names.items() if seat not in ready)


def role_of(table: PlayingTable, person: Page) -> str:
    if person is table.watcher:
        return "watcher"
    return "declarer" if person is table.pages[table.declarer_seat] else "opponent"


def expected_word(table: PlayingTable, person: Page) -> str:
    won = table.result()["won"]
    role = role_of(table, person)
    if role == "watcher":
        return f"{table.names[table.declarer_seat]} {WINS if won else LOSES}"
    return WON if won == (role == "declarer") else LOST


def loosely(*parts: str) -> re.Pattern[str]:
    """The parts in order, whatever whitespace the page puts between its elements."""
    return re.compile(r"^\s*" + r"\s*".join(re.escape(part) for part in parts) + r"\s*$")


def expect_the_card(table: PlayingTable) -> None:
    """Every viewer reads the card as the answer counted it, from their own side."""
    result = table.result()
    for person in table.everyone:
        role = role_of(table, person)
        card = person.locator(CARD)
        expect(card).to_have_count(1)
        expect(card.locator("h3")).to_have_text(expected_word(table, person))
        expect(card.locator(".value")).to_have_text(signed(result["score"]))
        expect(card.locator(".x2")).to_have_count(1 if result["doubled"] else 0)
        expect(card.locator(".ladder > *")).to_have_count(len(result["levels"]) + 1)
        equation = [str(result["multiplier"]), TIMES, str(result["base_value"])]
        if result["doubled"]:
            equation += ["=", str(result["game_value"])]
        expect(card.locator(".eq")).to_have_text(loosely(*equation))
        expect(card.locator(".miss.missed")).to_have_count(1 if result["announcement_missed"] else 0)
        if result["overbid"]:
            expect(card.locator(".stamp")).to_have_text(OVERBID)
            expect(card.locator(".miss:not(.missed)")).to_have_text(
                f"{WORTH} {result['game_value']} < {BID_VALUE} {result['bid']} \u2192 {result['settled_value']}"
            )
        else:
            expect(card.locator(".stamp")).to_have_count(0)
            expect(card.locator(".miss:not(.missed)")).to_have_count(0)
        names = {"declarer": (YOU, THEY), "opponent": (table.names[table.declarer_seat], WE)}.get(
            role, (table.names[table.declarer_seat], THEY)
        )
        expect(card.locator(".sides .declarer")).to_have_text(f"{names[0]} {result['declarer_points']}")
        expect(card.locator(".sides .opponents")).to_have_text(f"{names[1]} {result['opponents_points']}")
        declarer_gain = next(gain for gain in result["gains"] if gain["seat"] == result["declarer_seat"])["gain"]
        opponent_gain = next(gain for gain in result["gains"] if gain["seat"] != result["declarer_seat"])["gain"]
        steps = [
            names[0],
            f"{SPIEL} {signed(result['score'])}",
            f"{LIST_BONUS} {signed(result['list_bonus'])}",
            f"= {signed(declarer_gain)}",
        ]
        if result["doubled"]:
            steps.append(f"\u00b7 {names[1]} {EACH} {signed(opponent_gain)}")
        expect(card.locator(".list")).to_have_text(loosely(*steps))
        rows = card.locator(".reck")
        expect(rows).to_have_count(3)
        for gain in result["gains"]:
            row = card.locator(f".reck[data-seat='{gain['seat']}']")
            expect(row.locator(".dl")).to_have_text(signed(gain["gain"]) if gain["gain"] else "0")
            own = role != "watcher" and person is table.pages[gain["seat"]]
            expect(row.locator(".nm")).to_have_text(YOU if own else table.names[gain["seat"]])
            expect(card.locator(f".reck.win[data-seat='{gain['seat']}']")).to_have_count(1 if gain["won"] else 0)


def expect_the_page_around_the_card(people: list[Page]) -> None:
    for person in people:
        expect(person.locator(".card-face")).to_have_count(0)
        expect(person.locator("body")).not_to_contain_text(WAITING_FOR_PLAYERS)
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        bar = person.locator(".actions").bounding_box()
        card = person.locator(CARD).bounding_box()
        assert bar is not None
        assert card is not None
        assert card["y"] >= 0
        assert card["y"] + card["height"] <= bar["y"]


def expect_the_bars_inside_the_pages(table: PlayingTable) -> None:
    for person in table.everyone:
        bar = person.locator(".actions").bounding_box()
        assert bar is not None
        assert bar["x"] >= 0
        assert bar["x"] + bar["width"] <= person.evaluate("window.innerWidth")
        assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def expect_the_marks(table: PlayingTable, ready: set[int]) -> None:
    for person in table.everyone:
        expect(person.locator(".chair .mark.declarer")).to_have_count(1)
        expect(person.locator(f".chair[data-seat='{table.declarer_seat}'] .mark.declarer")).to_have_count(1)
        for seat in table.names:
            expect(person.locator(f".chair[data-seat='{seat}'] {READY_MARK}")).to_have_count(1 if seat in ready else 0)


def expect_the_buttons(table: PlayingTable, ready: set[int]) -> None:
    """The seated viewers' bars: „Weiter“ until they have tapped, then who is awaited; the watcher's has neither."""
    for seat, person in table.pages.items():
        bar = person.locator(".actions")
        assert bar.evaluate("bar => new Set([...bar.children].map(child => child.offsetTop)).size") == 1
        expect(bar.get_by_role("button", name=STAND_UP)).to_be_visible()
        expect(bar.get_by_role("button", name=COPY_LINK)).to_be_visible()
        if seat in ready:
            expect(bar.get_by_role("button", name=WEITER)).to_have_count(0)
            expect(bar.get_by_role("status")).to_have_text(f"{WAITING_FOR} {awaited(table, ready)}")
        else:
            expect(bar.get_by_role("button", name=WEITER)).to_be_visible()
    for name in (WEITER, STAND_UP):
        expect(table.watcher.locator(".actions").get_by_role("button", name=name)).to_have_count(0)


def reload_everyone(table: PlayingTable) -> None:
    for person in table.everyone:
        person.reload()
        expect(person.locator(".chair")).to_have_count(3)


@pytest.mark.parametrize("declaring", HANDS)
@pytest.mark.parametrize("form_factor", WIDTHS)
def test_everyone_reads_the_result_and_the_three_taps_deal_the_next_hand(
    deal_a_finished_hand: Callable[..., PlayingTable],
    page_errors: list[str],
    form_factor: dict[str, Any],
    declaring: type[DeclaringTable],
) -> None:
    table = deal_a_finished_hand(form_factor, declaring=declaring)
    first, second = (seat for seat in table.names if seat != table.declarer_seat)
    expect_the_card(table)
    expect_the_page_around_the_card(table.everyone)
    expect_the_marks(table, set())
    expect_the_buttons(table, set())

    table.pages[first].locator(".actions").get_by_role("button", name=WEITER).click()
    expect_the_marks(table, {first})
    expect_the_buttons(table, {first})
    expect_the_bars_inside_the_pages(table)
    reload_everyone(table)
    expect_the_card(table)
    expect_the_marks(table, {first})
    expect_the_buttons(table, {first})

    table.pages[second].locator(".actions").get_by_role("button", name=WEITER).click()
    table.pages[table.declarer_seat].locator(".actions").get_by_role("button", name=WEITER).click()
    for person in table.everyone:
        expect(person.locator(CARD)).to_have_count(0)
    for person in table.pages.values():
        expect(person.locator(OWN_HAND_CARD)).to_have_count(CARDS_IN_A_HAND)
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_very_long_name_leaves_every_pill_of_the_result_bar_whole(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor, joiners=LONG_NAMES)
    person = table.pages[table.declarer_seat]
    bar = person.locator(".actions")
    bar.get_by_role("button", name=WEITER).click()
    expect(bar.get_by_role("status")).to_contain_text(awaited(table, {table.declarer_seat}))
    heights = bar.evaluate(PILL_HEIGHTS)
    link = bar.locator(".copy.link").bounding_box()
    assert link is not None
    assert link["width"] >= link["height"]
    assert len(set(heights)) == 1
    expect_the_bars_inside_the_pages(table)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_wait_pill_holds_its_whole_text_with_a_25_character_name(
    deal_a_finished_hand: Callable[..., PlayingTable], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor, joiners=("Maximiliane-Bartholomaea1", "cleo"))
    bar = table.pages[table.declarer_seat].locator(".actions")
    bar.get_by_role("button", name=WEITER).click()
    pill = bar.get_by_role("status")
    expect(pill).to_be_visible()
    assert pill.evaluate(
        "pill => pill.scrollHeight <= pill.clientHeight + 1 && pill.scrollWidth <= pill.clientWidth + 1"
    )
    heights = bar.evaluate(PILL_HEIGHTS)
    assert len(set(heights)) == 1
    expect_the_bars_inside_the_pages(table)


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_member_who_stands_up_leaves_a_free_chair_and_the_card_stays(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    leaver, other = (seat for seat in table.names if seat != table.declarer_seat)
    table.ready_through_the_api(leaver)
    expect_the_marks(table, {leaver})

    table.pages[leaver].locator(".actions").get_by_role("button", name=STAND_UP).click()

    for person in (table.pages[table.declarer_seat], table.pages[other], table.watcher):
        expect(person.locator(f".chair[data-seat='{leaver}'] .plate")).to_have_text(SEAT_FREE)
        expect(person.locator(f".chair[data-seat='{leaver}'] {READY_MARK}")).to_have_count(0)
        expect(person.locator(CARD)).to_have_count(1)
    expect(table.watcher.locator(f".chair[data-seat='{leaver}']").get_by_role("button", name=SIT_DOWN)).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_tap_on_a_result_the_table_has_left_shows_the_failure_note(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    # The browser logs the refused tap as a console error; that refusal is the point of this test.
    table = deal_a_finished_hand(form_factor, console=False)
    tapper_seat = next(seat for seat in table.names if seat != table.declarer_seat)
    tapper = table.pages[tapper_seat]

    def tap_for_another_result(route: Route) -> None:
        route.continue_(post_data='{"command_id": "stale-tap", "ordinal": 99}')

    tapper.route(f"**{table.declaring.api_path}{TABLE_READY_SUFFIX}", tap_for_another_result)
    tapper.locator(".actions").get_by_role("button", name=WEITER).click()

    expect(tapper.locator(".note")).to_have_text(COMMAND_FAILED)
    expect_the_marks(table, set())
    expect(tapper.locator(".actions").get_by_role("button", name=WEITER)).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_the_next_hand_waits_for_an_away_member_who_tapped_until_they_are_back(
    deal_a_finished_hand: Callable[..., PlayingTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_finished_hand(form_factor)
    away_seat, other_seat = (seat for seat in table.names if seat != table.declarer_seat)
    away = table.pages[away_seat]
    away.locator(".actions").get_by_role("button", name=WEITER).click()
    expect_the_marks(table, {away_seat})
    away.close()
    declarer, other = table.pages[table.declarer_seat], table.pages[other_seat]
    expect(declarer.locator(f".chair[data-seat='{away_seat}']")).to_contain_text(SEAT_AWAY)

    for person in (declarer, other):
        person.locator(".actions").get_by_role("button", name=WEITER).click()

    for person in (declarer, other):
        expect(person.locator(".actions").get_by_role("status")).to_have_text(f"{WAITING_FOR} {table.names[away_seat]}")
        expect(person.locator(CARD)).to_have_count(1)

    back = away.context.new_page()
    back.goto(declarer.url)
    for person in (declarer, other, table.watcher, back):
        expect(person.locator(CARD)).to_have_count(0)
    assert page_errors == []


@dataclass(frozen=True)
class Reckoning:
    """One listed game and the card every viewer reads for it, counted by hand from the ISkO value rules."""

    id: str
    entry: ListEntry
    game: str
    chips: tuple[str, ...]
    equation: tuple[str, ...] | None
    value: str
    steps: tuple[str, str, str]
    opponent_gain: str
    raised: str | None = None
    missed: str | None = None
    points: bool = True


def listed(
    kind: GameKind,
    *,
    matadors: Matadors | None,
    hand: bool = False,
    ouvert: bool = False,
    announcement: Announcement = Announcement.NONE,
    **numbers: int | bool,
) -> ListEntry:
    declaration = Declaration(kind, hand=hand, ouvert=ouvert, announcement=announcement)
    return replace(an_entry(), declaration=declaration, matadors=matadors, **numbers)


def steps_of(score: str, bonus: str, gain: str) -> tuple[str, str, str]:
    return f"{SPIEL} {score}", f"{LIST_BONUS} {bonus}", f"= {gain}"


MIT_2 = Matadors(mit=True, count=2)
MIT_1 = Matadors(mit=True, count=1)
KREUZ_MIT_2 = (f"{MIT} 2", SPIEL)
HERZ_HAND_MIT_1 = (f"{MIT} 1", SPIEL, HAND)
HERZ_HAND_SCHNEIDER = (*HERZ_HAND_MIT_1, SCHNEIDER, SCHNEIDER_ANNOUNCED)
GRAND_HAND_SCHWARZ = (*HERZ_HAND_SCHNEIDER, SCHWARZ, SCHWARZ_ANNOUNCED)
GRAND_OUVERT_CHIPS = (*GRAND_HAND_SCHWARZ, OUVERT_CHIP)
GRAND_OUVERT_WORDS = f"{GAME_GRAND} {OUVERT}"
NULL_OUVERT_HAND_WORDS = f"{GAME_NULL} {OUVERT} {HAND}"
SCHNEIDER_MISSED = f"{SCHNEIDER_ANNOUNCED}, {NOT_REACHED}"
SCHWARZ_MISSED = f"{SCHWARZ_ANNOUNCED}, {NOT_REACHED}"
LOST_GAME_SHARE = "+40"

RECKONINGS = [
    Reckoning(
        "kreuz-mit-2-won",
        listed(
            GameKind.KREUZ,
            matadors=MIT_2,
            won=True,
            bid=18,
            game_value=36,
            settled_value=36,
            score=36,
            declarer_points=78,
        ),
        GAME_KREUZ,
        KREUZ_MIT_2,
        ("3", TIMES, "12"),
        "+36",
        steps_of("+36", "+50", "+86"),
        "0",
    ),
    Reckoning(
        "kreuz-mit-2-lost",
        listed(
            GameKind.KREUZ,
            matadors=MIT_2,
            won=False,
            bid=18,
            game_value=36,
            settled_value=36,
            score=-72,
            declarer_points=50,
        ),
        GAME_KREUZ,
        KREUZ_MIT_2,
        ("3", TIMES, "12", "=", "36"),
        f"{MINUS}72",
        steps_of(f"{MINUS}72", f"{MINUS}50", f"{MINUS}122"),
        LOST_GAME_SHARE,
    ),
    Reckoning(
        "karo-mit-1-overbid",
        listed(
            GameKind.KARO,
            matadors=MIT_1,
            won=False,
            bid=20,
            game_value=18,
            settled_value=27,
            score=-54,
            declarer_points=70,
        ),
        GAME_KARO,
        (f"{MIT} 1", SPIEL),
        ("2", TIMES, "9", "=", "18"),
        f"{MINUS}54",
        steps_of(f"{MINUS}54", f"{MINUS}50", f"{MINUS}104"),
        LOST_GAME_SHARE,
        raised=f"{WORTH} 18 < {BID_VALUE} 20 \u2192 27",
    ),
    Reckoning(
        "null-hand-won",
        listed(
            GameKind.NULL,
            matadors=None,
            hand=True,
            won=True,
            bid=23,
            game_value=35,
            settled_value=35,
            score=35,
            declarer_points=0,
        ),
        f"{GAME_NULL} {HAND}",
        (),
        None,
        "+35",
        steps_of("+35", "+50", "+85"),
        "0",
        points=False,
    ),
    Reckoning(
        "null-lost",
        listed(
            GameKind.NULL,
            matadors=None,
            won=False,
            bid=23,
            game_value=23,
            settled_value=23,
            score=-46,
            declarer_points=11,
        ),
        GAME_NULL,
        (),
        (GAME_NULL, "=", "23"),
        f"{MINUS}46",
        steps_of(f"{MINUS}46", f"{MINUS}50", f"{MINUS}96"),
        LOST_GAME_SHARE,
        points=False,
    ),
    Reckoning(
        "grand-ohne-2-won",
        listed(
            GameKind.GRAND,
            matadors=Matadors(mit=False, count=2),
            won=True,
            bid=18,
            game_value=72,
            settled_value=72,
            score=72,
            declarer_points=70,
        ),
        GAME_GRAND,
        (f"{OHNE} 2", SPIEL),
        ("3", TIMES, GAME_GRAND, "24"),
        "+72",
        steps_of("+72", "+50", "+122"),
        "0",
    ),
    Reckoning(
        "herz-hand-mit-1-won",
        listed(
            GameKind.HERZ,
            matadors=MIT_1,
            hand=True,
            won=True,
            bid=18,
            game_value=30,
            settled_value=30,
            score=30,
            declarer_points=80,
        ),
        f"{GAME_HERZ} {HAND}",
        HERZ_HAND_MIT_1,
        ("3", TIMES, "10"),
        "+30",
        steps_of("+30", "+50", "+80"),
        "0",
    ),
    Reckoning(
        "schneider-announced-and-reached",
        listed(
            GameKind.HERZ,
            matadors=MIT_1,
            hand=True,
            announcement=Announcement.SCHNEIDER,
            schneider=True,
            won=True,
            bid=18,
            game_value=50,
            settled_value=50,
            score=50,
            declarer_points=95,
        ),
        f"{GAME_HERZ} {HAND}",
        HERZ_HAND_SCHNEIDER,
        ("5", TIMES, "10"),
        "+50",
        steps_of("+50", "+50", "+100"),
        "0",
    ),
    Reckoning(
        "schneider-announced-and-missed",
        listed(
            GameKind.HERZ,
            matadors=MIT_1,
            hand=True,
            announcement=Announcement.SCHNEIDER,
            schneider=True,
            won=False,
            bid=18,
            game_value=50,
            settled_value=50,
            score=-100,
            declarer_points=75,
        ),
        f"{GAME_HERZ} {HAND}",
        HERZ_HAND_SCHNEIDER,
        ("5", TIMES, "10", "=", "50"),
        f"{MINUS}100",
        steps_of(f"{MINUS}100", f"{MINUS}50", f"{MINUS}150"),
        LOST_GAME_SHARE,
        missed=SCHNEIDER_MISSED,
    ),
    Reckoning(
        "grand-hand-schwarz-announced-and-missed",
        listed(
            GameKind.GRAND,
            matadors=MIT_1,
            hand=True,
            announcement=Announcement.SCHWARZ,
            schneider=True,
            schwarz=True,
            won=False,
            bid=18,
            game_value=168,
            settled_value=168,
            score=-336,
            declarer_points=90,
        ),
        f"{GAME_GRAND} {HAND}",
        GRAND_HAND_SCHWARZ,
        ("7", TIMES, GAME_GRAND, "24", "=", "168"),
        f"{MINUS}336",
        steps_of(f"{MINUS}336", f"{MINUS}50", f"{MINUS}386"),
        LOST_GAME_SHARE,
        missed=SCHWARZ_MISSED,
    ),
    Reckoning(
        "announced-game-overbid",
        listed(
            GameKind.HERZ,
            matadors=MIT_1,
            hand=True,
            announcement=Announcement.SCHNEIDER,
            schneider=True,
            won=False,
            bid=60,
            game_value=50,
            settled_value=60,
            score=-120,
            declarer_points=75,
        ),
        f"{GAME_HERZ} {HAND}",
        HERZ_HAND_SCHNEIDER,
        ("5", TIMES, "10", "=", "50"),
        f"{MINUS}120",
        steps_of(f"{MINUS}120", f"{MINUS}50", f"{MINUS}170"),
        LOST_GAME_SHARE,
        raised=f"{WORTH} 50 < {BID_VALUE} 60 \u2192 60",
    ),
    Reckoning(
        "grand-ouvert-won",
        listed(
            GameKind.GRAND,
            matadors=MIT_1,
            hand=True,
            ouvert=True,
            announcement=Announcement.SCHWARZ,
            schneider=True,
            schwarz=True,
            won=True,
            bid=18,
            game_value=192,
            settled_value=192,
            score=192,
            declarer_points=120,
        ),
        GRAND_OUVERT_WORDS,
        GRAND_OUVERT_CHIPS,
        ("8", TIMES, GAME_GRAND, "24"),
        "+192",
        steps_of("+192", "+50", "+242"),
        "0",
    ),
    Reckoning(
        "grand-ouvert-lost",
        listed(
            GameKind.GRAND,
            matadors=MIT_1,
            hand=True,
            ouvert=True,
            announcement=Announcement.SCHWARZ,
            schneider=True,
            schwarz=True,
            won=False,
            bid=18,
            game_value=192,
            settled_value=192,
            score=-384,
            declarer_points=100,
        ),
        GRAND_OUVERT_WORDS,
        GRAND_OUVERT_CHIPS,
        ("8", TIMES, GAME_GRAND, "24", "=", "192"),
        f"{MINUS}384",
        steps_of(f"{MINUS}384", f"{MINUS}50", f"{MINUS}434"),
        LOST_GAME_SHARE,
        missed=SCHWARZ_MISSED,
    ),
    Reckoning(
        "null-ouvert-hand-won",
        listed(
            GameKind.NULL,
            matadors=None,
            hand=True,
            ouvert=True,
            won=True,
            bid=23,
            game_value=59,
            settled_value=59,
            score=59,
            declarer_points=0,
        ),
        NULL_OUVERT_HAND_WORDS,
        (),
        None,
        "+59",
        steps_of("+59", "+50", "+109"),
        "0",
        points=False,
    ),
    Reckoning(
        "null-ouvert-hand-lost",
        listed(
            GameKind.NULL,
            matadors=None,
            hand=True,
            ouvert=True,
            won=False,
            bid=23,
            game_value=59,
            settled_value=59,
            score=-118,
            declarer_points=11,
        ),
        NULL_OUVERT_HAND_WORDS,
        (),
        (NULL_OUVERT_HAND_WORDS, "=", "59"),
        f"{MINUS}118",
        steps_of(f"{MINUS}118", f"{MINUS}50", f"{MINUS}168"),
        LOST_GAME_SHARE,
        points=False,
    ),
]


def expect_the_reckoning(person: Page, role: str, declarer_name: str, reckoning: Reckoning) -> None:
    """One viewer's card for a listed game: the parts the ISkO value rules make of it, from the viewer's side."""
    entry = reckoning.entry
    card = person.locator(CARD)
    expect(card).to_have_count(1)
    if role == "watcher":
        heading = f"{declarer_name} {WINS if entry.won else LOSES}"
    else:
        heading = WON if entry.won == (role == "declarer") else LOST
    expect(card.locator("h3")).to_have_text(heading)
    declarer_side, opponents_side = {
        "declarer": (YOU, THEY),
        "opponent": (declarer_name, WE),
        "watcher": (declarer_name, THEY),
    }[role]
    game = f"{declarer_name}, {reckoning.game}" if role == "opponent" else reckoning.game
    expect(card.locator(".sub .game")).to_have_text(game)
    if reckoning.chips:
        expect(card.locator(".ladder > *")).to_have_text(list(reckoning.chips))
    else:
        expect(card.locator(".ladder")).to_have_count(0)
    if reckoning.equation is None:
        expect(card.locator(".eq")).to_have_count(0)
    else:
        expect(card.locator(".eq")).to_have_text(loosely(*reckoning.equation))
    if reckoning.raised is None:
        expect(card.locator(".stamp")).to_have_count(0)
        expect(card.locator(".miss:not(.missed)")).to_have_count(0)
    else:
        expect(card.locator(".stamp")).to_have_text(OVERBID)
        expect(card.locator(".miss:not(.missed)")).to_have_text(reckoning.raised)
    if reckoning.missed is None:
        expect(card.locator(".miss.missed")).to_have_count(0)
    else:
        expect(card.locator(".miss.missed")).to_have_text(reckoning.missed)
    expect(card.locator(".x2")).to_have_count(0 if entry.won else 1)
    expect(card.locator(".value")).to_have_text(reckoning.value)
    steps = [declarer_side, *reckoning.steps]
    if not entry.won:
        steps.append(f"\u00b7 {opponents_side} {EACH} {reckoning.opponent_gain}")
    expect(card.locator(".list")).to_have_text(loosely(*steps))
    expect(card.locator(".points")).to_have_count(1 if reckoning.points else 0)
    for seat in (1, 2, 3):
        row = card.locator(f".reck[data-seat='{seat}']")
        declares = seat == entry.declarer_seat
        expect(row.locator(".dl")).to_have_text(
            reckoning.steps[2].removeprefix("= ") if declares else reckoning.opponent_gain
        )
        expect(row).to_have_class(re.compile(r"\bwin\b" if entry.won == declares else r"^(?!.*\bwin\b)"))


@pytest.fixture
def deal_a_declared_table(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
) -> Callable[..., DeclaringTable]:
    def deal(form_factor: dict[str, Any]) -> DeclaringTable:
        return DeclaringTable(open_person, e2e_server, member_of, page_errors, form_factor)

    return deal


def viewers_of(table: DeclaringTable) -> list[tuple[str, Page]]:
    return [
        ("declarer", table.declarer),
        *(("opponent", person) for person in table.others),
        ("watcher", table.watcher),
    ]


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_viewer_reads_the_reckoning_of_each_listed_game_above_the_bar(
    deal_a_declared_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declared_table(form_factor)
    declarer_name = table.name_of_the_declarer()
    viewers = viewers_of(table)
    for reckoning in RECKONINGS:
        table.list_the_game(replace(reckoning.entry, declarer_seat=table.declarer_seat))
        try:
            for role, person in viewers:
                expect_the_reckoning(person, role, declarer_name, reckoning)
            expect_the_page_around_the_card([person for _, person in viewers])
        except AssertionError as failure:
            failure.add_note(f"the listed game {reckoning.id}")
            raise
    assert page_errors == []


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_a_watcher_who_opens_the_table_while_the_result_stands_reads_the_same_card_and_no_skat(
    deal_a_declared_table: Callable[..., DeclaringTable], page_errors: list[str], form_factor: dict[str, Any]
) -> None:
    table = deal_a_declared_table(form_factor)
    reckoning = next(each for each in RECKONINGS if each.id == "herz-hand-mit-1-won")
    table.list_the_game(replace(reckoning.entry, declarer_seat=table.declarer_seat))
    arriving = table.watcher.context.new_page()
    arriving.goto(table.watcher.url)
    expect(arriving.locator(".chair")).to_have_count(3)

    expect_the_reckoning(arriving, "watcher", table.name_of_the_declarer(), reckoning)
    for seat in table.sessions:
        assert "skat" not in json.dumps(table.result_as_sent(seat))
    assert page_errors == []
