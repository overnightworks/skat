from dataclasses import replace

import pytest

from skat.engine.cards import Rank
from skat.engine.deal import Position
from skat.engine.tricks import ALL_POINTS
from skat.web.declaring import GameToken
from skat.web.playing import TABLE_THROW_DOWN_SUFFIX
from tests.support.payload_cards import FOREHAND_CARDS, KNOWN_DEAL, cards_in_text
from tests.web.support.playing import Table, card, ending_of, game_of, points_of_cards

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# The skat of the known deal is the Karo King and the Karo Ace.
SKAT_POINTS = 15
# Played from the start: the declarer takes the first, third to seventh tricks and the opponents the second.
FIRST_TWO_TRICKS = game_of("S7 S9 D7 / H7 DJ CJ")
FIRST_SEVEN_TRICKS = game_of(
    "S7 S9 D7 / H7 DJ CJ / S8 ST D8 / SQ D9 C7 / SK DT C8",
    "SA DQ C9 / SJ HJ CT",
)
ALL_LEVELS = ["spiel", "hand", "schneider", "schwarz"]


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


def throw_down(table, position, *, body=None):
    return table.act(TABLE_THROW_DOWN_SUFFIX, table.at[position], body=body)


def result_of(table, position):
    answer = throw_down(table, position)
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def shown(result, *keys):
    return {key: result[key] for key in keys}


class TestTheEnding:
    @pytest.mark.parametrize(
        ("position", "seat"),
        [
            pytest.param(MIDDLEHAND, 1, id="the-declarer"),
            pytest.param(REARHAND, 2, id="the-opponent-in-seat-two"),
            pytest.param(FOREHAND, 3, id="the-opponent-in-seat-three"),
        ],
    )
    def test_the_answer_and_every_chair_and_the_watcher_read_the_seat_that_threw_down(self, herz_hand, position, seat):
        assert ending_of(result_of(herz_hand, position)) == ("thrown-down", seat)
        assert herz_hand.endings_in_every_view() == {("thrown-down", seat)}


class TestTheDeclarerThrowsDown:
    def test_with_ten_cards_the_skat_alone_is_his_and_the_game_is_lost_with_every_level(self, herz_hand):
        result = result_of(herz_hand, MIDDLEHAND)

        assert herz_hand.record.hand is None
        assert shown(
            result,
            "won",
            "declarer_points",
            "opponents_points",
            "levels",
            "game_value",
            "score",
            "multiplier",
            "list_bonus",
            "announcement_missed",
        ) == {
            "won": False,
            "declarer_points": SKAT_POINTS,
            "opponents_points": ALL_POINTS - SKAT_POINTS,
            "levels": ALL_LEVELS,
            "game_value": 50,
            "score": -100,
            "multiplier": 5,
            "list_bonus": -50,
            "announcement_missed": False,
        }

    def test_with_the_completed_tricks_and_the_skat_reaching_sixty_one_the_game_is_won_at_the_levels_reached(
        self, herz_hand
    ):
        herz_hand.played_out(FIRST_SEVEN_TRICKS)

        result = result_of(herz_hand, MIDDLEHAND)

        # The declarer's tricks hold 0 + 10 + 3 + 14 + 14 + 14 = 55 and the skat 15; the opponents' one trick 4.
        assert shown(result, "won", "declarer_points", "opponents_points", "levels", "multiplier", "list_bonus") == {
            "won": True,
            "declarer_points": 70,
            "opponents_points": 50,
            "levels": ["spiel", "hand"],
            "multiplier": 3,
            "list_bonus": 50,
        }
        assert result["announcement_missed"] is False

    def test_the_ten_he_leads_counts_for_the_opponents(self, herz_hand):
        herz_hand.played_out(game_of("S7 S9 D7"))
        herz_hand.accepted(card("ST"))

        result = result_of(herz_hand, MIDDLEHAND)

        assert (result["declarer_points"], result["opponents_points"]) == (SKAT_POINTS, ALL_POINTS - SKAT_POINTS)

    def test_with_eight_cards_he_needs_no_consent(self, herz_hand):
        herz_hand.played_out(FIRST_TWO_TRICKS)

        result = result_of(herz_hand, MIDDLEHAND)

        assert (result["won"], result["declarer_points"]) == (False, SKAT_POINTS)


class TestANull:
    @pytest.mark.parametrize(
        ("position", "won", "score", "declarer_points"),
        [
            pytest.param(MIDDLEHAND, False, -70, 0, id="the-declarer-throws-down-and-loses-with-no-skat-points"),
            pytest.param(FOREHAND, True, 35, ALL_POINTS, id="an-opponent-throws-down-and-the-declarer-wins"),
        ],
    )
    def test_a_null_is_settled_at_its_fixed_value_without_matadors(self, table, position, won, score, declarer_points):
        table.declared_hand_game(GameToken.NULL)

        result = result_of(table, position)

        assert shown(result, "won", "declarer_points", "matadors", "game_value", "score") == {
            "won": won,
            "declarer_points": declarer_points,
            "matadors": None,
            "game_value": 35,
            "score": score,
        }


class TestAnOpponentThrowsDown:
    def test_before_the_first_card_the_declarer_wins_the_whole_deal_with_every_level(self, herz_hand):
        result = result_of(herz_hand, FOREHAND)

        assert shown(
            result,
            "won",
            "declarer_points",
            "opponents_points",
            "levels",
            "game_value",
            "score",
            "multiplier",
            "list_bonus",
            "announcement_missed",
        ) == {
            "won": True,
            "declarer_points": ALL_POINTS,
            "opponents_points": 0,
            "levels": ALL_LEVELS,
            "game_value": 50,
            "score": 50,
            "multiplier": 5,
            "list_bonus": 50,
            "announcement_missed": False,
        }

    def test_the_opponents_keep_exactly_the_points_of_their_completed_tricks(self, herz_hand):
        herz_hand.played_out(FIRST_TWO_TRICKS)

        result = result_of(herz_hand, REARHAND)

        # The opponents' one trick holds 0 + 2 + 2 = 4: the declarer reaches 116, Schneider but no Schwarz.
        assert shown(result, "declarer_points", "opponents_points", "levels", "multiplier") == {
            "declarer_points": ALL_POINTS - 4,
            "opponents_points": 4,
            "levels": ["spiel", "hand", "schneider"],
            "multiplier": 4,
        }

    @pytest.mark.parametrize("position", [FOREHAND, REARHAND], ids=lambda position: position.name)
    def test_either_opponent_off_turn_in_the_middle_of_a_trick_ends_the_same_game(self, table, position):
        table.declared_hand_game()
        table.accepted(card("CA"))
        assert table.record.progress.plays

        result = result_of(table, position)

        assert (result["won"], result["declarer_points"], result["opponents_points"]) == (True, ALL_POINTS, 0)

    def test_the_skat_never_changes_the_answer(self, skat):
        swapped = sorted((each for each in FOREHAND_CARDS if each.rank is not Rank.JACK), key=lambda each: -each.points)
        other_skat = tuple(swapped[:2])
        assert points_of_cards(other_skat) != SKAT_POINTS
        other_forehand = tuple(each for each in FOREHAND_CARDS if each not in other_skat) + KNOWN_DEAL.skat
        results = []
        for deal in (
            KNOWN_DEAL,
            replace(KNOWN_DEAL, forehand=other_forehand, skat=other_skat),
        ):
            table = Table(skat)
            table.with_deal(deal)
            table.declared_hand_game()
            results.append(result_of(table, FOREHAND))

        assert results[0] == results[1]


class TestWhatTheEndLeaves:
    def test_the_entry_is_stored_and_the_gains_follow(self, herz_hand):
        result = result_of(herz_hand, MIDDLEHAND)

        assert len(herz_hand.record.game_list) == 1
        assert herz_hand.result() == result
        assert [gain["won"] for gain in result["gains"]] == [False, True, True]
        assert result["gains"][0]["gain"] < 0 < result["gains"][1]["gain"]

    @pytest.mark.parametrize("position", [MIDDLEHAND, FOREHAND], ids=lambda position: position.name)
    def test_an_ouvert_declarers_cards_go_with_the_hand_and_every_viewer_reads_the_same_result(self, table, position):
        table.declared_grand_ouvert()
        table.accepted(card("S7"))

        result = result_of(table, position)

        for headers in (table.watcher, *table.at.values()):
            answer = table.read_as(headers)
            assert cards_in_text(answer.text) == set()
            assert answer.json()["result"] == result
