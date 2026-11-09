from dataclasses import replace
from itertools import combinations_with_replacement
from operator import attrgetter

import pytest

from skat.engine.bidding import Declared, Pass
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declaration, Declaring, declare, put_back, take_skat
from skat.engine.games import GameKind, Trump
from skat.engine.tricks import CompletedTrick, PlayedOut
from skat.engine.value import Matadors
from skat.table.game_list import list_entry_of, result_view_of, total_of
from skat.table.records import Chair, HandProgress, Occupant, TableId, TableRecord

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
KARO, KREUZ, NULL = GameKind.KARO, GameKind.KREUZ, GameKind.NULL
NONE, SCHWARZ = Announcement.NONE, Announcement.SCHWARZ
CLUBS_JACK, SPADES_JACK = Card(Suit.KREUZ, Rank.JACK), Card(Suit.PIK, Rank.JACK)
MIT_TWO = (CLUBS_JACK, SPADES_JACK)
MIT_ONE = (CLUBS_JACK,)
SEAT_ACCOUNTS = ("account-anna", "account-ben", "account-cleo")
# Seat 2 deals, so seat 3 is forehand, seat 1 middlehand (the declarer below) and seat 2 rearhand.
DEALER = 2
DECLARER_SEAT = 1
POINTS_IN_A_TRICK = (0, 2, 3, 4, 10, 11)
RANK_WORTH = {0: Rank.SEVEN, 2: Rank.JACK, 3: Rank.QUEEN, 4: Rank.KING, 10: Rank.TEN, 11: Rank.ACE}


def trick_worth(points):
    for combination in combinations_with_replacement(POINTS_IN_A_TRICK, 3):
        if sum(combination) == points:
            first, second, third = (Card(Suit.KARO, RANK_WORTH[each]) for each in combination)
            return first, second, third
    raise AssertionError(points)


def dealt_to_middlehand(kind, trumps):
    """Middlehand holds the chosen trumps, filled up with plain cards; the skat holds two cards worth nothing."""
    plain = [card for card in DECK if kind.playing_suit(card) is not Trump.TRUMP and card not in trumps]
    skat = tuple(card for card in plain if card.points == 0)[:2]
    hand = tuple(card for card in (*trumps, *plain) if card not in skat)[:10]
    rest = iter(card for card in DECK if card not in {*hand, *skat})
    return Deal(tuple(next(rest) for _ in range(10)), hand, tuple(next(rest) for _ in range(10)), skat)


def played(kind, trumps=(), declarer_tricks=(), *, bid=18, hand=False, ouvert=False, announcement=NONE):
    """Middlehand declares and takes tricks worth the given points; the opponents take the rest."""
    the_deal = dealt_to_middlehand(kind, trumps)
    state = Declaring.start(Declared(MIDDLEHAND, bid), the_deal)
    if not hand:
        state = put_back(take_skat(state).state, the_deal.skat).state
    outcome = declare(state, kind, hand=hand, ouvert=ouvert, announcement=announcement)
    assert outcome.refusal is None
    tricks = tuple(CompletedTrick(FOREHAND, trick_worth(points), MIDDLEHAND) for points in declarer_tricks) + tuple(
        CompletedTrick(FOREHAND, trick_worth(0), REARHAND) for _ in range(10 - len(declarer_tricks))
    )
    return PlayedOut(outcome.state, tricks)


def seated_table():
    chairs = tuple(Chair(seat, Occupant(account, account.title())) for seat, account in enumerate(SEAT_ACCOUNTS, 1))
    return TableRecord(
        id=TableId("0" * 32),
        version=9,
        chairs=chairs,
        dealer=DEALER,
        hand=None,
        progress=HandProgress(),
        game_list=(),
    )


def entry_of(game):
    return list_entry_of(game, seated_table())


def outcome(entry):
    return {
        "won": entry.won,
        "game_value": entry.game_value,
        "settled_value": entry.settled_value,
        "score": entry.score,
        "declarer_points": entry.declarer_points,
        "opponents_points": entry.opponents_points,
        "overbid": entry.overbid,
    }


def scored(*, won, game_value, settled_value, score, declarer_points, overbid=False):
    return {
        "won": won,
        "game_value": game_value,
        "settled_value": settled_value,
        "score": score,
        "declarer_points": declarer_points,
        "opponents_points": 120 - declarer_points,
        "overbid": overbid,
    }


class TestTheEntrysNumbers:
    @pytest.mark.parametrize(
        ("game", "expected"),
        [
            pytest.param(
                played(KREUZ, MIT_TWO, (30, 30, 18)),
                scored(won=True, game_value=36, settled_value=36, score=36, declarer_points=78),
                id="end-won",
            ),
            pytest.param(
                played(KREUZ, MIT_TWO, (30, 24)),
                scored(won=False, game_value=36, settled_value=36, score=-72, declarer_points=54),
                id="end-lost",
            ),
            pytest.param(
                played(KARO, MIT_ONE, (30, 30, 10), bid=20),
                scored(won=False, game_value=18, settled_value=27, score=-54, declarer_points=70, overbid=True),
                id="end-over",
            ),
            pytest.param(
                played(KREUZ, MIT_TWO, (30, 30, 30, 5)),
                scored(won=True, game_value=48, settled_value=48, score=48, declarer_points=95),
                id="r-score-3-kreuz-mit-2-schneider",
            ),
            pytest.param(
                played(NULL),
                scored(won=True, game_value=23, settled_value=23, score=23, declarer_points=0),
                id="null-won",
            ),
            pytest.param(
                played(NULL, declarer_tricks=(12,)),
                scored(won=False, game_value=23, settled_value=23, score=-46, declarer_points=12),
                id="null-lost",
            ),
        ],
    )
    def test_value_and_score_come_from_the_engine_s_valuation_and_settlement(self, game, expected):
        assert outcome(entry_of(game)) == expected

    def test_the_bid_is_the_auction_s(self):
        assert entry_of(played(KARO, MIT_ONE, (30, 30, 10), bid=20)).bid == 20


class TestTheEntrysGame:
    def test_names_the_declarer_s_seat_from_the_dealer_and_the_seated_accounts_by_seat(self):
        entry = entry_of(played(KREUZ, MIT_TWO, (30, 30, 18)))

        assert entry.declarer_seat == DECLARER_SEAT
        assert entry.seat_accounts == SEAT_ACCOUNTS

    def test_names_the_declared_game_and_its_matadors(self):
        entry = entry_of(played(KREUZ, MIT_TWO, (30, 30, 18)))

        assert entry.declaration == Declaration(KREUZ, hand=False, ouvert=False, announcement=NONE)
        assert entry.matadors == Matadors(mit=True, count=2)

    @pytest.mark.parametrize(
        ("game", "levels"),
        [
            pytest.param(played(KREUZ, MIT_TWO, (30, 30, 18)), (False, False), id="neither"),
            pytest.param(played(KREUZ, MIT_TWO, (30, 30, 30, 5)), (True, False), id="opponents-schneider"),
            pytest.param(played(KREUZ, MIT_TWO, (12,) * 10), (True, True), id="opponents-schwarz"),
            pytest.param(played(KREUZ, MIT_TWO, (25,)), (True, False), id="declarer-schneider"),
            pytest.param(played(KREUZ, MIT_TWO), (True, True), id="declarer-schwarz"),
            pytest.param(played(NULL, declarer_tricks=(12,)), (False, False), id="null"),
        ],
    )
    def test_schneider_and_schwarz_are_the_levels_the_valuation_counted(self, game, levels):
        entry = entry_of(game)

        assert attrgetter("schneider", "schwarz")(entry) == levels

    def test_hand_ouvert_and_the_announcement_read_back_and_each_level_counts_once(self):
        entry = entry_of(played(KREUZ, MIT_TWO, (12,) * 10, hand=True, ouvert=True, announcement=SCHWARZ))

        assert entry.declaration == Declaration(KREUZ, hand=True, ouvert=True, announcement=SCHWARZ)
        assert attrgetter("schneider", "schwarz")(entry) == (True, True)
        assert entry.game_value == (2 + 7) * 12

    def test_a_null_game_has_no_matadors(self):
        assert entry_of(played(NULL)).matadors is None


def pending_result(*games):
    """The table after its games: no hand, no steps, and one list entry per game."""
    table = seated_table()
    return replace(table, game_list=tuple(list_entry_of(game, table) for game in games))


class TestTheResult:
    @pytest.mark.parametrize(
        ("game", "gains"),
        [
            pytest.param(played(KREUZ, MIT_TWO, (30, 30, 18)), (86, 0, 0), id="end-won"),
            pytest.param(played(KREUZ, MIT_TWO, (30, 24)), (-122, 40, 40), id="end-lost"),
            pytest.param(played(KARO, MIT_ONE, (30, 30, 10), bid=20), (-104, 40, 40), id="end-over"),
            pytest.param(played(NULL, declarer_tricks=(12,)), (-96, 40, 40), id="null-lost"),
        ],
    )
    def test_each_chair_gains_what_the_reckoning_adds_the_declarer_in_seat_one(self, game, gains):
        result = result_view_of(pending_result(game))

        assert tuple(gain.gain for gain in result.gains) == gains
        assert tuple(gain.seat for gain in result.gains) == (DECLARER_SEAT, 2, 3)

    def test_reads_the_last_entry_and_numbers_it_by_its_place_in_the_list(self):
        won, lost = played(KREUZ, MIT_TWO, (30, 30, 18)), played(KREUZ, MIT_TWO, (30, 24))

        result = result_view_of(pending_result(won, lost))

        assert attrgetter("ordinal", "won", "score")(result) == (2, False, -72)

    def test_names_the_game_its_levels_and_both_sides_points(self):
        result = result_view_of(pending_result(played(KARO, MIT_ONE, (30, 30, 10), bid=20)))

        assert result.declaration == Declaration(KARO, hand=False, ouvert=False, announcement=NONE)
        assert attrgetter("schneider", "schwarz", "matadors")(result) == (False, False, Matadors(mit=True, count=1))
        assert attrgetter("overbid", "bid", "game_value", "settled_value")(result) == (True, 20, 18, 27)
        assert attrgetter("declarer_points", "opponents_points")(result) == (70, 50)

    @pytest.mark.parametrize(
        "changed",
        [
            pytest.param({"game_list": ()}, id="no-game-played"),
            pytest.param({"progress": HandProgress(auction=(Pass(MIDDLEHAND),))}, id="steps-of-a-pass-in-kept"),
        ],
    )
    def test_there_is_none_while_no_result_is_pending(self, changed):
        assert result_view_of(replace(pending_result(played(NULL)), **changed)) is None


ANNA, BEN, CLEO, DORA = "anna", "ben", "cleo", "dora"


def game_by(seat, game, accounts=(ANNA, BEN, CLEO)):
    return replace(entry_of(game), declarer_seat=seat, seat_accounts=accounts)


class TestTheTotal:
    def test_a_person_has_nothing_before_any_game(self):
        assert total_of((), ANNA) == 0

    def test_sums_the_gains_of_the_seat_the_person_held_in_each_game(self):
        won = game_by(2, played(KREUZ, MIT_TWO, (30, 30, 18)))
        lost = game_by(1, played(KREUZ, MIT_TWO, (30, 24)))

        assert [total_of((won, lost), account) for account in (ANNA, BEN, CLEO)] == [-122, 126, 40]

    def test_a_person_keeps_their_total_on_another_chair(self):
        won = game_by(2, played(KREUZ, MIT_TWO, (30, 30, 18)))
        moved = game_by(1, played(KREUZ, MIT_TWO, (30, 24)), accounts=(BEN, ANNA, CLEO))

        assert [total_of((won, moved), account) for account in (ANNA, BEN, CLEO)] == [40, -36, 40]

    def test_an_account_that_held_no_seat_adds_nothing_and_a_newcomer_starts_at_zero(self):
        won = game_by(2, played(KREUZ, MIT_TWO, (30, 30, 18)))

        assert total_of((won,), DORA) == 0
