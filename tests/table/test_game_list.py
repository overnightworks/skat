from dataclasses import replace
from itertools import combinations_with_replacement
from operator import attrgetter

import pytest

from skat.engine.bidding import Declared, Pass
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import Announcement, Declaration, Declaring, declare, put_back, take_skat
from skat.engine.games import GameKind, Trump
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer, Word
from skat.engine.tricks import CompletedTrick, PlayedOut
from skat.engine.value import Level, Matadors
from skat.table.game_list import (
    KontraResult,
    Standing,
    list_entry_of,
    result_view_of,
    series_list_view_of,
    standings_of,
    total_of,
)
from skat.table.records import Chair, HandProgress, Occupant, OccupantKind, TableId, TableOptions, TableRecord

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
REACH = KontraReach.KONTRA_RE
KONTRA, RE = Word.KONTRA, Word.RE
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
    chairs = tuple(
        Chair(seat, Occupant(account, account.title(), OccupantKind.PERSON))
        for seat, account in enumerate(SEAT_ACCOUNTS, 1)
    )
    return TableRecord(
        id=TableId("0" * 32),
        version=9,
        chairs=chairs,
        dealer=DEALER,
        hand=None,
        progress=HandProgress(),
        game_list=(),
        series=None,
        options=TableOptions(),
    )


def entry_of(game):
    return list_entry_of(game, seated_table(), None)


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

    def test_keeps_the_display_names_seated_beside_their_accounts(self):
        entry = entry_of(played(KREUZ, MIT_TWO, (30, 30, 18)))

        assert entry.seat_names == tuple(account.title() for account in SEAT_ACCOUNTS)

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
    return replace(table, game_list=tuple(list_entry_of(game, table, None) for game in games))


class TestTheResult:
    @pytest.mark.parametrize(
        ("game", "gains", "reckoning"),
        [
            pytest.param(played(KREUZ, MIT_TWO, (30, 30, 18)), (86, 0, 0), (3, 50, False), id="end-won"),
            pytest.param(played(KREUZ, MIT_TWO, (30, 24)), (-122, 40, 40), (3, -50, False), id="end-lost"),
            pytest.param(played(KARO, MIT_ONE, (30, 30, 10), bid=20), (-104, 40, 40), (2, -50, False), id="end-over"),
            pytest.param(played(NULL, declarer_tricks=(12,)), (-96, 40, 40), (None, -50, False), id="null-lost"),
        ],
    )
    def test_each_chair_gains_what_the_reckoning_adds_the_declarer_in_seat_one(self, game, gains, reckoning):
        result = result_view_of(pending_result(game))

        assert tuple(gain.gain for gain in result.gains) == gains
        assert attrgetter("multiplier", "list_bonus", "announcement_missed")(result) == reckoning
        assert tuple(gain.seat for gain in result.gains) == (DECLARER_SEAT, 2, 3)

    @pytest.mark.parametrize(
        ("game", "won"),
        [
            pytest.param(played(KREUZ, MIT_TWO, (30, 30, 18)), (True, False, False), id="declarer-won"),
            pytest.param(played(KREUZ, MIT_TWO, (30, 24)), (False, True, True), id="opponents-won"),
        ],
    )
    def test_each_chair_is_marked_won_when_its_side_won(self, game, won):
        result = result_view_of(pending_result(game))

        assert tuple(gain.won for gain in result.gains) == won

    @pytest.mark.parametrize(
        ("game", "base_value", "levels", "doubled"),
        [
            pytest.param(played(KREUZ, MIT_TWO, (30, 30, 18)), 12, (Level.SPIEL,), False, id="won"),
            pytest.param(played(KREUZ, MIT_TWO, (30, 24), hand=True), 12, (Level.SPIEL, Level.HAND), True, id="lost"),
            pytest.param(played(NULL, declarer_tricks=(12,)), None, (), True, id="null"),
        ],
    )
    def test_names_the_base_value_the_levels_and_whether_the_value_counts_doubled(
        self, game, base_value, levels, doubled
    ):
        result = result_view_of(pending_result(game))

        assert attrgetter("base_value", "levels", "doubled")(result) == (base_value, levels, doubled)

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
        assert total_of((), ANNA, REACH) == 0

    def test_sums_the_gains_of_the_seat_the_person_held_in_each_game(self):
        won = game_by(2, played(KREUZ, MIT_TWO, (30, 30, 18)))
        lost = game_by(1, played(KREUZ, MIT_TWO, (30, 24)))

        assert [total_of((won, lost), account, REACH) for account in (ANNA, BEN, CLEO)] == [-122, 126, 40]

    def test_a_person_keeps_their_total_on_another_chair(self):
        won = game_by(2, played(KREUZ, MIT_TWO, (30, 30, 18)))
        moved = game_by(1, played(KREUZ, MIT_TWO, (30, 24)), accounts=(BEN, ANNA, CLEO))

        assert [total_of((won, moved), account, REACH) for account in (ANNA, BEN, CLEO)] == [40, -36, 40]

    def test_an_account_that_held_no_seat_adds_nothing_and_a_newcomer_starts_at_zero(self):
        won = game_by(2, played(KREUZ, MIT_TWO, (30, 30, 18)))

        assert total_of((won,), DORA, REACH) == 0


def game_for(seat, *, won, score, accounts=(ANNA, BEN, CLEO), names=None):
    """A game the person on `seat` declared, with the score it was settled at."""
    names = names or tuple(account.title() for account in accounts)
    return replace(
        entry_of(played(KREUZ, MIT_TWO, (30, 30, 18))),
        declarer_seat=seat,
        seat_accounts=accounts,
        seat_names=names,
        won=won,
        score=score,
    )


def standing_rows(game_list):
    return [(each.account_id, each.place, each.total, each.won, each.lost) for each in standings_of(game_list, REACH)]


class TestTheStandings:
    def test_nobody_has_a_place_before_any_game(self):
        assert standings_of((), REACH) == ()

    @pytest.mark.parametrize(
        ("game_list", "rows"),
        [
            pytest.param(
                (game_for(2, won=True, score=36),),
                [(BEN, 1, 86, 1, 0), (ANNA, 2, 0, 0, 0), (CLEO, 2, 0, 0, 0)],
                id="ranked-by-total",
            ),
            pytest.param(
                (game_for(1, won=True, score=50), game_for(2, won=True, score=0), game_for(2, won=True, score=0)),
                [(BEN, 1, 100, 2, 0), (ANNA, 2, 100, 1, 0), (CLEO, 3, 0, 0, 0)],
                id="a-tie-on-total-goes-to-more-won",
            ),
            pytest.param(
                (game_for(1, won=True, score=90), game_for(1, won=False, score=0), game_for(2, won=True, score=0)),
                [(BEN, 1, 90, 1, 0), (ANNA, 2, 90, 1, 1), (CLEO, 3, 40, 0, 0)],
                id="a-tie-on-total-and-won-goes-to-fewer-lost",
            ),
            pytest.param(
                (game_for(3, won=False, score=-72),),
                [(ANNA, 1, 40, 0, 0), (BEN, 1, 40, 0, 0), (CLEO, 3, -122, 0, 1)],
                id="a-full-tie-shares-the-place-and-the-next-counts-everyone-above",
            ),
        ],
    )
    def test_ranks_by_total_then_more_won_then_fewer_lost(self, game_list, rows):
        assert standing_rows(game_list) == rows

    def test_a_person_who_left_keeps_a_row_under_their_own_name_and_their_own_games(self):
        stayed = game_for(2, won=True, score=36)
        replaced = game_for(2, won=True, score=0, accounts=(ANNA, DORA, CLEO), names=("Anna", "Dora", "Cleo"))

        standings = standings_of((stayed, replaced), REACH)

        assert [(each.display_name, each.total, each.won) for each in standings] == [
            ("Ben", 86, 1),
            ("Dora", 50, 1),
            ("Anna", 0, 0),
            ("Cleo", 0, 0),
        ]

    def test_an_account_that_sat_again_on_another_seat_has_one_row_with_all_its_games(self):
        first = game_for(1, won=True, score=36)
        moved = game_for(2, won=True, score=36, accounts=(BEN, ANNA, CLEO))

        assert standing_rows((first, moved)) == [(ANNA, 1, 172, 2, 0), (BEN, 2, 0, 0, 0), (CLEO, 2, 0, 0, 0)]

    def test_names_a_person_by_the_last_entry_that_seated_them(self):
        earlier = game_for(1, won=True, score=36, names=("Anna", "Ben", "Cleo"))
        later = game_for(1, won=True, score=36, names=("Anna", "Benno", "Cleo"))

        assert {each.account_id: each.display_name for each in standings_of((earlier, later), REACH)}[BEN] == "Benno"

    def test_a_row_stored_without_names_has_no_name_and_never_the_account(self):
        nameless = game_for(1, won=True, score=36, names=(None, None, None))

        assert {each.display_name for each in standings_of((nameless,), REACH)} == {None}

    def test_a_standing_is_its_account_name_total_record_and_place(self):
        assert standings_of((game_for(1, won=True, score=36),), REACH)[0] == Standing(ANNA, "Anna", 86, 1, 0, 1)


class TestTheSeriesList:
    def test_a_table_without_a_finished_game_has_an_empty_list(self):
        assert series_list_view_of(seated_table()) == ()

    def test_every_game_is_a_row_numbered_from_one_with_the_declarer_s_stored_name(self):
        table = pending_result(played(KREUZ, MIT_TWO, (30, 30, 18)), played(KREUZ, MIT_TWO, (30, 24)), played(NULL))

        rows = series_list_view_of(table)

        assert [row.number for row in rows] == [1, 2, 3]
        assert {row.declarer_name for row in rows} == {"Account-Anna"}

    def test_a_row_carries_the_game_its_levels_its_value_and_the_gain_or_loss_of_the_declarer(self):
        won, lost, overbid = (
            played(KREUZ, MIT_TWO, (30, 30, 30, 5)),
            played(KREUZ, MIT_TWO, (30, 24)),
            played(KARO, MIT_ONE, (30, 30, 10), bid=20),
        )

        rows = series_list_view_of(pending_result(won, lost, overbid))

        assert [(row.declaration, row.levels, row.settled_value, row.score) for row in rows] == [
            (Declaration(KREUZ, hand=False, ouvert=False, announcement=NONE), (Level.SPIEL, Level.SCHNEIDER), 48, 48),
            (Declaration(KREUZ, hand=False, ouvert=False, announcement=NONE), (Level.SPIEL,), 36, -72),
            (Declaration(KARO, hand=False, ouvert=False, announcement=NONE), (Level.SPIEL,), 27, -54),
        ]

    def test_the_levels_are_those_the_result_of_the_same_game_shows(self):
        table = pending_result(played(KREUZ, MIT_TWO, (30, 30, 30, 5)))

        assert series_list_view_of(table)[0].levels == result_view_of(table).levels

    def test_a_row_stored_before_names_were_kept_has_no_declarer_name(self):
        table = pending_result(played(KREUZ, MIT_TWO, (30, 30, 18)))
        nameless = replace(table.game_list[0], seat_names=(None, None, None))

        rows = series_list_view_of(replace(table, game_list=(nameless,)))

        assert rows[0].declarer_name is None
        assert not any(account in repr(rows) for account in SEAT_ACCOUNTS)

    def test_a_row_names_the_name_stored_with_the_game_not_the_one_seated_now(self):
        table = pending_result(played(KREUZ, MIT_TWO, (30, 30, 18)))
        replaced = replace(table.chairs[0], occupant=Occupant("account-dora", "Dora", OccupantKind.PERSON))

        rows = series_list_view_of(replace(table, chairs=(replaced, *table.chairs[1:])))

        assert [row.declarer_name for row in rows] == ["Account-Anna"]

    @pytest.mark.parametrize("seat", [1, 2, 3])
    def test_a_row_names_the_person_who_sat_on_the_declarer_s_seat(self, seat):
        names = ("Anna", "Ben", "Cleo")
        table = replace(seated_table(), game_list=(game_for(seat, won=True, score=48, names=names),))

        assert [row.declarer_name for row in series_list_view_of(table)] == [names[seat - 1]]


def doubled_table(entry, word, reach):
    options = TableOptions(kontra=KontraOptions(KontraSayer.ANY_OPPONENT, reach, KontraDeadline.OWN_CARD))
    return replace(seated_table(), options=options, game_list=(replace(entry, kontra_word=word),))


class TestTheDoubledGame:
    WON = replace(entry_of(played(KREUZ, MIT_TWO, (30, 30, 18))), score=72)  # Kontra doubles the won game's 36
    LOST = replace(entry_of(played(KREUZ, MIT_TWO, (30, 24))), score=-288)  # Re quadruples the lost game's -72

    @pytest.mark.parametrize(
        ("entry", "word", "reach", "gains", "list_bonus", "factor"),
        [
            pytest.param(WON, KONTRA, REACH, (122, 0, 0), 50, 2, id="won-kontra"),
            pytest.param(WON, KONTRA, KontraReach.KONTRA_RE_STANDINGS, (172, 0, 0), 100, 2, id="won-kontra-standings"),
            pytest.param(LOST, RE, REACH, (-338, 40, 40), -50, 4, id="lost-re"),
            pytest.param(LOST, RE, KontraReach.KONTRA_RE_STANDINGS, (-488, 160, 160), -200, 4, id="lost-re-standings"),
        ],
    )
    def test_the_gains_the_bonus_and_the_result_follow_the_doubled_list_score(
        self, entry, word, reach, gains, list_bonus, factor
    ):
        result = result_view_of(doubled_table(entry, word, reach))

        assert tuple(gain.gain for gain in result.gains) == gains
        assert result.list_bonus == list_bonus
        assert result.kontra == KontraResult(word, factor)
        assert (result.score, result.settled_value, result.game_value) == (
            entry.score,
            entry.settled_value,
            entry.game_value,
        )

    def test_a_game_without_a_word_names_no_doubling(self):
        assert result_view_of(pending_result(played(KREUZ, MIT_TWO, (30, 30, 18)))).kontra is None

    def test_the_totals_and_the_standings_follow_the_reach_of_the_table(self):
        entry = replace(self.WON, kontra_word=KONTRA)
        standings = KontraReach.KONTRA_RE_STANDINGS

        assert total_of((entry,), SEAT_ACCOUNTS[0], REACH) == 122
        assert total_of((entry,), SEAT_ACCOUNTS[0], standings) == 172
        assert standings_of((entry,), standings)[0].total == 172

    def test_a_row_of_the_series_list_names_the_last_word_and_the_doubled_score(self):
        row = series_list_view_of(doubled_table(self.WON, RE, REACH))[0]

        assert (row.kontra_word, row.score) == (RE, 72)
