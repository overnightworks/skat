import json
from dataclasses import replace
from typing import TYPE_CHECKING

from skat.engine.cards import DECK
from skat.engine.deal import Deal
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS

if TYPE_CHECKING:
    from collections.abc import Iterable

    from skat.engine.cards import Card

SUIT_WORDS = frozenset(SUIT_TOKENS.values())
RANK_WORDS = frozenset(RANK_TOKENS.values())

# Dealt by position out of the deck's order: seat 2 dealt, so seat 3 holds the forehand, seat 1 the middlehand.
DEALER_SEAT = 2
FOREHAND_CARDS = DECK[0:10]
MIDDLEHAND_CARDS = DECK[10:20]
REARHAND_CARDS = DECK[20:30]
SKAT_CARDS = DECK[30:32]
KNOWN_DEAL = Deal(forehand=FOREHAND_CARDS, middlehand=MIDDLEHAND_CARDS, rearhand=REARHAND_CARDS, skat=SKAT_CARDS)
CARDS_BY_SEAT = {1: MIDDLEHAND_CARDS, 2: REARHAND_CARDS, 3: FOREHAND_CARDS}


def wire_cards(cards: Iterable[Card]) -> set[tuple[str, str]]:
    return {(SUIT_TOKENS[card.suit], RANK_TOKENS[card.rank]) for card in cards}


def cards_in(body: object) -> set[tuple[str, str]]:
    """Every card in a decoded JSON tree: any object holding a suit token and a rank token, wherever it sits."""
    if isinstance(body, dict):
        values = list(body.values())
        suits = {value for value in values if isinstance(value, str) and value in SUIT_WORDS}
        ranks = {value for value in values if isinstance(value, str) and value in RANK_WORDS}
        found = {(suit, rank) for suit in suits for rank in ranks}
        children: list[object] = values
    elif isinstance(body, list):
        found = set()
        children = list(body)
    else:
        return set()
    for child in children:
        found |= cards_in(child)
    return found


def cards_in_text(text: str) -> set[tuple[str, str]]:
    """Every card in a raw HTTP body or in the messages of a captured event stream."""
    bodies = [line.removeprefix("data: ") for line in text.splitlines() if line.startswith("data: ")]
    found: set[tuple[str, str]] = set()
    for body in bodies or [text]:
        found |= cards_in(json.loads(body))
    return found


def with_known_deal(skat, table_id: str) -> None:
    """Replace the stored hand by the known one, so a test writes its expected cards as slices of the deck."""
    table = skat.store.tables[table_id]
    skat.store.tables[table_id] = replace(table, dealer=DEALER_SEAT, hand=KNOWN_DEAL)


def seated_three(skat, options=None):
    """Anna, Ben and Cleo sit in seats 1 to 3 of a new table with the known hand; Dora has no chair.

    Returns the table id and the four members as (headers, account), seated people in seat order.
    """
    people = [skat.member() for _ in range(4)]
    opened = skat.create(people[0][0], **({} if options is None else {"options": options}))
    table_id = opened.json()["id"]
    for seat, (headers, _) in enumerate(people[1:3], start=2):
        skat.sit(headers, table_id, seat, command_id=f"command-sit-{seat}")
    with_known_deal(skat, table_id)
    return table_id, people
