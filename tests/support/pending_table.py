from skat.engine.bock import BockRounds
from skat.table.records import (
    Actor,
    Chair,
    HandProgress,
    Occupant,
    TableId,
    TableOptions,
    TableRecord,
    TableStyle,
    Visibility,
)
from tests.support.played_game import an_entry

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")
TABLE_VERSION = 9


def pending(*ready_seats: int, games: int = 2) -> TableRecord:
    """Three seated after their `games`-th game: no hand, no steps, the dealer and the list; `ready_seats` tapped."""
    people = ((1, ANNA), (2, BEN), (3, CLEO))
    chairs = tuple(
        Chair(seat, Occupant(actor.account_id, actor.display_name, actor.kind), ready=seat in ready_seats)
        for seat, actor in people
    )
    return TableRecord(
        TableId("0" * 32),
        TABLE_VERSION,
        chairs,
        dealer=2,
        hand=None,
        progress=HandProgress(),
        game_list=tuple(an_entry() for _ in range(games)),
        series=None,
        options=TableOptions(),
        bock=BockRounds.start(),
        visibility=Visibility.OPEN,
        style=TableStyle.KLASSIK,
    )
