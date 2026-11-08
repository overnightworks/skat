from dataclasses import dataclass
from typing import TYPE_CHECKING

from skat.engine.cards import DECK
from skat.engine.deal import positions_from

if TYPE_CHECKING:
    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.table.records import Chair, TableRecord


@dataclass(frozen=True)
class ChairHand:
    """A chair's part of the running hand: where it sits in the order of play and how many cards it holds."""

    position: Position
    card_count: int


@dataclass(frozen=True)
class ChairView:
    seat: int
    occupant_name: str | None
    is_mine: bool
    is_away: bool
    hand: ChairHand | None


@dataclass(frozen=True)
class HandView:
    """The running hand as one viewer may see it: the dealer, their own cards in deck order, the skat's count."""

    dealer_seat: int
    own_cards: tuple[Card, ...]
    skat_count: int


@dataclass(frozen=True)
class TableView:
    id: str
    version: int
    chairs: tuple[ChairView, ...]
    watchers: int
    hand: HandView | None


def _is_occupied_by(chair: Chair, account_id: str) -> bool:
    return chair.occupant is not None and chair.occupant.account_id == account_id


def _hand_views(table: TableRecord, viewer_account_id: str) -> tuple[HandView | None, dict[int, ChairHand]]:
    """The hand view and each seat's part of it; both are empty while no hand runs."""
    if table.hand is None:
        return None, {}
    # The store writes the dealer with the hand, so a hand without a dealer is a wiring fault.
    if table.dealer is None:  # pragma: no cover
        message = f"table {table.id.value} holds a hand and no dealer"
        raise RuntimeError(message)
    positions = positions_from(table.dealer)
    hands = table.hand.hands
    own_cards = {
        card
        for chair in table.chairs
        if _is_occupied_by(chair, viewer_account_id)
        for card in hands[positions[chair.seat]]
    }
    hand_view = HandView(table.dealer, tuple(card for card in DECK if card in own_cards), len(table.hand.skat))
    return hand_view, {seat: ChairHand(position, len(hands[position])) for seat, position in positions.items()}


def view_of(table: TableRecord, viewer_account_id: str, connected_accounts: frozenset[str]) -> TableView:
    """The table as one account sees it: only the viewer's own chair is marked mine.

    The watchers are the connected accounts without a chair, each counted once. A chair is away when its occupant
    is not the viewer and has no connected stream; nothing is stored for it. While a hand runs, every chair shows
    its position and card count, and only the viewer's own cards are named; the skat is a count.
    """
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
                hand=chair_hands.get(chair.seat),
            )
            for chair in table.chairs
        ),
        hand=hand_view,
    )
