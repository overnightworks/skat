import json
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Locator, Page, expect

from skat.engine.declaration import Announcement, Declaration
from skat.engine.games import GameKind
from skat.engine.value import Matadors
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DeclaringTable
from tests.e2e.support.hands import THEY, WE
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.result_card import (
    CARD,
    LOST,
    MINUS,
    OVERBID,
    TIMES,
    WON,
    YOU,
    expect_the_page_around_the_card,
    loosely,
)
from tests.e2e.support.server import skat_on_new_database
from tests.support.played_game import an_entry

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from skat.table.game_list import ListEntry
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

HAND = text(SOURCE_LANGUAGE, "result.hand")
SCHNEIDER = text(SOURCE_LANGUAGE, "result.levelSchneider")
SCHWARZ = text(SOURCE_LANGUAGE, "result.levelSchwarz")
OUVERT_CHIP = text(SOURCE_LANGUAGE, "result.levelOuvert")
SCHNEIDER_ANNOUNCED = text(SOURCE_LANGUAGE, "result.announcedSchneider")
SCHWARZ_ANNOUNCED = text(SOURCE_LANGUAGE, "result.announcedSchwarz")
SPIEL = text(SOURCE_LANGUAGE, "result.levelSpiel")
GAME_KARO = text(SOURCE_LANGUAGE, "game.karo")
GAME_HERZ = text(SOURCE_LANGUAGE, "game.herz")
GAME_KREUZ = text(SOURCE_LANGUAGE, "game.kreuz")
GAME_GRAND = text(SOURCE_LANGUAGE, "game.grand")
GAME_NULL = text(SOURCE_LANGUAGE, "game.null")


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
    return (
        text(SOURCE_LANGUAGE, "result.listGame", score=score),
        text(SOURCE_LANGUAGE, "result.listBonus", bonus=bonus),
        f"= {gain}",
    )


def matadors_chip(mit: bool, count: int) -> str:
    return text(SOURCE_LANGUAGE, "result.matadorsWith" if mit else "result.matadorsWithout", count=count)


# The unticked chip of the matadors, in both its forms and the counts the listed games use.
MATADORS_CHIPS = {matadors_chip(mit, count) for mit in (True, False) for count in (1, 2)}


MIT_2 = Matadors(mit=True, count=2)
MIT_1 = Matadors(mit=True, count=1)
KREUZ_MIT_2 = (matadors_chip(True, 2), SPIEL)
HERZ_HAND_MIT_1 = (matadors_chip(True, 1), SPIEL, HAND)
HERZ_HAND_SCHNEIDER = (*HERZ_HAND_MIT_1, SCHNEIDER, SCHNEIDER_ANNOUNCED)
GRAND_HAND_SCHWARZ = (*HERZ_HAND_SCHNEIDER, SCHWARZ, SCHWARZ_ANNOUNCED)
GRAND_OUVERT_CHIPS = (*GRAND_HAND_SCHWARZ, OUVERT_CHIP)
GRAND_OUVERT_WORDS = text(SOURCE_LANGUAGE, "game.ouvertName", game=GAME_GRAND)
NULL_OUVERT_HAND_WORDS = text(SOURCE_LANGUAGE, "game.ouvertHandName", game=GAME_NULL)
NULL_HAND_WORDS = text(SOURCE_LANGUAGE, "game.handName", game=GAME_NULL)
HERZ_HAND_WORDS = text(SOURCE_LANGUAGE, "game.handName", game=GAME_HERZ)
GRAND_HAND_WORDS = text(SOURCE_LANGUAGE, "game.handName", game=GAME_GRAND)
SCHNEIDER_MISSED = text(SOURCE_LANGUAGE, "result.missedSchneider")
SCHWARZ_MISSED = text(SOURCE_LANGUAGE, "result.missedSchwarz")
LOST_GAME_SHARE = "+40"
STORE_READ_SECONDS = 0.1

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
        (matadors_chip(True, 1), SPIEL),
        ("2", TIMES, "9", "=", "18"),
        f"{MINUS}54",
        steps_of(f"{MINUS}54", f"{MINUS}50", f"{MINUS}104"),
        LOST_GAME_SHARE,
        raised=text(SOURCE_LANGUAGE, "result.raise", value="18", bid="20", settled="27"),
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
        NULL_HAND_WORDS,
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
        (matadors_chip(False, 2), SPIEL),
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
        HERZ_HAND_WORDS,
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
        HERZ_HAND_WORDS,
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
        HERZ_HAND_WORDS,
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
        GRAND_HAND_WORDS,
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
        HERZ_HAND_WORDS,
        HERZ_HAND_SCHNEIDER,
        ("5", TIMES, "10", "=", "50"),
        f"{MINUS}120",
        steps_of(f"{MINUS}120", f"{MINUS}50", f"{MINUS}170"),
        LOST_GAME_SHARE,
        raised=text(SOURCE_LANGUAGE, "result.raise", value="50", bid="60", settled="60"),
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


def expect_the_ticks_drawn(card: Locator, ticked: int) -> None:
    """Every counted level carries a tick drawn as an outline, not the browser's default black fill."""
    ticks = card.locator(".ladder .held svg path")
    expect(ticks).to_have_count(ticked)
    for index in range(ticked):
        expect(ticks.nth(index)).to_have_css("fill", "none")
        expect(ticks.nth(index)).to_have_css("stroke", re.compile(r"^rgb"))


def expect_one_pill_per_chip(card: Locator) -> None:
    """A chip is a single pill: its word draws no box of its own and keeps the chip's colour."""
    chips = card.locator(".ladder > *")
    for index in range(chips.count()):
        word = chips.nth(index).locator("span")
        expect(word).to_have_css("background-color", "rgba(0, 0, 0, 0)")
        expect(word).to_have_css("padding", "0px")
        expect(word).to_have_css("color", chips.nth(index).evaluate("chip => getComputedStyle(chip).color"))


def expect_the_ladder(card: Locator, reckoning: Reckoning) -> None:
    if reckoning.chips:
        expect(card.locator(".ladder > *")).to_have_text(list(reckoning.chips))
        expect_one_pill_per_chip(card)
        expect_the_ticks_drawn(card, sum(chip not in MATADORS_CHIPS for chip in reckoning.chips))
    else:
        expect(card.locator(".ladder")).to_have_count(0)


def expect_the_equation(card: Locator, reckoning: Reckoning) -> None:
    if reckoning.equation is None:
        expect(card.locator(".eq")).to_have_count(0)
    else:
        expect(card.locator(".eq")).to_have_text(loosely(*reckoning.equation))


def expect_the_overbid_and_miss(card: Locator, reckoning: Reckoning) -> None:
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


def expect_the_reckoning(person: Page, role: str, declarer_name: str, declarer_seat: int, reckoning: Reckoning) -> None:
    """One viewer's card for a listed game: the parts the ISkO value rules make of it, from the viewer's side."""
    entry = reckoning.entry
    card = person.locator(CARD)
    expect(card).to_have_count(1)
    declarer_side, opponents_side = {
        "declarer": (YOU, THEY),
        "opponent": (declarer_name, WE),
        "watcher": (declarer_name, THEY),
    }[role]
    steps = [declarer_side, *reckoning.steps]
    if not entry.won:
        steps.append(text(SOURCE_LANGUAGE, "result.share", opponents=opponents_side, gain=reckoning.opponent_gain))
    # The steps differ between two listed games in a row, so once they stand the page shows this game's card and no
    # earlier one, and every other part is read from it.
    expect(card.locator(".list")).to_have_text(loosely(*steps))
    if role == "watcher":
        heading = text(
            SOURCE_LANGUAGE,
            "result.declarerWins" if entry.won else "result.declarerLoses",
            name=declarer_name,
        )
    else:
        heading = WON if entry.won == (role == "declarer") else LOST
    expect(card.locator("h3")).to_have_text(heading)
    game = (
        text(SOURCE_LANGUAGE, "result.opponentGameLine", declarer=declarer_name, game=reckoning.game)
        if role == "opponent"
        else reckoning.game
    )
    expect(card.locator(".sub .game")).to_have_text(game)
    expect_the_ladder(card, reckoning)
    expect_the_equation(card, reckoning)
    expect_the_overbid_and_miss(card, reckoning)
    expect(card.locator(".x2")).to_have_count(0 if entry.won else 1)
    expect(card.locator(".value")).to_have_text(reckoning.value)
    expect(card.locator(".points")).to_have_count(1 if reckoning.points else 0)
    for seat in (1, 2, 3):
        row = card.locator(f".reck[data-seat='{seat}']")
        declares = seat == declarer_seat
        expect(row.locator(".dl")).to_have_text(
            reckoning.steps[2].removeprefix("= ") if declares else reckoning.opponent_gain
        )
        expect(row).to_have_class(re.compile(r"\bwin\b" if entry.won == declares else r"^(?!.*\bwin\b)"))


@pytest.fixture
def e2e_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningServer]:
    """A Skat whose streams read the table again every tenth of a second, so a game listed through the store reaches the
    open pages without a reload.
    """
    with skat_on_new_database(tmp_path_factory, heartbeat_seconds=STORE_READ_SECONDS) as server:
        yield server


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
                expect_the_reckoning(person, role, declarer_name, table.declarer_seat, reckoning)
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
    reckoning = next(each for each in RECKONINGS if each.id == "schneider-announced-and-missed")
    table.list_the_game(replace(reckoning.entry, declarer_seat=table.declarer_seat))
    arriving = table.watcher.context.new_page()
    arriving.goto(table.watcher.url)
    expect(arriving.locator(".chair")).to_have_count(3)

    expect_the_reckoning(arriving, "watcher", table.name_of_the_declarer(), table.declarer_seat, reckoning)
    for seat in table.sessions:
        assert "skat" not in json.dumps(table.result_as_sent(seat))
    assert page_errors == []
