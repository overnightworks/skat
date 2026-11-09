from dataclasses import dataclass
from typing import TYPE_CHECKING

from skat.engine.bidding import PassedIn
from skat.engine.cards import DECK
from skat.engine.deal import next_dealer, positions_from
from skat.table.auction import AuctionView, auction_view_of
from skat.table.declaring import DeclaringView, declaring_view_of
from skat.table.game_list import ResultView, Standing, result_view_of, standings_of, total_of
from skat.table.hand_state import auction_of, declaring_of, playing_of
from skat.table.playing import PlayingView, playing_view_of
from skat.table.records import EndedTable, EndReason
from skat.table.rules import hand_runs, series_over

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skat.engine.cards import Card
    from skat.engine.deal import Deal, Position
    from skat.engine.declaration import Declaring
    from skat.engine.tricks import Playing
    from skat.table.records import Chair, TableRecord


@dataclass(frozen=True)
class ChairHand:
    """A chair's part of the running hand: where it sits in the order of play and how many cards it holds."""

    position: Position
    card_count: int


@dataclass(frozen=True)
class ChairView:
    """A chair as one viewer sees it; `ready` says its occupant is ready for the next hand,
    by a tap of „Weiter“ or by sitting down while a result is pending, the same for every viewer."""

    seat: int
    occupant_name: str | None
    is_mine: bool
    is_away: bool
    ready: bool
    hand: ChairHand | None
    total: int | None


@dataclass(frozen=True)
class HandView:
    """The running hand as one viewer may see it: the dealer, their own cards in deck order, the skat's count."""

    dealer_seat: int
    own_cards: tuple[Card, ...]
    skat_count: int
    auction: AuctionView
    declaring: DeclaringView | None
    playing: PlayingView | None


@dataclass(frozen=True)
class PassedInView:
    """The hand was passed in: who deals next, named only while three chairs are occupied and the series goes on."""

    next_dealer_seat: int | None


@dataclass(frozen=True)
class EndedView:
    """Why the table ended and, for an empty one, the whole seconds nobody was there."""

    reason: EndReason
    empty_seconds: int


@dataclass(frozen=True)
class SeriesView:
    """Which game of how many the table runs, 0 before the first deal, and whether its last game is over.

    Once it is over, `standings` ranks every account the list seated, the same for every viewer.
    """

    game_number: int
    game_count: int
    over: bool
    standings: tuple[Standing, ...] | None


@dataclass(frozen=True)
class TableView:
    """A live table has no `ended`; an ended one has no chairs, watchers, hand, result, passed-in fact or series."""

    id: str
    version: int
    chairs: tuple[ChairView, ...]
    watchers: int
    hand: HandView | None
    passed_in: PassedInView | None
    result: ResultView | None
    series: SeriesView | None
    ended: EndedView | None = None


def _is_occupied_by(chair: Chair, account_id: str) -> bool:
    return chair.occupant is not None and chair.occupant.account_id == account_id


def _hands_now(deal: Deal, state: Declaring | None, playing: Playing | None) -> Mapping[Position, tuple[Card, ...]]:
    """Each position's cards now: what is left in play, the declarer's own while declaring, else the deal."""
    if playing is not None:
        return playing.hands
    if state is not None:
        return {**deal.hands, state.declarer: state.hand}
    return deal.hands


def _hand_views(table: TableRecord, viewer_account_id: str) -> tuple[HandView | None, dict[int, ChairHand]]:
    """The hand view and each seat's part of it; both are empty while no hand runs."""
    if table.hand is None:
        return None, {}
    # The store writes the dealer with the hand, so a hand without a dealer is a wiring fault.
    if table.dealer is None:  # pragma: no cover
        message = f"table {table.id.value} holds a hand and no dealer"
        raise RuntimeError(message)
    positions = positions_from(table.dealer)
    state = declaring_of(table)
    playing = playing_of(table)
    hands = _hands_now(table.hand, state, playing)
    viewer_positions = frozenset(
        positions[chair.seat] for chair in table.chairs if _is_occupied_by(chair, viewer_account_id)
    )
    own_cards = {card for position in viewer_positions for card in hands[position]}
    hand_view = HandView(
        table.dealer,
        tuple(card for card in DECK if card in own_cards),
        len(table.hand.skat if state is None else state.skat),
        auction_view_of(table, viewer_account_id, table.dealer),
        declaring_view_of(state, table.dealer, () if state is None else hands[state.declarer]),
        playing_view_of(playing, table.dealer, viewer_positions),
    )
    return hand_view, {seat: ChairHand(position, len(hands[position])) for seat, position in positions.items()}


def _total_shown(table: TableRecord, chair: Chair) -> int | None:
    """No chair shows a total until the table's first result."""
    if chair.occupant is None or not table.game_list:
        return None
    return total_of(table.game_list, chair.occupant.account_id)


def _passed_in_view(table: TableRecord) -> PassedInView | None:
    """What the stored steps say between hands: set only while no hand runs and the steps ended in three passes."""
    if hand_runs(table) or table.dealer is None or not isinstance(auction_of(table).result, PassedIn):
        return None
    three_seated = all(chair.occupant is not None for chair in table.chairs)
    return PassedInView(next_dealer(table.dealer) if three_seated and not series_over(table) else None)


def _series_view(table: TableRecord) -> SeriesView | None:
    if table.series is None:
        return None
    over = series_over(table)
    return SeriesView(table.series.deals, table.series.length, over, standings_of(table.game_list) if over else None)


def view_of(table: TableRecord | EndedTable, viewer_account_id: str, connected_accounts: frozenset[str]) -> TableView:
    """The table as one account sees it: only the viewer's own chair is marked mine.

    The watchers are the connected accounts without a chair, each counted once. A chair is away when its occupant
    is not the viewer and has no connected stream; nothing is stored for it. While a hand runs, every chair shows
    its position and card count, and only the viewer's own cards are named: the declarer's hold the skat from the
    take to the put-back, and an ouvert game's cards are open to all. The skat is otherwise a count. While a game
    is played, the cards and counts are those still held, and played cards are shown only in the trick in progress
    and the last completed one. Between hands the view says whether the last hand was passed in and, while three
    chairs are occupied and the series goes on, who deals next; after a played game it carries the result, the same
    for every viewer. A table with a series says which game of how many runs and whether the series is over, and
    carries the standings once it is.
    An ended table names nobody and holds nothing of a hand.
    """
    if isinstance(table, EndedTable):
        return TableView(
            id=table.id.value,
            version=table.version,
            chairs=(),
            watchers=0,
            hand=None,
            passed_in=None,
            result=None,
            series=None,
            ended=EndedView(table.reason, table.empty_seconds),
        )
    seated = {chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}
    hand_view, chair_hands = _hand_views(table, viewer_account_id)
    return TableView(
        id=table.id.value,
        version=table.version,
        watchers=len(connected_accounts - seated),
        chairs=tuple(
            ChairView(
                seat=chair.seat,
                occupant_name=None if chair.occupant is None else chair.occupant.display_name,
                is_mine=_is_occupied_by(chair, viewer_account_id),
                is_away=chair.occupant is not None
                and chair.occupant.account_id != viewer_account_id
                and chair.occupant.account_id not in connected_accounts,
                ready=chair.ready,
                hand=chair_hands.get(chair.seat),
                total=_total_shown(table, chair),
            )
            for chair in table.chairs
        ),
        hand=hand_view,
        passed_in=_passed_in_view(table),
        result=result_view_of(table),
        series=_series_view(table),
    )
