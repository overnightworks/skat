import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from skat.store.game_list import read_game_cards
from tests.support.migrations import list_row, migrated_from, run_in_transaction

pytestmark = pytest.mark.postgres


def card_row(pile="trick", seat=1, trick=1, place=1, suit="hearts", rank="ace", ordinal=1):
    """A card of the one game the fixture stores; the columns a pile does not name are NULL."""
    return text(
        "INSERT INTO game_cards (table_id, series_number, ordinal, pile, seat, trick, place, suit, rank)"
        " VALUES ('t', 1, :ordinal, :pile, :seat, :trick, :place, :suit, :rank)"
    ).bindparams(ordinal=ordinal, pile=pile, seat=seat, trick=trick, place=place, suit=suit, rank=rank)


def a_hand_card(**changed):
    return card_row(**{"pile": "hand", "trick": None, "place": None, **changed})


def a_skat_card(**changed):
    return card_row(**{"pile": "skat", "seat": None, "trick": None, "place": None, **changed})


def a_put_away_card(**changed):
    return card_row(**{"pile": "put-away", "trick": None, "place": None, **changed})


class TestFromAGameListedAtTheRevisionBefore:
    @pytest.fixture
    def migrated(self, unmigrated_engine):
        return migrated_from(
            unmigrated_engine,
            "0045",
            text("INSERT INTO tables (id, version, dealer, last_played_at) VALUES ('t', 3, 2, now())"),
            text(list_row(series_number=1)),
        )

    def test_the_game_stays_and_says_it_has_no_cards(self, migrated):
        with migrated.connect() as connection:
            games = connection.execute(text("SELECT count(*) FROM game_list")).scalar_one()
            cards = read_game_cards(connection, "t", 1)

        assert (games, cards) == (1, None)

    @pytest.mark.parametrize(
        "row",
        [
            pytest.param(a_hand_card(), id="a-hand-card"),
            pytest.param(a_skat_card(), id="a-skat-card"),
            pytest.param(a_put_away_card(), id="a-put-away-card"),
            pytest.param(card_row(), id="a-trick-card"),
        ],
    )
    def test_accepts_a_card_of_each_pile(self, migrated, row):
        run_in_transaction(migrated, row)

    @pytest.mark.parametrize(
        "row",
        [
            pytest.param(card_row(pile="stack"), id="no-pile"),
            pytest.param(a_hand_card(seat=4), id="no-seat"),
            pytest.param(card_row(trick=11), id="no-trick"),
            pytest.param(card_row(place=4), id="no-place"),
            pytest.param(card_row(suit="swords"), id="no-suit"),
            pytest.param(card_row(rank="one"), id="no-rank"),
            pytest.param(a_hand_card(seat=None), id="a-hand-card-without-its-seat"),
            pytest.param(a_hand_card(trick=1), id="a-hand-card-in-a-trick"),
            pytest.param(a_skat_card(seat=1), id="a-skat-card-of-a-seat"),
            pytest.param(a_put_away_card(seat=None), id="a-put-away-card-without-its-seat"),
            pytest.param(card_row(place=None), id="a-trick-card-without-its-place"),
            pytest.param(card_row(ordinal=2), id="a-card-of-no-game"),
        ],
    )
    def test_refuses_a_row_that_is_no_card_of_a_game(self, migrated, row):
        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, row)

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            pytest.param(a_hand_card(seat=1), a_hand_card(seat=2), id="a-card-dealt-twice"),
            pytest.param(a_hand_card(), a_skat_card(), id="a-card-dealt-to-a-seat-and-the-skat"),
            pytest.param(card_row(), card_row(trick=2), id="a-card-played-twice"),
            pytest.param(card_row(), card_row(rank="king"), id="a-place-taken-twice"),
            pytest.param(a_put_away_card(), a_put_away_card(), id="a-card-put-away-twice-by-a-seat"),
        ],
    )
    def test_refuses_what_a_game_holds_once(self, migrated, first, second):
        run_in_transaction(migrated, first)

        with pytest.raises(IntegrityError):
            run_in_transaction(migrated, second)

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            pytest.param(a_hand_card(), card_row(), id="a-dealt-card-played"),
            pytest.param(a_put_away_card(seat=1), a_put_away_card(seat=2), id="a-card-put-away-by-two-seats"),
            pytest.param(a_skat_card(), a_put_away_card(), id="a-skat-card-put-away-again"),
        ],
    )
    def test_accepts_a_card_in_two_piles_and_a_card_put_away_by_two_seats(self, migrated, first, second):
        run_in_transaction(migrated, first)
        run_in_transaction(migrated, second)
