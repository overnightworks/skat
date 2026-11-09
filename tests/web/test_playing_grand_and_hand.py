import pytest

from skat.engine.deal import Deal
from skat.engine.tricks import PlayRefusal
from skat.table.auction import AuctionAction
from skat.table.hand_state import playing_of
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.declaring import AnnouncementToken, GameToken
from skat.web.tables import TABLES_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import FOREHAND, MIDDLEHAND, REARHAND, Table, card, cards, game_of

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
        "doubled": False,
        "overbid": False,
        "bid": 18,
    }
    return plain | changed


def gains(declarer, each_opponent):
    """The opponents gain only from a lost game, which is the declarer's loss."""
    declarer_won = each_opponent == 0
    return [
        {"seat": 1, "gain": declarer, "won": declarer_won},
        {"seat": 2, "gain": each_opponent, "won": not declarer_won},
        {"seat": 3, "gain": each_opponent, "won": not declarer_won},
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
            base_value=24,
            levels=["spiel"],
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
            base_value=24,
            levels=["spiel", "hand"],
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
            base_value=9,
            levels=["spiel", "hand"],
            doubled=True,
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
            base_value=12,
            levels=["spiel", "hand", "schneider", "schneider_announced"],
            doubled=True,
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
            base_value=24,
            levels=["spiel", "hand", "schneider", "schneider_announced", "schwarz", "schwarz_announced", "ouvert"],
            doubled=True,
            won=False,
            game_value=216,
            settled_value=216,
            score=-432,
            declarer_points=107,
            opponents_points=13,
            gains=gains(-482, 40),
        )

    def test_a_won_suit_game_mit_two_counts_the_spiel_level_only(self, table):
        # Herz is mit 2 (Kreuz and Pik jacks, no Herz jack). Spiel adds 1: (2 + 1) x 10 = 30; won, so the score is 30
        # and the declarer gains 30 + 50 = 80. Declarer points: 78; opponents 120 - 78.
        table.with_deal(
            Deal(
                forehand=cards("DK HK HA C9 CQ SQ CA DA S8 HQ"),
                middlehand=cards("D9 DJ H7 SJ CJ SK C8 S7 ST C7"),
                rearhand=cards("CT DQ S9 HT D7 CK H8 D8 HJ SA"),
                skat=cards("DT H9"),
            )
        )
        table.declared_after_putting_back(cards("D9 C8"))

        table.played_out(
            game_of(
                "S8 ST S9 / CJ HJ HQ / SJ HT HA / DJ H8 HK / H9 CK DA",
                "H7 D7 CQ / DT D8 DK / SK SA SQ / DQ C9 S7 / CT CA C7",
            )
        )

        assert result_of(table) == result_fields(
            game="herz",
            matadors={"mit": True, "count": 2},
            base_value=10,
            levels=["spiel"],
            won=True,
            game_value=30,
            settled_value=30,
            score=30,
            declarer_points=78,
            opponents_points=42,
            gains=gains(80, 0),
        )

    def test_a_lost_suit_game_ohne_three_counts_doubled_and_the_opponents_gain_forty_each(self, table):
        # Herz is ohne 3 (no Kreuz, Pik or Herz jack). Spiel adds 1: (3 + 1) x 10 = 40. The declarer has 31 points, so
        # the game is lost without Schneider: score -80, he gains -80 - 50 = -130 and each opponent 40.
        table.with_deal(
            Deal(
                forehand=cards("CA HA SJ DA DK CK HQ HJ DT S7"),
                middlehand=cards("C8 DJ H8 SK SQ HT DQ H9 CQ HK"),
                rearhand=cards("C9 S9 H7 CT CJ D9 SA ST D8 D7"),
                skat=cards("S8 C7"),
            )
        )
        table.declared_after_putting_back(cards("C8 S8"))

        table.played_out(
            game_of(
                "SJ DJ CJ / ST S7 SK / C9 CA CQ / DK DQ D9 / DT HT D7",
                "HK H7 HJ / CK C7 CT / D8 DA H9 / H8 S9 HQ / HA SQ SA",
            )
        )

        assert result_of(table) == result_fields(
            game="herz",
            matadors={"mit": False, "count": 3},
            base_value=10,
            levels=["spiel"],
            doubled=True,
            won=False,
            game_value=40,
            settled_value=40,
            score=-80,
            declarer_points=31,
            opponents_points=89,
            gains=gains(-130, 40),
        )

    def test_a_grand_hand_game_with_schneider_announced_and_reached_counts_both_schneider_levels(self, table):
        # Grand Hand is mit 1 (Kreuz jack, no Pik jack). Spiel, Hand, Schneider and Schneider angesagt make 4:
        # (1 + 4) x 24 = 120. The declarer has 93 points, the opponents 27: Schneider reached, won, he gains 170.
        table.with_deal(
            Deal(
                forehand=cards("C8 SQ CQ C9 D8 HT H7 CA DA D9"),
                middlehand=cards("D7 HQ CJ DK S7 CK HA DT DQ SA"),
                rearhand=cards("H9 S9 SJ H8 S8 ST DJ HK SK CT"),
                skat=cards("C7 HJ"),
            )
        )
        table.declared_hand_game(GameToken.GRAND, announcement=AnnouncementToken.SCHNEIDER)

        table.played_out(
            game_of(
                "CA CK CT / HT HA HK / CJ SJ DA / SA SK SQ / DT H8 D8",
                "DK ST D9 / HQ H9 H7 / DQ S8 C9 / D7 S9 CQ / S7 DJ C8",
            )
        )

        assert result_of(table) == result_fields(
            game=GRAND,
            hand=True,
            announcement="schneider",
            schneider=True,
            matadors={"mit": True, "count": 1},
            base_value=24,
            levels=["spiel", "hand", "schneider", "schneider_announced"],
            won=True,
            game_value=120,
            settled_value=120,
            score=120,
            declarer_points=93,
            opponents_points=27,
            gains=gains(170, 0),
        )

    def test_a_won_suit_game_in_which_the_opponents_take_no_trick_counts_schneider_and_schwarz_unannounced(self, table):
        # Herz is mit 3 (Kreuz, Pik and Herz jacks, the Karo jack is missing). Spiel, Schneider and Schwarz
        # make 3: (3 + 3) x 10 = 60. The declarer takes all 120 points, so he gains 60 + 50 = 110.
        table.with_deal(
            Deal(
                forehand=cards("SQ C9 HT DT DJ HQ SK CK CQ SA"),
                middlehand=cards("SJ H9 CA C8 DK HJ H8 DA CJ CT"),
                rearhand=cards("HK C7 D7 H7 D8 HA DQ S7 ST S9"),
                skat=cards("S8 D9"),
            )
        )
        table.declared_after_putting_back(cards("C8 S8"))

        table.played_out(
            game_of(
                "CQ CA C7 / CJ HA DJ / SJ HK HQ / HJ H7 HT / H9 S7 DT",
                "H8 ST SA / DA D8 C9 / CT D7 CK / DK DQ SQ / D9 S9 SK",
            )
        )

        assert result_of(table) == result_fields(
            game="herz",
            schneider=True,
            schwarz=True,
            matadors={"mit": True, "count": 3},
            base_value=10,
            levels=["spiel", "schneider", "schwarz"],
            won=True,
            game_value=60,
            settled_value=60,
            score=60,
            declarer_points=120,
            opponents_points=0,
            gains=gains(110, 0),
        )

    def test_a_won_null_hand_game_has_a_fixed_value_and_no_base_matadors_or_levels(self, table):
        # Null Hand is worth 35 whatever the hand. The declarer takes two points only (no trick), so he wins:
        # score 35, he gains 35 + 50 = 85.
        table.with_deal(
            Deal(
                forehand=cards("HK SK DT CA HJ HA DQ HQ C9 H7"),
                middlehand=cards("DK C8 D7 HT H8 SA ST SJ CT S7"),
                rearhand=cards("D9 SQ DA CJ H9 S9 CK CQ C7 S8"),
                skat=cards("DJ D8"),
            )
        )
        table.declared_hand_game(GameToken.NULL)

        table.played_out(
            game_of(
                "HA H8 H9 / DQ D7 D9 / HJ HT S9 / H7 S7 CQ / C9 C8 CK",
                "DA DT DK / C7 CA CT / SK ST SQ / HQ SJ CJ / HK SA S8",
            )
        )

        assert result_of(table) == result_fields(
            game="null",
            hand=True,
            matadors=None,
            base_value=None,
            levels=[],
            won=True,
            game_value=35,
            settled_value=35,
            score=35,
            declarer_points=2,
            opponents_points=118,
            gains=gains(85, 0),
        )

    def test_an_overbid_null_hand_game_is_lost_at_the_cheapest_game_that_reaches_the_bid(self, table):
        # Null Hand is worth 35, the bid 36 is more. The twelve cards hold only the Pik jack, so every game is ohne 1
        # and Spiel adds 1: Kreuz (2 x 12 raised to 3 x 12) and Karo (2 x 9 raised to 4 x 9) reach 36, the others
        # more. The value rises to 36, lost and doubled, score -72; the declarer gains -72 - 50. Rearhand takes the
        # first trick (DA, 14 points) and middlehand the second with DK, which ends the Null: 120 - 14 = 106 points.
        table.with_deal(
            Deal(
                forehand=cards("D9 H8 ST S9 DJ C8 CQ CJ CA H7"),
                middlehand=cards("S8 HT DK SQ HK C7 HQ DQ CK SJ"),
                rearhand=cards("HJ HA SK SA CT DA C9 D7 D8 DT"),
                skat=cards("H9 S7"),
            )
        )
        table.declared_hand_game(GameToken.NULL, bid=36)

        table.played_out(game_of("D9 DQ DA / DT DJ DK"))

        assert result_of(table) == result_fields(
            game="null",
            hand=True,
            matadors=None,
            base_value=None,
            levels=[],
            doubled=True,
            won=False,
            overbid=True,
            bid=36,
            game_value=35,
            settled_value=36,
            score=-72,
            declarer_points=106,
            opponents_points=14,
            gains=gains(-122, 40),
        )

    def test_a_passed_in_hand_has_no_result(self, table):
        for position in (MIDDLEHAND, REARHAND, FOREHAND):
            answer = table.skat.client.post(
                f"{TABLES_PATH}/{table.table_id}{TABLE_AUCTION_SUFFIX}",
                json={"command_id": table.fresh_id(), "version": table.record.version, "action": AuctionAction.PASS},
                headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[position]},
            )
            assert answer.status_code == 200, answer.text

        assert result_of(table) is None


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
