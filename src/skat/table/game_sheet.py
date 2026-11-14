from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skat.engine.deal import SEATS, Position
from skat.engine.games import GameKind
from skat.engine.play import trick_winner
from skat.engine.ramsch import RamschPlayedOut, skat_takers
from skat.engine.tricks import TRICKS_IN_A_GAME, CompletedTrick
from skat.table.game_list import GameEnding, RamschEntry

if TYPE_CHECKING:
    from skat.engine.cards import Card
    from skat.engine.ramsch import RamschScoring
    from skat.table.game_cards import GameCards, SeatedCard
    from skat.table.game_list import GameEntry, ListEntry
    from skat.table.records import TableRecord

# A Ramsch's tricks name seats, and the engine's Ramsch rules name positions: any one-to-one pairing of the two
# answers the same question, which seats the skat counts for.
_POSITION_OF_SEAT: Final[dict[int, Position]] = dict(zip(SEATS, Position, strict=True))
_SEAT_OF_POSITION: Final = {position: seat for seat, position in _POSITION_OF_SEAT.items()}


class CardState(StrEnum):
    """What became of a card a seat held when the game started."""

    PLAYED = "played"
    PUT_AWAY = "put-away"
    UNPLAYED = "unplayed"


@dataclass(frozen=True)
class SheetCard:
    card: Card
    state: CardState


@dataclass(frozen=True)
class SheetHand:
    """One seat's cards as the game started, each with what became of it."""

    seat: int
    cards: tuple[SheetCard, ...]


@dataclass(frozen=True)
class SheetTrick:
    """One trick in the order played: its cards from the lead on, and who took it and with how many card points, both
    None for a trick the end of the game interrupted.
    """

    number: int
    cards: tuple[SeatedCard, ...]
    taker_seat: int | None
    points: int | None


@dataclass(frozen=True)
class SheetCards:
    """Every card of a game: the hands, the skat as it lay, what each seat put away and the tricks; `skat_takers` are
    the seats a Ramsch's skat counted for, none for a declared game.
    """

    hands: tuple[SheetHand, ...]
    skat: tuple[Card, ...]
    put_away: tuple[SeatedCard, ...]
    tricks: tuple[SheetTrick, ...]
    skat_takers: tuple[int, ...]


@dataclass(frozen=True)
class DeclaredCount:
    """What a declared game counted: the card points of the declarer against the two opponents' and how it ended."""

    declarer_seat: int
    declarer_points: int
    opponents_points: int
    ending: GameEnding
    ended_by_seat: int | None


@dataclass(frozen=True)
class RamschCount:
    """What a Ramsch counted: the card points of each seat, by seat, and the seat that took all ten tricks."""

    seat_points: tuple[int, int, int]
    durchmarsch_seat: int | None


@dataclass(frozen=True)
class GameSheetView:
    """One game of the table's current series opened from its list, the same for every viewer; `seat_names` are the
    names stored with the game (None for a game stored before names were kept), and `cards` is None for a game
    finished before games kept their cards.
    """

    number: int
    seat_names: tuple[str | None, str | None, str | None]
    count: DeclaredCount | RamschCount
    cards: SheetCards | None


def _taker_of(trick: tuple[SeatedCard, ...], kind: GameKind) -> int | None:
    if len(trick) < len(SEATS):
        return None
    first, second, third = (each.card for each in trick)
    return trick[trick_winner((first, second, third), kind)].seat


def _skat_takers_of(tricks: tuple[SheetTrick, ...], skat: tuple[Card, ...], scoring: RamschScoring) -> tuple[int, ...]:
    completed = tuple(
        CompletedTrick(
            _POSITION_OF_SEAT[trick.cards[0].seat],
            (trick.cards[0].card, trick.cards[1].card, trick.cards[2].card),
            _POSITION_OF_SEAT[trick.taker_seat],
        )
        for trick in tricks
        if trick.taker_seat is not None
    )
    takers = skat_takers(RamschPlayedOut(completed, skat), scoring)
    return tuple(sorted(_SEAT_OF_POSITION[position] for position in takers))


def _hand_of(seat: int, cards: GameCards, played: set[tuple[int, Card]], put_away: set[tuple[int, Card]]) -> SheetHand:
    def state_of(card: Card) -> CardState:
        if (seat, card) in played:
            return CardState.PLAYED
        return CardState.PUT_AWAY if (seat, card) in put_away else CardState.UNPLAYED

    return SheetHand(seat, tuple(SheetCard(card, state_of(card)) for card in cards.hands[seat - 1]))


def _points_played(declarer_seat: int, cards: SheetCards) -> tuple[int, int]:
    """The card points of the declarer and of the opponents counted over the cards played: the tricks each took and the
    cards the declarer put away.
    """
    taken = [(trick.taker_seat == declarer_seat, trick.points) for trick in cards.tricks if trick.points is not None]
    put_away = sum(each.card.points for each in cards.put_away)
    return (
        put_away + sum(points for by_declarer, points in taken if by_declarer),
        sum(points for by_declarer, points in taken if not by_declarer),
    )


def _declared_count_of(entry: ListEntry, cards: SheetCards | None) -> DeclaredCount:
    """The points a declared game counted; a game that ended before its tenth trick was taken counts only what was
    played, whatever the points the ending settled it by.
    """
    declarer_points, opponents_points = entry.declarer_points, entry.opponents_points
    if cards is not None and sum(trick.points is not None for trick in cards.tricks) < TRICKS_IN_A_GAME:
        declarer_points, opponents_points = _points_played(entry.declarer_seat, cards)
    return DeclaredCount(
        declarer_seat=entry.declarer_seat,
        declarer_points=declarer_points,
        opponents_points=opponents_points,
        ending=entry.ending,
        ended_by_seat=entry.ended_by_seat,
    )


def _count_of(entry: GameEntry, cards: SheetCards | None) -> DeclaredCount | RamschCount:
    if isinstance(entry, RamschEntry):
        return RamschCount(entry.seat_points, entry.durchmarsch_seat)
    return _declared_count_of(entry, cards)


def _sheet_cards_of(table: TableRecord, entry: GameEntry, cards: GameCards) -> SheetCards:
    kind = GameKind.GRAND if isinstance(entry, RamschEntry) else entry.declaration.kind
    tricks = tuple(
        SheetTrick(
            number,
            trick,
            _taker_of(trick, kind),
            None if len(trick) < len(SEATS) else sum(each.card.points for each in trick),
        )
        for number, trick in enumerate(cards.tricks, start=1)
    )
    played = {(each.seat, each.card) for trick in cards.tricks for each in trick}
    put_away = {(each.seat, each.card) for each in cards.put_away}
    ramsch = table.options.ramsch
    # A Ramsch is stored only at a table that plays one, and its options never change.
    if isinstance(entry, RamschEntry) and ramsch is None:  # pragma: no cover
        message = f"table {table.id.value} lists a Ramsch without playing one"
        raise RuntimeError(message)
    takers = (
        _skat_takers_of(tricks, cards.skat, ramsch.reckoning.scoring)
        if isinstance(entry, RamschEntry) and ramsch is not None
        else ()
    )
    return SheetCards(
        hands=tuple(_hand_of(seat, cards, played, put_away) for seat in SEATS),
        skat=cards.skat,
        put_away=cards.put_away,
        tricks=tricks,
        skat_takers=takers,
    )


def game_sheet_of(table: TableRecord, number: int, cards: GameCards | None) -> GameSheetView:
    """The `number`th game of the table's list with its stored `cards`; each trick's taker comes from the engine's rule
    for the game's kind, a Ramsch's as Grand.
    """
    entry = table.game_list[number - 1]
    sheet_cards = None if cards is None else _sheet_cards_of(table, entry, cards)
    return GameSheetView(
        number=number, seat_names=entry.seat_names, count=_count_of(entry, sheet_cards), cards=sheet_cards
    )
