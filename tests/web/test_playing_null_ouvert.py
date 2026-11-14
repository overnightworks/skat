from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from skat.engine.deal import Deal
from skat.table.records import Refusal
from skat.web.declaration_tokens import GameToken
from tests.support.payload_cards import cards_in_text, wire_cards
from tests.web.support.playing import (
    FOREHAND,
    MIDDLEHAND,
    REARHAND,
    Table,
    card,
    cards,
    gains,
    game_of,
    result_fields,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from skat.engine.cards import Card

# Null ouvert is worth 46 and Null ouvert Hand 59 whatever the hand; a lost game scores double.
# A Null game has no matadors and no levels. The declarer is middlehand and sits in seat 1.


@dataclass(frozen=True)
class NullOuvertGame:
    deal: Deal
    declare: Callable[[Table], None]
    played: tuple[Card, ...]
    result: dict[str, object]

    def reach_the_end(self, table):
        table.with_deal(self.deal)
        self.declare(table)
        table.played_out(self.played)


def null_ouvert_result(**changed):
    return result_fields(
        game="null", ouvert=True, matadors=None, base_value=None, levels=[], multiplier=None, **changed
    )


def declared_picked_up(put_back):
    return lambda table: table.declared_after_putting_back(cards(put_back), GameToken.NULL, ouvert=True)


def declared_in_hand(table):
    table.declared_hand_game(GameToken.NULL, ouvert=True)


# The declarer keeps only sevens, eights and nines of clubs, spades and hearts, so every trick but a diamond one
# goes to an opponent, who leads the next: forehand takes trick 3 with the Pik ace only to lead the Kreuz ace.
PICKED_UP_WON = NullOuvertGame(
    deal=Deal(
        forehand=cards("CT CQ CA ST SQ SA HT HQ D8 DT"),
        middlehand=cards("C7 C8 C9 S7 S8 S9 H7 H8 H9 D7"),
        rearhand=cards("CJ CK SJ SK HJ HK HA D9 DJ DQ"),
        skat=cards("DA DK"),
    ),
    declare=declared_picked_up("DA DK"),
    played=game_of(
        "CT C7 CJ / CK CQ C8 / SK SA S7 / CA C9 D9 / ST S8 SJ",
        "HK HQ H7 / HA HT H8 / HJ D8 H9 / DQ DT D7 / DJ SQ S9",
    ),
    # The declarer takes the two put-back cards' points only: ace 11 and king 4.
    result=null_ouvert_result(
        won=True,
        list_bonus=50,
        game_value=46,
        settled_value=46,
        score=46,
        declarer_points=15,
        opponents_points=105,
        gains=gains(96, 0),
    ),
)

# Middlehand keeps the Karo king instead of the seven, which beats every opponent diamond: he takes trick 3. The
# opponents took 12 points in trick 1 (Zehn, Sieben, Bube) and 7 in trick 2 (Koenig, Dame, Acht), so the rest is his.
PICKED_UP_LOST = NullOuvertGame(
    deal=Deal(
        forehand=cards("CT CQ CA ST SQ SA HT HQ D8 DT"),
        middlehand=cards("C7 C8 C9 S7 S8 S9 H7 H8 H9 DK"),
        rearhand=cards("CJ CK SJ SK HJ HK HA D9 DJ DQ"),
        skat=cards("DA D7"),
    ),
    declare=declared_picked_up("DA D7"),
    played=game_of("CT C7 CJ / CK CQ C8 / DQ DT DK"),
    result=null_ouvert_result(
        doubled=True,
        won=False,
        list_bonus=-50,
        game_value=46,
        settled_value=46,
        score=-92,
        declarer_points=101,
        opponents_points=19,
        gains=gains(-142, 40),
    ),
)

# The declarer takes the two skat cards' points only, the Bube and the eight: 2.
HAND_WON = NullOuvertGame(
    deal=Deal(
        forehand=cards("HK SK DT CA HJ HA DQ HQ C9 H7"),
        middlehand=cards("DK C8 D7 HT H8 SA ST SJ CT S7"),
        rearhand=cards("D9 SQ DA CJ H9 S9 CK CQ C7 S8"),
        skat=cards("DJ D8"),
    ),
    declare=declared_in_hand,
    played=game_of(
        "HA H8 H9 / DQ D7 D9 / HJ HT S9 / H7 S7 CQ / C9 C8 CK",
        "DA DT DK / C7 CA CT / SK ST SQ / HQ SJ CJ / HK SA S8",
    ),
    result=null_ouvert_result(
        hand=True,
        won=True,
        list_bonus=50,
        game_value=59,
        settled_value=59,
        score=59,
        declarer_points=2,
        opponents_points=118,
        gains=gains(109, 0),
    ),
)

# Forehand leads the Karo nine, middlehand takes it with the Dame and so the first trick: the Null is lost at once.
HAND_LOST = NullOuvertGame(
    deal=Deal(
        forehand=cards("D9 H8 ST S9 DJ C8 CQ CJ CA H7"),
        middlehand=cards("S8 HT DK SQ HK C7 HQ DQ CK SJ"),
        rearhand=cards("HJ HA SK SA CT DA C9 D7 D8 DT"),
        skat=cards("H9 S7"),
    ),
    declare=declared_in_hand,
    played=game_of("D9 DQ D7"),
    result=null_ouvert_result(
        hand=True,
        doubled=True,
        won=False,
        list_bonus=-50,
        game_value=59,
        settled_value=59,
        score=-118,
        declarer_points=120,
        opponents_points=0,
        gains=gains(-168, 40),
    ),
)

EVERY_GAME = [
    pytest.param(PICKED_UP_WON, id="null-ouvert-won"),
    pytest.param(PICKED_UP_LOST, id="null-ouvert-lost-at-the-third-trick"),
    pytest.param(HAND_WON, id="null-ouvert-hand-won"),
    pytest.param(HAND_LOST, id="null-ouvert-hand-lost-at-the-first-trick"),
]
EARLY_ENDS = [EVERY_GAME[1], EVERY_GAME[3]]


@pytest.fixture
def table(skat):
    return Table(skat)


class TestNullOuvertReachesItsResult:
    @pytest.mark.parametrize("game", EVERY_GAME)
    def test_the_game_ends_at_the_declarers_first_trick_or_its_tenth_and_scores_its_fixed_value(self, table, game):
        game.reach_the_end(table)

        assert table.result() == game.result
        assert table.record.hand is None


class TestAfterAnEarlyEnd:
    @pytest.mark.parametrize("game", EARLY_ENDS)
    def test_no_viewer_sees_a_card_that_was_not_played_apart_from_the_declarers_open_cards(self, table, game):
        game.reach_the_end(table)
        declarers_open_cards = game.deal.middlehand
        allowed = wire_cards({*game.played, *declarers_open_cards})
        viewers = [table.at[FOREHAND], table.at[MIDDLEHAND], table.at[REARHAND], table.watcher]

        seen = [cards_in_text(table.read_as(headers).text) for headers in viewers]

        assert [found - allowed for found in seen] == [set()] * len(viewers)
        assert [found & wire_cards(game.deal.skat) for found in seen] == [set()] * len(viewers)

    @pytest.mark.parametrize("game", EARLY_ENDS)
    def test_the_answer_to_the_ending_card_names_no_card_that_was_not_played(self, table, game):
        table.with_deal(game.deal)
        game.declare(table)
        table.played_out(game.played[:-1])
        allowed = wire_cards({*game.played, *game.deal.middlehand})

        answer = table.accepted(game.played[-1])

        assert cards_in_text(answer.text) - allowed == set()
        assert cards_in_text(answer.text) & wire_cards(game.deal.skat) == set()

    @pytest.mark.parametrize("game", EARLY_ENDS)
    def test_a_card_after_the_end_is_refused_and_the_result_stays(self, table, game):
        game.reach_the_end(table)

        table.refused(table.at[FOREHAND], card("S7"), Refusal.NO_HAND)

        assert table.result() == game.result
