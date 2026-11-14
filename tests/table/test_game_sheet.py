from dataclasses import replace

import pytest

from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.declaration import Announcement, Declaration
from skat.engine.games import GameKind
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.table.game_cards import GameCards, SeatedCard
from skat.table.game_list import GameEnding
from skat.table.game_sheet import (
    CardState,
    DeclaredCount,
    RamschCount,
    SheetCard,
    SheetTrick,
    game_sheet_of,
)
from skat.table.records import HandProgress, RamschOccasion, RamschSetting, TableOptions
from tests.support.played_game import a_ramsch_entry, an_entry, table_in

KREUZ_ACE, KREUZ_TEN, KREUZ_SEVEN = (Card(Suit.KREUZ, rank) for rank in (Rank.ACE, Rank.TEN, Rank.SEVEN))
HERZ_SEVEN, PIK_KING, KARO_ACE = Card(Suit.HERZ, Rank.SEVEN), Card(Suit.PIK, Rank.KING), Card(Suit.KARO, Rank.ACE)
KARO_JACK, PIK_NINE, PIK_EIGHT = (Card(Suit.KARO, Rank.JACK), Card(Suit.PIK, Rank.NINE), Card(Suit.PIK, Rank.EIGHT))
RECKONING = RamschOptions(RamschScoring.POINTS, JungfrauRule.DOUBLES_LOSER, DurchmarschRule.WINS_120)
HERZ_GAME = Declaration(GameKind.HERZ, hand=False, ouvert=False, announcement=Announcement.NONE)


def cards_of(**changed):
    """A game of seat 1's Herz in which seat 1 took both tricks."""
    fields = {
        "hands": ((HERZ_SEVEN, KARO_ACE, PIK_KING), (KREUZ_ACE, PIK_NINE), (KREUZ_TEN, KREUZ_SEVEN, PIK_EIGHT)),
        "skat": (KARO_JACK, KREUZ_SEVEN),
        "put_away": (SeatedCard(1, PIK_KING), SeatedCard(1, KARO_JACK)),
        "tricks": (
            (SeatedCard(1, HERZ_SEVEN), SeatedCard(2, KREUZ_ACE), SeatedCard(3, KREUZ_TEN)),
            (SeatedCard(1, KARO_ACE), SeatedCard(2, PIK_NINE), SeatedCard(3, PIK_EIGHT)),
        ),
        **changed,
    }
    return GameCards(**fields)


def a_whole_game():
    """Ten tricks of thirty distinct cards, so that a game is played out whatever its cards are worth."""
    seated = [SeatedCard(place % 3 + 1, card) for place, card in enumerate(DECK[:30])]
    return tuple(tuple(seated[start : start + 3]) for start in range(0, 30, 3))


def a_herz_game(**changed):
    return replace(an_entry(), declaration=HERZ_GAME, **{"declarer_points": 70, **changed})


def sheet_of(entry, cards, options=None):
    table = replace(table_in(HandProgress(), options), hand=None, game_list=(entry,))
    return game_sheet_of(table, 1, cards)


class TestADeclaredGame:
    def test_its_tricks_come_numbered_with_their_taker_and_points_and_the_interrupted_one_has_neither(self):
        interrupted = (SeatedCard(3, KREUZ_SEVEN), SeatedCard(1, PIK_KING))
        cards = cards_of(tricks=(*cards_of().tricks, interrupted))

        tricks = sheet_of(a_herz_game(), cards).cards.tricks

        assert tricks == (
            SheetTrick(1, cards.tricks[0], taker_seat=1, points=21),
            SheetTrick(2, cards.tricks[1], taker_seat=1, points=11),
            SheetTrick(3, interrupted, taker_seat=None, points=None),
        )

    @pytest.mark.parametrize(("kind", "taker_seat"), [(GameKind.HERZ, 2), (GameKind.GRAND, 1)])
    def test_the_game_s_kind_decides_whether_a_seven_of_hearts_takes_a_trick(self, kind, taker_seat):
        trick = (SeatedCard(1, KREUZ_ACE), SeatedCard(2, HERZ_SEVEN), SeatedCard(3, KREUZ_TEN))
        entry = replace(a_herz_game(), declaration=replace(HERZ_GAME, kind=kind))

        (taken,) = sheet_of(entry, cards_of(tricks=(trick,))).cards.tricks

        assert taken.taker_seat == taker_seat

    def test_names_the_declarer_and_the_points_each_side_counted_and_how_the_game_ended(self):
        entry = a_herz_game(ending=GameEnding.PLAYED_OUT, ended_by_seat=None)

        count = sheet_of(entry, cards_of(tricks=a_whole_game())).count

        assert count == DeclaredCount(
            declarer_seat=1, declarer_points=70, opponents_points=50, ending=GameEnding.PLAYED_OUT, ended_by_seat=None
        )

    def test_a_game_that_ended_early_counts_only_the_points_played(self):
        interrupted = (SeatedCard(3, KREUZ_SEVEN), SeatedCard(1, PIK_KING))
        opponents_trick = (SeatedCard(2, PIK_NINE), SeatedCard(3, PIK_EIGHT), SeatedCard(1, KARO_ACE))
        cards = cards_of(tricks=(cards_of().tricks[0], opponents_trick, interrupted))
        entry = a_herz_game(ending=GameEnding.GIVEN_UP, ended_by_seat=1, declarer_points=0)

        count = sheet_of(entry, cards).count

        assert (count.declarer_points, count.opponents_points) == (21 + 4 + 2, 11)

    def test_a_dealt_card_is_marked_played_put_away_or_unplayed_by_what_became_of_it(self):
        hands = sheet_of(a_herz_game(), cards_of()).cards.hands

        assert (hands[0].seat, hands[0].cards) == (
            1,
            (
                SheetCard(HERZ_SEVEN, CardState.PLAYED),
                SheetCard(KARO_ACE, CardState.PLAYED),
                SheetCard(PIK_KING, CardState.PUT_AWAY),
            ),
        )
        assert hands[2].cards[2] == SheetCard(PIK_EIGHT, CardState.PLAYED)

    def test_a_card_never_played_is_unplayed(self):
        cards = cards_of(tricks=cards_of().tricks[:1])

        hands = sheet_of(a_herz_game(), cards).cards.hands

        assert hands[1].cards == (SheetCard(KREUZ_ACE, CardState.PLAYED), SheetCard(PIK_NINE, CardState.UNPLAYED))

    def test_shows_the_skat_as_dealt_and_what_each_seat_put_away(self):
        cards = sheet_of(a_herz_game(), cards_of()).cards

        assert (cards.skat, cards.put_away) == (cards_of().skat, cards_of().put_away)


class TestARamsch:
    def test_counts_each_seat_s_points_and_names_the_seat_the_skat_went_to(self):
        options = TableOptions(ramsch=RamschSetting(RamschOccasion.PASSED_IN, RECKONING))
        entry = a_ramsch_entry()

        sheet = sheet_of(entry, cards_of(put_away=()), options)

        assert sheet.count == RamschCount(seat_points=(47, 40, 33), durchmarsch_seat=None)
        assert sheet.cards.skat_takers == (1,)

    @pytest.mark.parametrize(
        ("scoring", "skat_takers"),
        [(RamschScoring.POINTS, (2,)), (RamschScoring.SKAT_TO_LOSER, (1,))],
        ids=["the-last-trick-s-taker", "the-seat-with-the-most-points"],
    )
    def test_the_scoring_the_table_sets_names_who_got_the_skat(self, scoring, skat_takers):
        options = TableOptions(ramsch=RamschSetting(RamschOccasion.PASSED_IN, replace(RECKONING, scoring=scoring)))
        cards = cards_of(
            tricks=(
                (SeatedCard(1, KARO_ACE), SeatedCard(2, PIK_NINE), SeatedCard(3, KREUZ_ACE)),
                (SeatedCard(3, KREUZ_TEN), SeatedCard(1, KREUZ_SEVEN), SeatedCard(2, PIK_EIGHT)),
                (SeatedCard(3, HERZ_SEVEN), SeatedCard(1, PIK_KING), SeatedCard(2, KARO_JACK)),
            )
        )

        assert sheet_of(a_ramsch_entry(), cards, options).cards.skat_takers == skat_takers

    def test_a_schieberamsch_s_skat_takers_get_the_skat_as_it_lay_not_the_skat_as_dealt(self):
        options = TableOptions(ramsch=RamschSetting(RamschOccasion.PASSED_IN, RECKONING))
        laid = (HERZ_SEVEN, KARO_JACK)

        cards = sheet_of(a_ramsch_entry(), cards_of(put_away=(), laid_skat=laid), options).cards

        assert (cards.skat, cards.laid_skat, cards.skat_takers) == (cards_of().skat, laid, (1,))


class TestAGameStoredWithoutCards:
    def test_has_its_count_and_no_cards(self):
        sheet = sheet_of(a_herz_game(), None)

        assert (sheet.number, sheet.cards) == (1, None)
        assert isinstance(sheet.count, DeclaredCount)
