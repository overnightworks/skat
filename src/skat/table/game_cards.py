from dataclasses import dataclass
from typing import TYPE_CHECKING

from skat.engine.cards import DECK
from skat.engine.deal import SEATS, positions_from, seats_from
from skat.engine.declaration import TakeSkat
from skat.engine.schieberamsch import Put
from skat.engine.tricks import PlayedOut

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.engine.ramsch import RamschPlayedOut
    from skat.engine.tricks import CompletedTrick
    from skat.table.records import TableRecord


@dataclass(frozen=True)
class SeatedCard:
    """A card and the seat it belongs to: the seat that played it, or that put it away."""

    seat: int
    card: Card


@dataclass(frozen=True)
class GameCards:
    """Every card of one finished game, by seat: the ten each seat was dealt, in deck order, the skat as dealt, the
    cards put away (a declarer's two, or each Schieberamsch seat's), in seat then deck order, and the
    tricks in the order played, each with its cards from the lead on. A trick an early end interrupted has fewer than
    three cards.
    """

    hands: tuple[tuple[Card, ...], tuple[Card, ...], tuple[Card, ...]]
    skat: tuple[Card, ...]
    put_away: tuple[SeatedCard, ...]
    tricks: tuple[tuple[SeatedCard, ...], ...]


def in_deck_order(cards: Iterable[Card]) -> tuple[Card, ...]:
    return tuple(sorted(cards, key=DECK.index))


def put_away_in_order(put_away: Iterable[SeatedCard]) -> tuple[SeatedCard, ...]:
    return tuple(sorted(put_away, key=lambda each: (each.seat, DECK.index(each.card))))


def _seat_after(leader: int, places: int) -> int:
    return SEATS[(SEATS.index(leader) + places) % len(SEATS)]


def _seated_trick(trick: CompletedTrick, seats: Mapping[Position, int]) -> tuple[SeatedCard, ...]:
    leader = seats[trick.leader]
    return tuple(SeatedCard(_seat_after(leader, place), card) for place, card in enumerate(trick.cards))


def _put_away_of(
    table: TableRecord, played: PlayedOut | RamschPlayedOut, seats: Mapping[Position, int]
) -> list[SeatedCard]:
    """What a Ramsch's stage put back, and what a declarer who took the skat put away."""
    puts = [
        SeatedCard(seats[step.position], card)
        for step in table.progress.pushing
        if isinstance(step, Put)
        for card in step.cards
    ]
    if isinstance(played, PlayedOut) and any(isinstance(step, TakeSkat) for step in table.progress.declaring):
        puts += [SeatedCard(seats[played.declared.declarer], card) for card in played.declared.skat]
    return puts


def game_cards_of(table: TableRecord, played: PlayedOut | RamschPlayedOut) -> GameCards:
    """The cards of the hand that ends with `played`, read before the table forgets its steps: the hands and the skat
    as dealt, whatever a Schieberamsch's takes and puts did to them, the engine's completed tricks, and the cards of a
    trick the end interrupted, which the table's steps hold beyond them.
    """
    deal = table.hand
    # A game is played only on a deal, and the store writes the dealer with the hand.
    if deal is None or table.dealer is None:  # pragma: no cover
        message = f"table {table.id.value} ended a game without a deal or a dealer"
        raise RuntimeError(message)
    positions, seats = positions_from(table.dealer), seats_from(table.dealer)
    first, second, third = (in_deck_order(deal.hands[positions[seat]]) for seat in SEATS)
    interrupted = tuple(
        SeatedCard(seats[play.position], play.card) for play in table.progress.plays[3 * len(played.tricks) :]
    )
    tricks = tuple(_seated_trick(trick, seats) for trick in played.tricks)
    return GameCards(
        hands=(first, second, third),
        skat=in_deck_order(deal.skat),
        put_away=put_away_in_order(_put_away_of(table, played, seats)),
        tricks=(*tricks, interrupted) if interrupted else tricks,
    )
