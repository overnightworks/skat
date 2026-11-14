from typing import TYPE_CHECKING, ClassVar

from skat.engine.bidding import VALID_BIDS
from skat.engine.kontra import Word
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_HOLD_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from tests.e2e.support.declaring import DeclaringTable, command_numbers
from tests.e2e.support.raw_http import RawSession
from tests.e2e.support.tables import open_table_with_options

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Page

    from tests.e2e.support.hands import PlayingTable
    from tests.e2e.support.server import RunningServer
    from tests.support.signed_in import SeededMember

KONTRA_OPTIONS = {"sayer": "any-opponent", "reach": "kontra-re", "deadline": "own-card"}
# Only an opponent who bid says Kontra, and the declarer answers with Re.
BIDDERS_ONLY_OPTIONS = {"sayer": "bidders-only", "reach": "kontra-re", "deadline": "own-card"}
KEY = ".copy.kontra"
STAMP = ".callout"


class KontraTable(DeclaringTable):
    """A table opened through the API with Kontra and Re under `kontra_options`."""

    kontra_options: ClassVar[dict[str, str]] = BIDDERS_ONLY_OPTIONS

    def _open_table(
        self, opener: Page, server: RunningServer, member_of: Callable[[Page], SeededMember], *, running_points: bool
    ) -> str:
        assert not running_points
        return open_table_with_options(
            opener, server, RawSession(server, member_of(opener)), {"kontra": self.kontra_options}
        )


class ContestedTable(KontraTable):
    """The forehand holds at the first bid and drops out at the second; the rearhand passes at once."""

    def _win_the_auction(self, seat_at: dict[str, int]) -> None:
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[0])
        self.step(seat_at["forehand"], TABLE_AUCTION_HOLD_SUFFIX)
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[-1])
        self.step(seat_at["forehand"], TABLE_AUCTION_PASS_SUFFIX)
        self.step(seat_at["rearhand"], TABLE_AUCTION_PASS_SUFFIX)


class LeadingTable(KontraTable):
    """The forehand outbids the middlehand, so the declarer leads and the middlehand may say Kontra."""

    declarer_position = "forehand"

    def _win_the_auction(self, seat_at: dict[str, int]) -> None:
        self.step(seat_at["middlehand"], TABLE_AUCTION_BID_SUFFIX, value=VALID_BIDS[0])
        self.step(seat_at["forehand"], TABLE_AUCTION_HOLD_SUFFIX)
        self.step(seat_at["middlehand"], TABLE_AUCTION_PASS_SUFFIX)
        self.step(seat_at["rearhand"], TABLE_AUCTION_PASS_SUFFIX)


def expect_nothing_to_overflow(person: Page) -> None:
    assert person.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    viewport = person.viewport_size
    assert viewport is not None
    for part in person.locator(f"{KEY}, {STAMP}, .actions > *").all():
        box = part.bounding_box()
        assert box is not None
        assert box["x"] >= 0, box
        assert box["x"] + box["width"] <= viewport["width"], box


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
