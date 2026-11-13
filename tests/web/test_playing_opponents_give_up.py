from contextlib import contextmanager

import pytest

from skat.engine.deal import Deal, Position, next_dealer
from skat.table.game_list import GameEnding
from skat.table.records import Refusal
from skat.web.declaring import (
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
    AnnouncementToken,
    GameToken,
)
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.kontra import TABLE_KONTRA_SUFFIX, TABLE_NO_WORD_SUFFIX
from skat.web.mcp import AGREE_TO_GIVE_UP_TOOL, DECLINE_GIVE_UP_TOOL, GIVE_UP_GAME_TOOL
from skat.web.playing import (
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_THROW_DOWN_SUFFIX,
)
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import CARDS_BY_SEAT, DEALER_SEAT, KNOWN_DEAL, cards_in, cards_in_text, wire_cards
from tests.web.support.playing import Table, card, card_body, cards, ending_of, gains, game_of, three_pass
from tests.web.support.series import tap_weiter
from tests.web.support.skat import AgentTable, Skat, stored, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# Seats: the declarer (middlehand) sits in seat 1, rearhand in seat 2, forehand in seat 3.
SEAT = {MIDDLEHAND: 1, REARHAND: 2, FOREHAND: 3}
OPPONENTS = [pytest.param(FOREHAND, id="forehand"), pytest.param(REARHAND, id="rearhand")]
HERZ_GAME = game_of(
    "S7 S9 D7 / H7 DJ CJ / S8 ST D8 / SQ D9 C7 / SK DT C8",
    "SA DQ C9 / SJ HJ CT / H8 HQ CQ / HK CK H9 / HA CA HT",
)
# The declarer holds eight cards once he has played to the second trick, led with H7; rearhand is on turn.
EIGHT_CARDS = HERZ_GAME[:4]
# After seven tricks the declarer has taken 0 + 10 + 3 + 14 + 14 + 14 = 55 card points, and the skat (D K, D A) adds
# 4 + 11: 70 points win the game without Schneider.
SEVEN_TRICKS = HERZ_GAME[:21]
# Clubs and spades are the declarer's own: forehand and rearhand take the first two tricks, so a Null game runs on.
NULL_DEAL = Deal(
    forehand=cards("CT CQ CA ST SQ SA HT HQ D8 DT"),
    middlehand=cards("C7 C8 C9 S7 S8 S9 H7 H8 H9 D7"),
    rearhand=cards("CJ CK SJ SK HJ HK HA D9 DJ DQ"),
    skat=cards("DA DK"),
)
# The opponents took 10 + 2 and 4 + 3 points, so the declarer holds 120 - 19 = 101.
NULL_TWO_TRICKS = game_of("CT C7 CJ / CK CQ C8")
# Forehand leads an ace, and the partner adds a ten each time: three tricks of 11 + 10 + 0 = 21 points. The declarer
# holds the Spade Jack and not the Kreuz Jack, so Herz is played "ohne 1".
HEAVY_DEAL = Deal(
    forehand=cards("CA CJ SA DA HA HK HQ H9 H8 CK"),
    middlehand=cards("C7 C8 C9 S7 S8 S9 SJ H7 D7 D8"),
    rearhand=cards("CT CQ ST SK SQ HJ HT DT DJ DQ"),
    skat=cards("D9 DK"),
)
HEAVY_TWO_TRICKS = game_of("CA C7 CT / SA S7 ST")
HEAVY_THREE_TRICKS = game_of("CA C7 CT / SA S7 ST / DA D7 DT")
HERZ_HAND_RESULT = {
    "won": True,
    "game_value": 30,
    "settled_value": 30,
    "score": 30,
    "multiplier": 3,
    "list_bonus": 50,
    "schneider": False,
    "schwarz": False,
    "declarer_points": 120,
    "opponents_points": 0,
}


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


@pytest.fixture
def eight_cards(herz_hand):
    herz_hand.played_out(EIGHT_CARDS)
    return herz_hand


@pytest.fixture
def kontra_table(skat):
    options = {"kontra": {"sayer": "any-opponent", "reach": "up-to-hirsch", "deadline": "own-card"}}
    table = Table(skat, options=options)
    table.declared_hand_game()
    return table


def asked_by(position):
    return {"asking_seat": SEAT[position], "declined_seat": None}


def give_up(table, position, *, body=None):
    return table.act(TABLE_GIVE_UP_SUFFIX, table.at[position], body=body)


def gives_up(table, position):
    answer = give_up(table, position)
    assert answer.status_code == 200, answer.text
    return answer


def agree(table, *, body=None):
    return table.act(TABLE_GIVE_UP_AGREE_SUFFIX, table.at[MIDDLEHAND], body=body)


def decline(table, *, body=None):
    return table.act(TABLE_GIVE_UP_DECLINE_SUFFIX, table.at[MIDDLEHAND], body=body)


def accepted_end(table):
    answer = agree(table)
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def playing_as(table, headers):
    answer = table.read_as(headers)
    assert answer.status_code == 200, answer.text
    return answer.json()["hand"]["playing"]


def everyone_reads(table):
    return [playing_as(table, headers)["give_up"] for headers in (table.watcher, *table.at.values())]


@contextmanager
def everyones_streams(table):
    """One open stream per viewer, the watcher first: each as (position or None for the watcher, decoded messages)."""
    viewers = [(None, table.watcher), *table.at.items()]
    with streams_of(table.skat, table.table_id, [(headers, None) for _, headers in viewers]) as streams:
        yield [(position, stream) for (position, _), stream in zip(viewers, streams, strict=True)]


def own_cards_of(position):
    """The cards a viewer's frame may carry before any card is played: his own hand, none for the watcher."""
    return set() if position is None else wire_cards(CARDS_BY_SEAT[SEAT[position]])


def series_list_of(table):
    """The numbered entries the series list shows a watcher, as (number, settled value, score)."""
    table.skat.client.cookies.clear()
    listing = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher)
    return [(row["number"], row["settled_value"], row["score"]) for row in listing.json()["entries"]]


def chair_totals_of(table):
    """The running total each chair shows a watcher, in seat order."""
    return [chair["total"] for chair in table.read_as(table.watcher).json()["chairs"]]


def shown(result, expected):
    return {key: result[key] for key in expected}


def declared_herz_at_22(table):
    """Herz played from the skat, declared below the bid: its simple value (1 + 1) * 10 = 20 is under 22."""
    table.middlehand_wins(22)
    for suffix, body in (
        (TABLE_DECLARING_TAKE_SUFFIX, None),
        (TABLE_DECLARING_PUT_BACK_SUFFIX, {"cards": [card_body(each) for each in cards("D9 DK")]}),
        (
            TABLE_DECLARING_DECLARE_SUFFIX,
            {"game": GameToken.HERZ, "hand": False, "ouvert": False, "announcement": AnnouncementToken.NONE},
        ),
    ):
        answer = table.act(suffix, body=body)
        assert answer.status_code == 200, answer.text


def undecided_herz_hand(table):
    table.declared_hand_game()


def undecided_herz_at_22(table):
    table.with_deal(HEAVY_DEAL)
    declared_herz_at_22(table)


def herz_at_22_with_42_points_against(table):
    undecided_herz_at_22(table)
    table.played_out(HEAVY_TWO_TRICKS)


def herz_hand_won_by_tricks_and_skat(table):
    table.declared_hand_game()
    table.played_out(SEVEN_TRICKS)


def herz_hand_with_63_points_against(table):
    table.with_deal(HEAVY_DEAL)
    table.declared_hand_game()
    table.played_out(HEAVY_THREE_TRICKS)


def null_hand_before_a_trick(table):
    table.with_deal(NULL_DEAL)
    table.declared_hand_game(GameToken.NULL)
    table.played_out(NULL_TWO_TRICKS)


def null_before_a_trick(table):
    table.with_deal(NULL_DEAL)
    table.declared_after_putting_back(cards("DA DK"), GameToken.NULL, ouvert=False)
    table.played_out(NULL_TWO_TRICKS)


class TestAnOpponentGivesUp:
    @pytest.mark.parametrize("position", OPPONENTS)
    @pytest.mark.parametrize(
        ("played_before", "on_turn"),
        [
            pytest.param((), FOREHAND, id="forehand-on-turn"),
            pytest.param(HERZ_GAME[:1], MIDDLEHAND, id="the-declarer-on-turn"),
            pytest.param(HERZ_GAME[:2], REARHAND, id="rearhand-on-turn"),
        ],
    )
    def test_the_game_waits_and_every_viewer_reads_the_opponent_and_the_player_on_turn_has_no_card_to_play(
        self, herz_hand, position, played_before, on_turn
    ):
        herz_hand.played_out(played_before)
        before = herz_hand.record

        answer = gives_up(herz_hand, position)

        assert herz_hand.record.version == before.version + 1
        assert herz_hand.record.hand is not None
        assert herz_hand.record.game_list == ()
        assert answer.json()["hand"]["playing"]["give_up"] == asked_by(position)
        assert everyone_reads(herz_hand) == [asked_by(position)] * 4
        assert playing_as(herz_hand, herz_hand.at[on_turn])["legal_cards"] == []

    def test_every_stream_carries_the_same_result_with_no_card_after_the_yes(self, herz_hand):
        with everyones_streams(herz_hand) as streams:
            gives_up(herz_hand, FOREHAND)
            for _, stream in streams:
                next(stream)

            accepted_end(herz_hand)

            frames = [next(stream) for _, stream in streams]
        assert [cards_in(frame) for frame in frames] == [set()] * 4
        assert {str(frame["result"]) for frame in frames} == {str(frames[0]["result"])}
        assert ending_of(frames[0]["result"]) == ("given-up", SEAT[FOREHAND])

    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_partners_give_up_and_his_own_again_change_nothing(self, herz_hand, position):
        gives_up(herz_hand, position)
        before = herz_hand.record
        partner = REARHAND if position is FOREHAND else FOREHAND

        for each in (partner, position):
            again = give_up(herz_hand, each)

            assert again.status_code == 200, again.text
            assert herz_hand.record == before
            assert everyone_reads(herz_hand) == [asked_by(position)] * 4

    def test_a_give_up_while_the_declarers_own_request_stands_is_pending(self, eight_cards):
        gives_up(eight_cards, MIDDLEHAND)

        eight_cards.refused_act(TABLE_GIVE_UP_SUFFIX, eight_cards.at[FOREHAND], Refusal.REQUEST_PENDING)
        assert everyone_reads(eight_cards) == [asked_by(MIDDLEHAND)] * 4


class TestTheDeclarerAccepts:
    @pytest.mark.parametrize("position", OPPONENTS)
    def test_a_game_not_yet_decided_is_won_as_declared_and_the_ending_names_the_opponent(self, herz_hand, position):
        gives_up(herz_hand, position)

        result = accepted_end(herz_hand)

        assert shown(result, HERZ_HAND_RESULT) == HERZ_HAND_RESULT
        assert ending_of(result) == ("given-up", SEAT[position])
        assert herz_hand.endings_in_every_view() == {("given-up", SEAT[position])}
        assert herz_hand.record.hand is None
        assert len(herz_hand.record.game_list) == 1

    @pytest.mark.parametrize(
        ("scene", "expected"),
        [
            pytest.param(
                undecided_herz_at_22,
                {
                    "won": True,
                    "bid": 22,
                    "game_value": 30,
                    "settled_value": 30,
                    "score": 30,
                    "multiplier": 3,
                    "declarer_points": 120,
                    "opponents_points": 0,
                    "gains": gains(80, 0),
                },
                id="undecided-the-bid-forces-schneider",
            ),
            pytest.param(
                herz_at_22_with_42_points_against,
                {
                    "won": False,
                    "bid": 22,
                    "overbid": True,
                    "game_value": 20,
                    "settled_value": 30,
                    "score": -60,
                    "declarer_points": 78,
                    "opponents_points": 42,
                    "gains": gains(-110, 40),
                },
                id="decided-lost-the-schneider-is-out-of-reach",
            ),
            pytest.param(
                herz_hand_won_by_tricks_and_skat,
                {
                    "won": True,
                    "game_value": 30,
                    "settled_value": 30,
                    "score": 30,
                    "list_bonus": 50,
                    "declarer_points": 70,
                    "opponents_points": 50,
                    "gains": gains(80, 0),
                },
                id="decided-won-with-the-skat-counted",
            ),
            pytest.param(
                herz_hand_with_63_points_against,
                {
                    "won": False,
                    "game_value": 30,
                    "settled_value": 30,
                    "score": -60,
                    "multiplier": 3,
                    "list_bonus": -50,
                    "declarer_points": 57,
                    "opponents_points": 63,
                    "gains": gains(-110, 40),
                },
                id="decided-lost-the-opponents-hold-more-than-sixty",
            ),
            pytest.param(
                null_hand_before_a_trick,
                {
                    "won": True,
                    "matadors": None,
                    "game_value": 35,
                    "settled_value": 35,
                    "score": 35,
                    "list_bonus": 50,
                    "declarer_points": 101,
                    "gains": gains(85, 0),
                },
                id="null-hand",
            ),
            pytest.param(
                null_before_a_trick,
                {
                    "won": True,
                    "matadors": None,
                    "game_value": 23,
                    "settled_value": 23,
                    "score": 23,
                    "list_bonus": 50,
                    "declarer_points": 101,
                    "gains": gains(73, 0),
                },
                id="null",
            ),
        ],
    )
    def test_the_game_is_scored_by_the_branch_its_state_takes(self, table, scene, expected):
        scene(table)
        gives_up(table, FOREHAND)

        result = accepted_end(table)

        assert shown(result, expected) == expected
        assert ending_of(result) == ("given-up", SEAT[FOREHAND])
        (entry,) = table.record.game_list
        assert (entry.won, entry.game_value, entry.settled_value, entry.score, entry.declarer_points) == (
            expected["won"],
            expected["game_value"],
            expected["settled_value"],
            expected["score"],
            expected["declarer_points"],
        )
        assert (entry.ending, entry.ended_by_seat) == (GameEnding.GIVEN_UP, SEAT[FOREHAND])
        assert series_list_of(table) == [(1, expected["settled_value"], expected["score"])]
        assert chair_totals_of(table) == [gain["gain"] for gain in expected["gains"]]
        assert table.result() == result

    def test_each_opponent_gives_up_the_same_state_for_the_same_result(self, skat):
        results = []
        for position in (FOREHAND, REARHAND):
            table = Table(skat)
            table.declared_hand_game()
            gives_up(table, position)
            results.append(accepted_end(table))

        assert [ending_of(result)[1] for result in results] == [SEAT[FOREHAND], SEAT[REARHAND]]
        assert {key: value for key, value in results[0].items() if key != "ended_by_seat"} == {
            key: value for key, value in results[1].items() if key != "ended_by_seat"
        }

    def test_two_deals_differing_in_the_skat_alone_answer_and_end_the_same(self, skat):
        swapped = Deal(
            forehand=KNOWN_DEAL.forehand,
            middlehand=KNOWN_DEAL.middlehand,
            rearhand=tuple(card("DA") if each == card("D9") else each for each in KNOWN_DEAL.rearhand),
            skat=(card("DK"), card("D9")),
        )
        reads, results = [], []
        for deal in (KNOWN_DEAL, swapped):
            table = Table(skat)
            table.with_deal(deal)
            table.declared_hand_game()
            table.played_out(EIGHT_CARDS)
            gives_up(table, FOREHAND)
            reads.append(everyone_reads(table))
            results.append(shown(accepted_end(table), HERZ_HAND_RESULT))

        assert reads[0] == reads[1] == [asked_by(FOREHAND)] * 4
        assert results[0] == results[1] == HERZ_HAND_RESULT

    def test_every_viewer_reads_the_same_result_and_no_card_after_the_end(self, table):
        table.declared_grand_ouvert()
        table.played_out(cards("S7 S9 D7 H7"))
        gives_up(table, FOREHAND)

        accepted_end(table)

        reads = [table.read_as(headers) for headers in (table.watcher, *table.at.values())]
        assert {tuple(sorted(cards_in_text(read.text))) for read in reads} == {()}
        assert len({str(read.json()["result"]) for read in reads}) == 1

    def test_the_words_said_before_double_the_score(self, kontra_table):
        answer = kontra_table.act(TABLE_KONTRA_SUFFIX, kontra_table.at[FOREHAND], body={"word": "kontra"})
        assert answer.status_code == 200, answer.text
        gives_up(kontra_table, REARHAND)

        result = accepted_end(kontra_table)

        assert (result["kontra"]["word"], result["score"]) == ("kontra", 60)

    def test_all_three_tapping_weiter_deal_the_next_hand(self, server):
        table = Table(server)
        table.declared_hand_game()
        gives_up(table, FOREHAND)
        accepted_end(table)

        with streams_of(server, table.table_id, [(headers, None) for headers in table.at.values()]):
            for number, headers in enumerate(table.at.values()):
                server.client.cookies.clear()
                assert tap_weiter(server, headers, table.table_id, f"command-weiter-{number}").status_code == 200

        assert table.record.hand is not None
        assert table.record.dealer == next_dealer(DEALER_SEAT)


class TestRefusalsAroundTheGiveUp:
    def test_an_opponents_give_up_while_a_chair_is_open_is_seat_open(self, herz_hand):
        assert herz_hand.skat.stand(herz_hand.at[REARHAND], herz_hand.table_id).status_code == 200

        herz_hand.refused_act(TABLE_GIVE_UP_SUFFIX, herz_hand.at[FOREHAND], Refusal.SEAT_OPEN)

    def test_a_ramsch_has_no_give_up(self, skat):
        table = Table(
            skat,
            {
                "ramsch": {
                    "occasion": "passed-in",
                    "scoring": "points",
                    "jungfrau": "doubles-loser",
                    "durchmarsch": "wins-120",
                }
            },
        )
        three_pass(table)

        table.refused_act(TABLE_GIVE_UP_SUFFIX, table.at[FOREHAND], Refusal.WRONG_PHASE)

    def test_a_table_between_hands_has_no_hand(self, herz_hand):
        gives_up(herz_hand, FOREHAND)
        accepted_end(herz_hand)

        herz_hand.refused_act(TABLE_GIVE_UP_SUFFIX, herz_hand.at[FOREHAND], Refusal.NO_HAND)

    def test_an_opponent_retrying_his_give_up_with_the_same_id_and_version_changes_the_table_once(self, herz_hand):
        body = {"command_id": "command-ask", "version": herz_hand.record.version}
        first = give_up(herz_hand, FOREHAND, body=body)
        stored = herz_hand.record

        again = give_up(herz_hand, FOREHAND, body=body)

        assert (again.status_code, again.json()) == (200, first.json())
        assert herz_hand.record == stored
        assert herz_hand.record.version == body["version"] + 1

    @pytest.mark.parametrize(
        ("answer", "entries"), [pytest.param(agree, 1, id="yes"), pytest.param(decline, 0, id="no")]
    )
    def test_an_answer_retried_with_the_same_id_and_version_answers_the_same_and_changes_the_table_once(
        self, herz_hand, answer, entries
    ):
        gives_up(herz_hand, FOREHAND)
        body = {"command_id": "command-answer", "version": herz_hand.record.version}
        first = answer(herz_hand, body=body)
        stored = herz_hand.record

        again = answer(herz_hand, body=body)

        assert (again.status_code, again.json()) == (200, first.json())
        assert herz_hand.record == stored
        assert len(herz_hand.record.game_list) == entries


class TestTheDeclarerDemandsPlayOn:
    def test_the_request_ends_with_one_version_and_the_player_on_turn_has_his_cards_back(self, eight_cards):
        gives_up(eight_cards, FOREHAND)
        before = eight_cards.record

        answer = decline(eight_cards)

        assert answer.status_code == 200, answer.text
        assert eight_cards.record.version == before.version + 1
        assert eight_cards.record.hand is not None
        assert eight_cards.record.progress.give_up is None
        assert everyone_reads(eight_cards) == [None] * 4
        assert playing_as(eight_cards, eight_cards.at[REARHAND])["legal_cards"] != []

    def test_the_game_played_out_is_scored_by_its_play_alone(self, herz_hand):
        gives_up(herz_hand, FOREHAND)
        assert decline(herz_hand).status_code == 200

        herz_hand.played_out(HERZ_GAME)

        result = herz_hand.result()
        assert shown(result, HERZ_HAND_RESULT | {"declarer_points": 70, "opponents_points": 50}) == (
            HERZ_HAND_RESULT | {"declarer_points": 70, "opponents_points": 50}
        )
        assert ending_of(result) == ("played-out", None)

    @pytest.mark.parametrize("position", OPPONENTS)
    def test_an_opponent_may_give_up_again_and_the_request_is_new(self, herz_hand, position):
        gives_up(herz_hand, FOREHAND)
        assert decline(herz_hand).status_code == 200
        before = herz_hand.record.version

        gives_up(herz_hand, position)

        assert herz_hand.record.version == before + 1
        assert everyone_reads(herz_hand) == [asked_by(position)] * 4

    def test_the_same_id_with_another_version_is_reused(self, herz_hand):
        gives_up(herz_hand, FOREHAND)
        version = herz_hand.record.version
        gives_up_again = {"command_id": "command-ask", "version": version}
        assert give_up(herz_hand, REARHAND, body=gives_up_again).status_code == 200

        again = give_up(herz_hand, REARHAND, body={"command_id": "command-ask", "version": version - 1})

        assert again.status_code == 409
        assert "reused" in again.json()["detail"]


class TestWhileTheGameWaitsForTheDeclarer:
    @pytest.fixture
    def waiting(self, eight_cards):
        gives_up(eight_cards, FOREHAND)
        return eight_cards

    @pytest.mark.parametrize(
        ("position", "played"),
        [
            pytest.param(MIDDLEHAND, "H8", id="the-declarer"),
            pytest.param(REARHAND, "D7", id="rearhand"),
            pytest.param(FOREHAND, "C9", id="forehand-on-turn-or-not"),
        ],
    )
    def test_a_card_from_each_seat_is_pending_before_the_engine_refuses_it(self, waiting, position, played):
        waiting.refused(waiting.at[position], card(played), Refusal.REQUEST_PENDING)

        assert playing_as(waiting, waiting.at[position])["legal_cards"] == []

    @pytest.mark.parametrize("position", [MIDDLEHAND, REARHAND, FOREHAND], ids=lambda position: position.name)
    def test_a_throw_down_from_each_side_is_pending(self, waiting, position):
        waiting.refused_act(TABLE_THROW_DOWN_SUFFIX, waiting.at[position], Refusal.REQUEST_PENDING)

    @pytest.mark.parametrize(
        ("played_before", "asker"),
        [pytest.param(EIGHT_CARDS, FOREHAND, id="eight-cards"), pytest.param((), REARHAND, id="ten-cards")],
    )
    def test_the_declarers_give_up_is_pending(self, herz_hand, played_before, asker):
        herz_hand.played_out(played_before)
        gives_up(herz_hand, asker)

        herz_hand.refused_act(TABLE_GIVE_UP_SUFFIX, herz_hand.at[MIDDLEHAND], Refusal.REQUEST_PENDING)

    @pytest.mark.parametrize("position", OPPONENTS)
    @pytest.mark.parametrize("route", [TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX])
    def test_an_opponent_answering_his_sides_request_is_not_the_declarer(self, waiting, position, route):
        waiting.refused_act(route, waiting.at[position], Refusal.NOT_DECLARER)

    @pytest.mark.parametrize("route", [TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX])
    def test_an_answer_with_nothing_asked_has_no_request(self, herz_hand, route):
        herz_hand.refused_act(route, herz_hand.at[MIDDLEHAND], Refusal.NO_REQUEST)


class TestWhatTheViewsOfferWhileItWaits:
    def test_no_viewer_has_a_card_or_a_word_to_play_and_all_come_back_after_the_no(self, kontra_table):
        gives_up(kontra_table, FOREHAND)

        for headers in kontra_table.at.values():
            playing = playing_as(kontra_table, headers)
            assert (playing["legal_cards"], playing["kontra"]["my_word"]) == ([], None)
        assert everyone_reads(kontra_table) == [asked_by(FOREHAND)] * 4

        assert decline(kontra_table).status_code == 200

        assert playing_as(kontra_table, kontra_table.at[FOREHAND])["legal_cards"] != []
        assert playing_as(kontra_table, kontra_table.at[FOREHAND])["kontra"]["my_word"] == "kontra"
        assert everyone_reads(kontra_table) == [None] * 4

    def test_every_stream_carries_the_request_with_no_card_or_word_to_play_and_then_the_no(self, kontra_table):
        with everyones_streams(kontra_table) as streams:
            gives_up(kontra_table, FOREHAND)
            waiting = [(position, next(stream)) for position, stream in streams]

            assert decline(kontra_table).status_code == 200
            playing_on = [(position, next(stream)) for position, stream in streams]

        for position, frame in waiting:
            playing = frame["hand"]["playing"]
            assert playing["give_up"] == asked_by(FOREHAND)
            assert (playing["legal_cards"], playing["kontra"]["my_word"]) == ([], None)
            assert cards_in(frame) == own_cards_of(position)
        for position, frame in playing_on:
            assert frame["hand"]["playing"]["give_up"] is None
            assert cards_in(frame) == own_cards_of(position)
        (forehand,) = (frame["hand"]["playing"] for position, frame in playing_on if position is FOREHAND)
        assert (forehand["legal_cards"] != [], forehand["kontra"]["my_word"]) == (True, "kontra")


class TestKontraWhileItWaits:
    def test_a_word_and_the_answer_of_no_word_are_pending_on_the_routes(self, kontra_table):
        gives_up(kontra_table, FOREHAND)

        kontra_table.refused_act(
            TABLE_KONTRA_SUFFIX, kontra_table.at[REARHAND], Refusal.REQUEST_PENDING, body={"word": "kontra"}
        )
        kontra_table.refused_act(TABLE_NO_WORD_SUFFIX, kontra_table.at[REARHAND], Refusal.REQUEST_PENDING)


class TestThroughTheMcpTools:
    """An agent opponent gives up for his side; an agent declarer answers an opponent's give-up."""

    @pytest.fixture
    def skat(self, hold, issuer):
        skat = Skat(lambda: hold, issuer_transports=issuer.transports)
        with skat.client:
            yield skat

    @pytest.fixture
    def gave_up(self, skat, agent):
        """The agent holds the forehand chair, on turn, and has given up through the tool."""
        table = AgentTable(skat, agent, FOREHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()
        answer = agent.call(
            GIVE_UP_GAME_TOOL, table_id=table.table_id, command_id="agent-give-up-0001", version=table.record.version
        )
        assert not answer.is_error, answer.text
        return table, answer

    @pytest.fixture
    def declarer_asked(self, skat, agent):
        """The agent holds the declarer's chair; the person in the forehand chair has given up."""
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.declared_hand_game()
        assert table.act(TABLE_GIVE_UP_SUFFIX, table.at[FOREHAND]).status_code == 200
        skat.client.cookies.clear()
        return table

    def answer(self, agent, table, tool, *, command_id="agent-answer-0001"):
        return agent.call(tool, table_id=table.table_id, command_id=command_id, version=table.record.version)

    def test_the_agent_opponents_give_up_waits_for_the_declarer_with_no_card_to_play(self, agent, gave_up):
        table, _ = gave_up

        playing = agent.read(table.table_id).json()["hand"]["playing"]
        assert playing["give_up"] == {"asking_seat": 3, "declined_seat": None}
        assert playing["legal_cards"] == []
        assert table.record.hand is not None

    def test_the_agents_card_while_it_waits_is_a_failed_result_that_spends_the_id(self, agent, gave_up):
        table, _ = gave_up
        before = stored(table.skat)

        answer = agent.play(table, card("C7"))

        assert answer.is_error
        assert answer.json()["reason"] == Refusal.REQUEST_PENDING
        assert stored(table.skat)[0] == before[0]
        assert table.act(TABLE_GIVE_UP_DECLINE_SUFFIX, table.at[MIDDLEHAND]).status_code == 200
        assert "reused" in agent.play(table, card("C7")).text

    def test_the_persons_yes_ends_the_game_won_for_the_declarer_by_the_agent_opponent(self, agent, gave_up):
        table, _ = gave_up

        assert table.act(TABLE_GIVE_UP_AGREE_SUFFIX, table.at[MIDDLEHAND]).status_code == 200

        result = agent.read(table.table_id).json()["result"]
        assert (result["won"], result["declarer_points"]) == (True, 120)
        assert ending_of(result) == ("given-up", 3)

    def test_the_agent_declarers_yes_ends_the_game_under_its_own_account(self, agent, declarer_asked):
        answer = self.answer(agent, declarer_asked, AGREE_TO_GIVE_UP_TOOL)

        assert not answer.is_error, answer.text
        result = agent.read(declarer_asked.table_id).json()["result"]
        assert (result["won"], result["list_bonus"]) == (True, 50)
        assert ending_of(result) == ("given-up", 3)
        assert len(declarer_asked.record.game_list) == 1

    def test_the_agent_declarers_no_demands_play_on(self, agent, declarer_asked):
        answer = self.answer(agent, declarer_asked, DECLINE_GIVE_UP_TOOL)

        assert not answer.is_error, answer.text
        assert agent.read(declarer_asked.table_id).json()["hand"]["playing"]["give_up"] is None
        assert declarer_asked.record.hand is not None
        assert declarer_asked.read_as(declarer_asked.at[FOREHAND]).json()["hand"]["playing"]["legal_cards"] != []
