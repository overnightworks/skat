from typing import TYPE_CHECKING

from skat.engine.kontra import Word
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from tests.e2e.support.declaring import command_numbers

if TYPE_CHECKING:
    from tests.e2e.support.hands import PlayingTable

KONTRA_OPTIONS = {"sayer": "any-opponent", "reach": "kontra-re", "deadline": "own-card"}


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
