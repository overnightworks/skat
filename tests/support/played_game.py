from dataclasses import replace

from skat.engine.bidding import Bid, Pass
from skat.engine.bock import BockRounds
from skat.engine.cards import DECK
from skat.engine.deal import Deal, Position, positions_from
from skat.engine.declaration import Announcement, Declaration, Declare
from skat.engine.games import GameKind
from skat.engine.tricks import CardPlayed, play_card
from skat.engine.value import Matadors
from skat.table.game_list import ListEntry, RamschEntry
from skat.table.hand_state import playing_of
from skat.table.records import Chair, HandProgress, Occupant, OccupantKind, TableId, TableOptions, TableRecord

HERZ_HAND = Declare(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE)
ANNA_BEN_CLEO = ("account-anna", "account-ben", "account-cleo")


def declared_herz_hand() -> HandProgress:
    """The middlehand won at 18 and declared a Herz Hand game; forehand leads."""
    return HandProgress(
        auction=(Bid(Position.MIDDLEHAND, 18), Pass(Position.FOREHAND), Pass(Position.REARHAND)),
        declaring=(HERZ_HAND,),
    )


def table_in(progress: HandProgress, options: TableOptions | None = None) -> TableRecord:
    """Seat 2 deals: seat 3 is forehand, seat 1 middlehand and seat 2 rearhand, each on the account named by its
    position, in the hand of `progress`.
    """
    dealer = 2
    seats = {position: seat for seat, position in positions_from(dealer).items()}
    chairs = tuple(
        Chair(seats[position], Occupant(f"account-{position.name.lower()}", position.name, OccupantKind.PERSON))
        for position in (Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND)
    )
    deal = Deal(forehand=DECK[0:10], middlehand=DECK[10:20], rearhand=DECK[20:30], skat=DECK[30:32])
    return TableRecord(
        id=TableId("0123456789abcdef0123456789abcdef"),
        version=7,
        chairs=chairs,
        dealer=dealer,
        hand=deal,
        progress=progress,
        game_list=(),
        series=None,
        options=options or TableOptions(),
        bock=BockRounds.start(),
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
        kontra_word=None,
        bock_factor=1,
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


def a_ramsch_entry(
    seat_scores: tuple[int, int, int] = (-47, 0, 0), seat_accounts: tuple[str, str, str] = ANNA_BEN_CLEO
) -> RamschEntry:
    return RamschEntry(
        seat_accounts=seat_accounts,
        seat_names=("Anna", "Ben", "Cleo"),
        seat_points=(47, 40, 33),
        seat_scores=seat_scores,
        durchmarsch_seat=None,
        jungfrau=False,
    )
