from dataclasses import replace

import pytest

from skat.engine.bidding import Awaiting, Bid, Pass
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declare, Stage, TakeSkat
from skat.engine.games import GameKind
from skat.table.records import Chair, HandProgress, Occupant, TableId, TableRecord
from skat.table.views import view_of

ANNA, BEN, CLEO, DORA = "account-anna", "account-ben", "account-cleo", "account-dora"
NOBODY_CONNECTED = frozenset[str]()

FOREHAND_CARDS = DECK[0:10]
MIDDLEHAND_CARDS = DECK[10:20]
REARHAND_CARDS = DECK[20:30]
KNOWN_DEAL = Deal(forehand=FOREHAND_CARDS, middlehand=MIDDLEHAND_CARDS, rearhand=REARHAND_CARDS, skat=DECK[30:32])


THREE_PASSES = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))


def seated_table(
    dealer: int | None = None, hand: Deal | None = None, steps: tuple[Pass | Bid, ...] = ()
) -> TableRecord:
    people = ((1, ANNA, "Anna"), (2, BEN, "Ben"), (3, CLEO, "Cleo"))
    chairs = tuple(Chair(seat, Occupant(account_id, name)) for seat, account_id, name in people)
    return TableRecord(TableId("0" * 32), 5, chairs, dealer, hand, HandProgress(steps))


class TestChairPositions:
    @pytest.mark.parametrize(
        ("dealer", "positions"),
        [
            pytest.param(1, ["rearhand", "forehand", "middlehand"], id="dealer-1"),
            pytest.param(2, ["middlehand", "rearhand", "forehand"], id="dealer-2"),
            pytest.param(3, ["forehand", "middlehand", "rearhand"], id="dealer-3"),
        ],
    )
    def test_names_each_chairs_position_from_the_dealer_with_the_forehand_left_of_the_dealer(self, dealer, positions):
        view = view_of(seated_table(dealer, KNOWN_DEAL), ANNA, NOBODY_CONNECTED)

        assert [chair.hand.position.value for chair in view.chairs] == positions
        assert view.hand.dealer_seat == dealer

    def test_gives_every_chair_the_count_of_its_cards_and_the_hand_the_count_of_the_skat(self):
        view = view_of(seated_table(2, KNOWN_DEAL), ANNA, NOBODY_CONNECTED)

        assert [chair.hand.card_count for chair in view.chairs] == [10, 10, 10]
        assert view.hand.skat_count == 2


class TestOwnCards:
    @pytest.mark.parametrize(
        ("viewer", "cards"),
        [
            pytest.param(ANNA, MIDDLEHAND_CARDS, id="anna-middlehand"),
            pytest.param(BEN, REARHAND_CARDS, id="ben-rearhand"),
            pytest.param(CLEO, FOREHAND_CARDS, id="cleo-forehand"),
        ],
    )
    def test_gives_a_seated_viewer_only_the_cards_of_their_own_position(self, viewer, cards):
        view = view_of(seated_table(2, KNOWN_DEAL), viewer, NOBODY_CONNECTED)

        assert view.hand.own_cards == cards

    def test_gives_a_viewer_without_a_chair_no_card_but_every_count(self):
        view = view_of(seated_table(2, KNOWN_DEAL), DORA, frozenset({DORA}))

        assert view.hand.own_cards == ()
        assert [chair.hand.card_count for chair in view.chairs] == [10, 10, 10]
        assert [chair.hand.position.value for chair in view.chairs] == ["middlehand", "rearhand", "forehand"]
        assert view.hand.dealer_seat == 2

    def test_lists_the_own_cards_in_deck_order_whatever_order_the_deal_holds_them(self):
        shuffled = replace(KNOWN_DEAL, middlehand=tuple(reversed(MIDDLEHAND_CARDS)))

        view = view_of(seated_table(2, shuffled), ANNA, NOBODY_CONNECTED)

        assert view.hand.own_cards == (
            Card(Suit.PIK, Rank.NINE),
            Card(Suit.PIK, Rank.TEN),
            Card(Suit.PIK, Rank.JACK),
            Card(Suit.PIK, Rank.QUEEN),
            Card(Suit.PIK, Rank.KING),
            Card(Suit.PIK, Rank.ACE),
            Card(Suit.HERZ, Rank.SEVEN),
            Card(Suit.HERZ, Rank.EIGHT),
            Card(Suit.HERZ, Rank.NINE),
            Card(Suit.HERZ, Rank.TEN),
        )


class TestSkatStaysHidden:
    @pytest.mark.parametrize("viewer", [ANNA, BEN, CLEO, DORA])
    def test_no_viewer_gets_the_skats_cards_only_its_count(self, viewer):
        view = view_of(seated_table(2, KNOWN_DEAL), viewer, frozenset({DORA}))

        assert not set(view.hand.own_cards) & set(KNOWN_DEAL.skat)
        assert view.hand.skat_count == len(KNOWN_DEAL.skat)


class TestNoHand:
    def test_a_table_without_a_hand_has_no_hand_view_and_no_chair_hand(self):
        view = view_of(seated_table(), ANNA, NOBODY_CONNECTED)

        assert view.hand is None
        assert [chair.hand for chair in view.chairs] == [None, None, None]


class TestPassedIn:
    @pytest.mark.parametrize(("dealer", "next_seat"), [(1, 2), (2, 3), (3, 1)])
    def test_after_three_passes_says_passed_in_and_names_the_next_dealer(self, dealer, next_seat):
        view = view_of(seated_table(dealer, steps=THREE_PASSES), ANNA, NOBODY_CONNECTED)

        assert view.passed_in is not None
        assert view.passed_in.next_dealer_seat == next_seat

    def test_names_no_next_dealer_while_a_chair_is_free(self):
        table = seated_table(1, steps=THREE_PASSES)
        table = replace(table, chairs=(table.chairs[0], Chair(2, None), table.chairs[2]))

        view = view_of(table, ANNA, NOBODY_CONNECTED)

        assert view.passed_in is not None
        assert view.passed_in.next_dealer_seat is None

    @pytest.mark.parametrize(
        "table",
        [
            pytest.param(seated_table(), id="never-dealt"),
            pytest.param(seated_table(1, KNOWN_DEAL), id="a-hand-runs"),
            pytest.param(seated_table(1, KNOWN_DEAL, THREE_PASSES), id="the-hand-still-on-the-table"),
            pytest.param(
                seated_table(1, steps=(Bid(Position.MIDDLEHAND, 18),)), id="the-auction-did-not-end-in-passes"
            ),
        ],
    )
    def test_says_nothing_of_a_passed_in_hand_otherwise(self, table):
        assert view_of(table, ANNA, NOBODY_CONNECTED).passed_in is None


class TestAuctionInTheHand:
    def test_a_running_hand_carries_the_auction_for_its_viewer(self):
        view = view_of(seated_table(2, KNOWN_DEAL), ANNA, NOBODY_CONNECTED)

        assert view.hand.auction.awaiting is Awaiting.BID
        assert view.hand.auction.values != ()

    def test_a_viewer_whose_turn_it_is_not_gets_no_value_to_name(self):
        view = view_of(seated_table(2, KNOWN_DEAL), BEN, NOBODY_CONNECTED)

        assert view.hand.auction.values == ()


def middlehand_won(*steps) -> HandProgress:
    won = (Bid(Position.MIDDLEHAND, 18), Pass(Position.FOREHAND), Pass(Position.REARHAND))
    return HandProgress(auction=won, declaring=tuple(steps))


class TestDeclaringInTheHand:
    def test_a_hand_with_no_declarer_has_no_declaring(self):
        view = view_of(seated_table(2, KNOWN_DEAL), ANNA, NOBODY_CONNECTED)

        assert view.hand.declaring is None

    def test_the_declarers_twelve_are_listed_in_deck_order_after_the_take(self):
        shuffled = replace(KNOWN_DEAL, middlehand=tuple(reversed(MIDDLEHAND_CARDS)))
        table = replace(seated_table(2, shuffled), progress=middlehand_won(TakeSkat()))

        view = view_of(table, ANNA, NOBODY_CONNECTED)

        assert view.hand.own_cards == (*MIDDLEHAND_CARDS, *KNOWN_DEAL.skat)
        assert view.hand.skat_count == 0
        assert view.hand.declaring.stage is Stage.DISCARDING

    def test_the_declarers_open_cards_are_listed_in_deck_order(self):
        shuffled = replace(KNOWN_DEAL, middlehand=tuple(reversed(MIDDLEHAND_CARDS)))
        ouvert = Declare(GameKind.GRAND, hand=True, ouvert=True, announcement=Announcement.SCHWARZ)
        table = replace(seated_table(2, shuffled), progress=middlehand_won(ouvert))

        view = view_of(table, BEN, NOBODY_CONNECTED)

        assert view.hand.declaring.open_cards == MIDDLEHAND_CARDS
