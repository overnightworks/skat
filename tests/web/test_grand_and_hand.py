import pytest

from skat.engine.deal import Deal
from skat.engine.tricks import PlayRefusal
from skat.table.hand_state import playing_of
from skat.web.declaring import AnnouncementToken, GameToken
from skat.web.tables import TABLES_PATH
from tests.web.support.playing import MIDDLEHAND, Table, card, cards, game_of

# Middlehand declares in every game below; seats 1, 2, 3 are middlehand, rearhand, forehand.
DECLARER_SEAT = 1
GRAND = "grand"


@pytest.fixture
def table(skat):
    return Table(skat)


def result_of(table):
    table.skat.client.cookies.clear()
    answer = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}", headers=table.watcher)
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def result_fields(**changed):
    """A result answer for a plain first game of the declarer in seat 1; a test names what differs."""
    plain = {
        "ordinal": 1,
        "declarer_seat": DECLARER_SEAT,
        "hand": False,
        "ouvert": False,
        "announcement": "none",
        "schneider": False,
        "schwarz": False,
        "overbid": False,
        "bid": 18,
    }
    return plain | changed


def gains(declarer, each_opponent):
    return [
        {"seat": 1, "gain": declarer},
        {"seat": 2, "gain": each_opponent},
        {"seat": 3, "gain": each_opponent},
    ]


class TestGrandAndHandGamesReachTheirResult:
    def test_a_grand_after_taking_the_skat_is_won_with_the_matadors_the_skat_completes(self, table):
        # The skat holds the Kreuz jack, so middlehand has Kreuz, Pik and Herz jacks without the Karo jack: mit 3.
        # Spiel adds 1: (3 + 1) x 24 = 96. Won, so the score is 96 and the declarer gains 96 + 50 = 146.
        # Declarer points: tricks 3 to 8 are 64, the two cards put back (CQ 3, HK 4) add 7, so 71; opponents 120 - 71.
        table.with_deal(
            Deal(
                forehand=cards("DJ C7 SQ SK HA HQ CK S7 DA H7"),
                middlehand=cards("DT SJ CT D7 HK CA HJ CQ S9 D8"),
                rearhand=cards("HT SA H8 DK DQ ST S8 H9 C8 D9"),
                skat=cards("C9 CJ"),
            )
        )
        table.declared_after_putting_back(cards("CQ HK"), GameToken.GRAND)

        table.played_out(
            game_of(
                "SK S9 SA / DQ DA DT / C7 CA C8 / CJ ST DJ / SJ H8 HA",
                "HJ D9 H7 / CT HT CK / C9 S8 S7 / D8 DK SQ / H9 HQ D7",
            )
        )

        assert result_of(table) == result_fields(
            game=GRAND,
            matadors={"mit": True, "count": 3},
            won=True,
            game_value=96,
            settled_value=96,
            score=96,
            declarer_points=71,
            opponents_points=49,
            gains=gains(146, 0),
        )

    def test_a_grand_hand_game_counts_the_hand_level_and_is_won(self, table):
        # Middlehand holds the Pik jack but not the Kreuz jack: ohne 1. Spiel and Hand add 2: (1 + 2) x 24 = 72.
        # Won, so the declarer gains 72 + 50 = 122.
        # Declarer points: tricks 1, 4, 5, 6 and 7 are 6 + 15 + 6 + 21 + 7 = 55,
        # the skat's CA SA add 22, so 77; opponents 120 - 77.
        table.with_deal(
            Deal(
                forehand=cards("CJ CT HK D8 S9 CK ST S8 SK DT"),
                middlehand=cards("HA H9 DA CQ HJ S7 DK D7 SQ SJ"),
                rearhand=cards("DQ C7 HQ DJ HT C9 D9 H7 H8 C8"),
                skat=cards("CA SA"),
            )
        )
        table.declared_hand_game(GameToken.GRAND)

        table.played_out(
            game_of(
                "S8 SQ DQ / SJ DJ CJ / S9 S7 H7 / HK HA H8 / HJ C7 SK",
                "DA D9 DT / DK HQ D8 / CQ C9 CK / CT H9 C8 / ST D7 HT",
            )
        )

        assert result_of(table) == result_fields(
            game=GRAND,
            hand=True,
            matadors={"mit": False, "count": 1},
            won=True,
            game_value=72,
            settled_value=72,
            score=72,
            declarer_points=77,
            opponents_points=43,
            gains=gains(122, 0),
        )

    def test_a_hand_game_whose_skat_jack_lowers_its_value_below_the_bid_is_lost_overbid(self, table):
        # Karo Hand at 54 is ohne 4 (6 x 9). The skat holds the Kreuz jack, so the game is mit 1:
        # Spiel and Hand add 2, (1 + 2) x 9 = 27 < 54. Overbid: the value rises to 54, lost and doubled, score -108;
        # the declarer gains -108 - 50 = -158 and each opponent 40.
        # Declarer points: tricks 1, 2, 3, 5 and 9 are 13 + 21 + 25 + 11 + 3 = 73,
        # the skat's CJ S7 add 2, so 75 (more than 60); opponents 120 - 75.
        table.with_deal(
            Deal(
                forehand=cards("S8 C8 H7 C9 DJ S9 D8 CT HT DQ"),
                middlehand=cards("DA CQ ST SK HK DK H9 CA HA D9"),
                rearhand=cards("DT D7 H8 SA C7 SQ CK HQ SJ HJ"),
                skat=cards("CJ S7"),
            )
        )
        table.declared_hand_game(GameToken.KARO, bid=54)

        table.played_out(
            game_of(
                "S9 ST SQ / DA DT D8 / CA CK CT / H9 HQ HT / H7 HA H8",
                "SK SA S8 / SJ DQ DK / D7 DJ D9 / C9 CQ C7 / HK HJ C8",
            )
        )

        assert result_of(table) == result_fields(
            game="karo",
            hand=True,
            matadors={"mit": True, "count": 1},
            won=False,
            overbid=True,
            bid=54,
            game_value=27,
            settled_value=54,
            score=-108,
            declarer_points=75,
            opponents_points=45,
            gains=gains(-158, 40),
        )

    def test_a_suit_game_that_misses_its_announced_schneider_is_lost_at_the_announced_level(self, table):
        # Kreuz Hand is mit 2 (Kreuz and Pik jacks, no Herz jack). Spiel 1, Hand 1, Schneider 1 and Schneider
        # angesagt 1 make 4: (2 + 4) x 12 = 72. The declarer has 86 points but the opponents keep 34, over 30, so
        # Schneider is missed: lost, score -144, the declarer gains -144 - 50 = -194 and each opponent 40.
        # Declarer points: tricks 1, 2, 3, 5, 8, 9 and 10 are 25 + 14 + 6 + 11 + 10 + 7 + 7 = 80,
        # the skat's SQ HQ add 6.
        table.with_deal(
            Deal(
                forehand=cards("CK ST HK HT DJ H7 CT H9 D7 DK"),
                middlehand=cards("SJ D8 CA S8 S9 HA DA CQ C8 CJ"),
                rearhand=cards("H8 HJ D9 DT C9 C7 S7 SK DQ SA"),
                skat=cards("SQ HQ"),
            )
        )
        table.declared_hand_game(GameToken.KREUZ, announcement=AnnouncementToken.SCHNEIDER)

        table.played_out(
            game_of(
                "DK DA DT / CJ HJ CT / SJ C9 CK / CA C7 DJ / H9 HA H8",
                "S8 SA ST / D9 D7 D8 / S7 HT S9 / CQ SK H7 / C8 DQ HK",
            )
        )

        assert result_of(table) == result_fields(
            game="kreuz",
            hand=True,
            announcement="schneider",
            schneider=True,
            matadors={"mit": True, "count": 2},
            won=False,
            game_value=72,
            settled_value=72,
            score=-144,
            declarer_points=86,
            opponents_points=34,
            gains=gains(-194, 40),
        )

    def test_a_grand_ouvert_in_which_the_declarer_loses_a_trick_is_lost_at_the_schwarz_announced_level(self, table):
        # Grand ouvert is mit 2 (Kreuz and Pik jacks, no Herz jack). Spiel 1, Hand 1, Schneider 1, Schneider angesagt 1,
        # Schwarz 1, Schwarz angesagt 1 and ouvert 1 make 7: (2 + 7) x 24 = 216. The declarer loses the last trick
        # (ST 10, SQ 3), so he has 120 - 13 = 107 points but no Schwarz: lost, score -432, he gains -432 - 50 = -482.
        table.with_deal(
            Deal(
                forehand=cards("H7 D7 C7 SQ HT S9 DJ CQ C9 H8"),
                middlehand=cards("C8 CT CJ HA H9 SJ S8 DT CA HK"),
                rearhand=cards("SK D8 DQ DA HQ CK ST HJ SA S7"),
                skat=cards("DK D9"),
            )
        )
        table.declared_grand_ouvert()

        table.played_out(
            game_of(
                "C9 CA CK / CJ HJ DJ / SJ SK CQ / HA HQ HT / CT SA C7",
                "DT D8 D7 / HK DQ H7 / C8 DA S9 / H9 S7 H8 / S8 ST SQ",
            )
        )

        assert result_of(table) == result_fields(
            game=GRAND,
            hand=True,
            ouvert=True,
            announcement="schwarz",
            schneider=True,
            schwarz=True,
            matadors={"mit": True, "count": 2},
            won=False,
            game_value=216,
            settled_value=216,
            score=-432,
            declarer_points=107,
            opponents_points=13,
            gains=gains(-482, 40),
        )


class TestAJackInGrand:
    def test_a_jack_played_to_a_lead_of_its_printed_suit_is_refused_and_stays_in_the_hand(self, table):
        # Forehand leads SK. In Grand only the jacks are trump, so middlehand's SJ is trump and does not follow Pik.
        table.with_deal(
            Deal(
                forehand=cards("C7 C8 C9 CT CJ CQ CK CA SK S8"),
                middlehand=cards("S9 ST SJ SQ S7 SA H7 H8 H9 HT"),
                rearhand=cards("HJ HQ HK HA D7 D8 D9 DT DJ DQ"),
                skat=cards("DK DA"),
            )
        )
        table.declared_hand_game(GameToken.GRAND)
        table.accepted(card("SK"))

        table.refused(table.at[MIDDLEHAND], card("SJ"), PlayRefusal.MUST_FOLLOW)

        assert card("SJ") in playing_of(table.record).hands[MIDDLEHAND]
