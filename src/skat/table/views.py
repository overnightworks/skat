from dataclasses import dataclass
from typing import TYPE_CHECKING

from skat.engine.bidding import PassedIn
from skat.engine.cards import DECK
from skat.engine.deal import next_dealer, positions_from
from skat.engine.ramsch import RamschPlaying
from skat.engine.tricks import Playing
from skat.table.auction import AuctionView, auction_view_of
from skat.table.bock import BockView, bock_view_of
from skat.table.declaring import DeclaringView, declaring_view_of
from skat.table.game_list import (
    RamschResultView,
    ResultView,
    Standing,
    reach_of,
    result_view_of,
    standings_of,
    total_of,
)
from skat.table.hand_state import auction_of, declaring_of, game_of
from skat.table.kontra import kontra_view_of
from skat.table.playing import PlayingView, playing_view_of
from skat.table.records import EndedTable, EndReason, OccupantKind
from skat.table.rules import hand_runs, series_over

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from skat.engine.cards import Card
    from skat.engine.deal import Deal, Position
    from skat.engine.declaration import Declaring
    from skat.table.records import Chair, EndProposal, TableOptions, TableRecord


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
    occupant_kind: OccupantKind | None
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
    ramsch: bool


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
    """Which game of how many the table runs, 0 before the first deal, and whether the series is over.

    The series is over once its last game is played or it ended early.
    Once it is over, `standings` ranks every account the list seated, the same for every viewer. Between two games
    `end_proposal` names the seats that proposed and accepted ending the series; once it is over none stands.
    """

    game_number: int
    game_count: int
    over: bool
    standings: tuple[Standing, ...] | None
    end_proposal: EndProposal | None


@dataclass(frozen=True)
class TableView:
    """A live table has no `ended`; an ended one has no chairs, watchers, hand, result, passed-in fact, series,
    options or Bock games. A live table without Bock has no `bock`.
    """

    id: str
    version: int
    chairs: tuple[ChairView, ...]
    watchers: int
    hand: HandView | None
    passed_in: PassedInView | None
    result: ResultView | RamschResultView | None
    series: SeriesView | None
    options: TableOptions | None
    bock: BockView | None
    ended: EndedView | None = None


def _is_occupied_by(chair: Chair, account_id: str) -> bool:
    return chair.occupant is not None and chair.occupant.account_id == account_id


def _hands_now(
    deal: Deal, state: Declaring | None, playing: Playing | RamschPlaying | None
) -> Mapping[Position, tuple[Card, ...]]:
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
    playing = game_of(table)
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
        playing_view_of(
            playing,
            table.dealer,
            viewer_positions,
            show_running_points=table.options.show_running_points,
            asked=table.progress.give_up,
            kontra=kontra_view_of(table, playing, table.dealer, viewer_positions)
            if isinstance(playing, Playing)
            else None,
        ),
        isinstance(playing, RamschPlaying),
    )
    return hand_view, {seat: ChairHand(position, len(hands[position])) for seat, position in positions.items()}


def _total_shown(table: TableRecord, chair: Chair) -> int | None:
    """No chair shows a total before its table's first result, except from a later series' first deal on, when every
    occupied chair shows 0 until that series' first result.
    """
    in_a_later_series = table.series is not None and table.series.number > 1
    if chair.occupant is None or not (table.game_list or in_a_later_series):
        return None
    return total_of(table.game_list, chair.occupant.account_id, reach_of(table.options))


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
    return SeriesView(
        table.series.deals,
        table.series.length,
        over,
        standings_of(table.game_list, reach_of(table.options)) if over else None,
        None if over else table.series.end_proposal,
    )


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
    carries the standings once it is. A table with Bock says how many Bock games are still to come and by what the
    running or next game's list score is multiplied.
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
            options=None,
            bock=None,
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
                occupant_kind=None if chair.occupant is None else chair.occupant.kind,
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
        options=table.options,
        bock=bock_view_of(table),
    )


@dataclass(frozen=True)
class PausedChairView:
    """A chair of a paused table: who sits there, whether it is the viewer's own and its running total."""

    seat: int
    occupant_name: str | None
    is_mine: bool
    total: int | None


@dataclass(frozen=True)
class PausedEntryView:
    """A table on which a hand was dealt, as its chair holder's start page lists it.

    The game number and length are None for a table without a series; `turn_seat` is the seat whose move the running
    hand waits for, None between hands, and `result_waits` says a played game's result stands. It names no card, no
    card count, no skat, no watcher and no account. `ends_at` is the instant the table ends, in UTC, and
    `opener_name` the name its opener had when he opened it, None for a table opened before the name was kept.
    """

    id: str
    chairs: tuple[PausedChairView, ...]
    game_number: int | None
    game_count: int | None
    turn_seat: int | None
    result_waits: bool
    ends_at: datetime
    opener_name: str | None


def turn_seat_of(hand: HandView | None) -> int | None:
    """The seat on turn: the playing turn while a game is played, the declarer while he declares, else the auction's."""
    if hand is None:
        return None
    if hand.playing is not None:
        return hand.playing.turn_seat
    if hand.declaring is not None:
        return hand.declaring.declarer_seat
    return hand.auction.turn_seat


def paused_entry_of(
    table: TableRecord, viewer_account_id: str, ends_at: datetime, opener_name: str | None
) -> PausedEntryView:
    """The table for the viewer as the paused list shows it, projected from the table view with nobody connected."""
    view = view_of(table, viewer_account_id, frozenset())
    return PausedEntryView(
        id=view.id,
        chairs=tuple(
            PausedChairView(chair.seat, chair.occupant_name, chair.is_mine, chair.total) for chair in view.chairs
        ),
        game_number=None if view.series is None else view.series.game_number,
        game_count=None if view.series is None else view.series.game_count,
        turn_seat=turn_seat_of(view.hand),
        result_waits=view.result is not None,
        ends_at=ends_at,
        opener_name=opener_name,
    )
