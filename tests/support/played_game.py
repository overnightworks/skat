from dataclasses import replace

from skat.engine.bidding import Bid, Pass
from skat.engine.cards import DECK
from skat.engine.deal import Position
from skat.engine.declaration import Announcement, Declaration, Declare
from skat.engine.games import GameKind
from skat.engine.tricks import CardPlayed, play_card
from skat.engine.value import Matadors
from skat.table.game_list import ListEntry
from skat.table.hand_state import playing_of
from skat.table.records import HandProgress, TableRecord

HERZ_HAND = Declare(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE)
ANNA_BEN_CLEO = ("account-anna", "account-ben", "account-cleo")


def declared_herz_hand() -> HandProgress:
    """The middlehand won at 18 and declared a Herz Hand game; forehand leads."""
    return HandProgress(
        auction=(Bid(Position.MIDDLEHAND, 18), Pass(Position.FOREHAND), Pass(Position.REARHAND)),
        declaring=(HERZ_HAND,),
    )


def a_whole_game(table: TableRecord) -> tuple[CardPlayed, ...]:
    """All thirty cards, each the first in deck order the engine accepts from the player on turn."""
    state = playing_of(table)
    plays = []
    while state.result is None:
        position = state.turn
        accepted = next(
            each for each in DECK if each in state.hands[position] and play_card(state, position, each).refusal is None
        )
        state = play_card(state, position, accepted).state
        plays.append(CardPlayed(position, accepted))
    return tuple(plays)


def before_the_last_card(table: TableRecord) -> tuple[TableRecord, CardPlayed]:
    """The table declared as a Herz Hand game and holding every card but the last, and that last card."""
    declared = replace(table, progress=declared_herz_hand())
    plays = a_whole_game(declared)
    return replace(declared, progress=replace(declared.progress, plays=plays[:-1])), plays[-1]


def an_entry(seat_accounts: tuple[str, str, str] = ANNA_BEN_CLEO) -> ListEntry:
    return ListEntry(
        seat_accounts=seat_accounts,
        seat_names=("Anna", "Ben", "Cleo"),
        declarer_seat=1,
        declaration=Declaration(GameKind.KREUZ, hand=False, ouvert=False, announcement=Announcement.NONE),
        schneider=False,
        schwarz=False,
        matadors=Matadors(mit=True, count=2),
        won=True,
        bid=18,
        game_value=36,
        settled_value=36,
        score=36,
        declarer_points=78,
    )


def after_a_game(record: TableRecord, entry: ListEntry, *ready_seats: int) -> TableRecord:
    """The seated table as a game's last card leaves it: `entry` seated at the table's chairs ends its list."""
    seat_accounts = tuple(chair.occupant.account_id for chair in record.chairs)
    chairs = tuple(replace(chair, ready=chair.seat in ready_seats) for chair in record.chairs)
    listed = replace(entry, seat_accounts=seat_accounts)
    return replace(record, chairs=chairs, hand=None, progress=HandProgress(), game_list=(*record.game_list, listed))


def after_the_first_game(record: TableRecord, *ready_seats: int) -> TableRecord:
    """The seated table as the thirtieth card leaves it, with `ready_seats` having tapped „Weiter“."""
    return after_a_game(replace(record, game_list=()), an_entry(), *ready_seats)
