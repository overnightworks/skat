import json
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import Page, expect

from skat.engine.kontra import Word
from skat.engine.tricks import CARDS_IN_A_GAME
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from skat.web.tables import TABLE_PAGE_PREFIX, TABLES_PATH
from skat.web.words import SOURCE_LANGUAGE, text
from tests.e2e.support.declaring import DeclaringTable, command_numbers
from tests.e2e.support.hands import PlayingTable, deal_playing_table
from tests.e2e.support.people import WIDTHS
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.result_card import CARD, MINUS, expect_the_page_around_the_card
from tests.e2e.support.tables import TABLE_URL

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

pytestmark = pytest.mark.e2e

KONTRA_OPTIONS = {"sayer": "any-opponent", "reach": "kontra-re", "deadline": "own-card"}
SERIES_LENGTH = 36


class KontraTable(DeclaringTable):
    """A table opened through the API with Kontra and Re, whose opener sits in chair 1."""

    @staticmethod
    def _open_table(opener: Page, server: RunningServer, member_of: Callable[[Page], SeededMember]) -> str:
        body = {
            "command_id": f"kontra-result-create-{next(command_numbers):04d}",
            "series_length": SERIES_LENGTH,
            "options": {"kontra": KONTRA_OPTIONS},
        }
        opened = json.loads(RawSession(server, member_of(opener)).post(TABLES_PATH, body))
        path = f"{TABLE_PAGE_PREFIX}{opened['id']}"
        opener.goto(f"{server.base_url}{path}")
        expect(opener).to_have_url(TABLE_URL)
        return path


def signed(number: int) -> str:
    return f"{MINUS}{-number}" if number < 0 else f"+{number}"


def say_kontra_as_an_opponent(table: PlayingTable) -> None:
    seat = table.seat_at["forehand"]
    view = table.view(seat)
    assert view["hand"]["playing"]["kontra"]["my_word"] == Word.KONTRA
    body = {
        "command_id": f"kontra-result-word-{next(command_numbers):04d}",
        "version": view["version"],
        "word": "kontra",
    }
    table.declaring.sessions[seat].post(f"{table.declaring.api_path}{TABLE_KONTRA_SUFFIX}", body)
    assert table.playing()["kontra"]["factor"] == Word.KONTRA.factor


@pytest.mark.parametrize("form_factor", WIDTHS)
def test_every_viewers_card_draws_the_kontra_word_and_the_score_the_answer_counted(
    open_person: Callable[..., Page],
    e2e_server: RunningServer,
    member_of: Callable[[Page], SeededMember],
    page_errors: list[str],
    form_factor: dict[str, Any],
) -> None:
    table = deal_playing_table(open_person, e2e_server, member_of, page_errors, form_factor, declaring=KontraTable)
    say_kontra_as_an_opponent(table)
    table.play_out(CARDS_IN_A_GAME)

    result = table.result()
    assert result["kontra"] == {"word": Word.KONTRA, "factor": Word.KONTRA.factor}
    doubled_by_loss = 1 if result["won"] else 2
    assert abs(result["score"]) == result["settled_value"] * doubled_by_loss * Word.KONTRA.factor
    chip = text(
        SOURCE_LANGUAGE,
        "result.wordFactor",
        word=text(SOURCE_LANGUAGE, "result.wordKontra"),
        factor=str(Word.KONTRA.factor),
    )
    game_step = text(
        SOURCE_LANGUAGE,
        "result.listGameWord",
        word=text(SOURCE_LANGUAGE, "result.wordKontra"),
        score=signed(result["score"]),
    )
    for person in table.everyone:
        card = person.locator(CARD)
        expect(card.locator(".ladder").nth(1)).to_have_text(chip)
        expect(card.locator(".value")).to_have_text(signed(result["score"]))
        expect(card.locator(".list")).to_contain_text(game_step)
    expect_the_page_around_the_card(table.everyone)
    assert page_errors == []
