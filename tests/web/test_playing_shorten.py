from contextlib import contextmanager

import pytest

from skat.engine.deal import Deal, Position
from skat.engine.tricks import PlayRefusal
from skat.table.game_list import GameEnding
from skat.table.records import Refusal
from skat.web.declaring import (
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
    AnnouncementToken,
    GameToken,
)
from skat.web.mcp import AGREE_TO_GIVE_UP_TOOL, DECLINE_GIVE_UP_TOOL, SHORTEN_GAME_TOOL
from skat.web.playing import (
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_SHORTEN_SUFFIX,
    TABLE_THROW_DOWN_SUFFIX,
)
from tests.support.payload_cards import CARDS_BY_SEAT, cards_in, cards_in_text, wire_cards
from tests.web.support.playing import HERZ_GAME, Table, card_body, cards, ending_of, game_of
from tests.web.support.series import tap_weiter
from tests.web.support.skat import AgentTable, Skat, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# Seats: the declarer (middlehand) sits in seat 1, rearhand in seat 2, forehand in seat 3.
SEAT = {MIDDLEHAND: 1, REARHAND: 2, FOREHAND: 3}
OPPONENTS = [pytest.param(FOREHAND, id="forehand"), pytest.param(REARHAND, id="rearhand")]
NONE, SCHNEIDER, SCHWARZ = AnnouncementToken.NONE, AnnouncementToken.SCHNEIDER, AnnouncementToken.SCHWARZ
# The declarer holds eight cards once he has played to the second trick.
EIGHT_CARDS = HERZ_GAME[:4]
# After seven tricks the declarer holds 55 card points and the skat 15: 70 win the game, the opponents hold 50.
SEVEN_TRICKS = HERZ_GAME[:21]
# Forehand leads an ace, and the partner adds a ten each time: three tricks of 21 points, so the opponents hold 63.
HEAVY_DEAL = Deal(
    forehand=cards("CA CJ SA DA HA HK HQ H9 H8 CK"),
    middlehand=cards("C7 C8 C9 S7 S8 S9 SJ H7 D7 D8"),
    rearhand=cards("CT CQ ST SK SQ HJ HT DT DJ DQ"),
    skat=cards("D9 DK"),
)
HEAVY_TWO_TRICKS = game_of("CA C7 CT / SA S7 ST")
HEAVY_THREE_TRICKS = game_of("CA C7 CT / SA S7 ST / DA D7 DT")
# Clubs and spades are the declarer's own: forehand and rearhand take the first two tricks, so a Null game runs on.
NULL_DEAL = Deal(
    forehand=cards("CT CQ CA ST SQ SA HT HQ D8 DT"),
    middlehand=cards("C7 C8 C9 S7 S8 S9 H7 H8 H9 D7"),
    rearhand=cards("CJ CK SJ SK HJ HK HA D9 DJ DQ"),
    skat=cards("DA DK"),
)
NULL_TWO_TRICKS = game_of("CT C7 CJ / CK CQ C8")


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


def asked(claim=NONE, agreed=None):
    return {"asking_seat": SEAT[MIDDLEHAND], "claim": claim, "agreed_seat": agreed}


def shorten(table, *, claim=None, position=MIDDLEHAND, body=None):
    extra = {} if claim is None else {"claim": claim}
    return table.act(TABLE_SHORTEN_SUFFIX, table.at[position], body=extra | (body or {}))


def shortens(table, claim=None):
    answer = shorten(table, claim=claim)
    assert answer.status_code == 200, answer.text
    return answer


def answer_of(table, position, suffix):
    return table.act(suffix, table.at[position])


def says_yes(table, position):
    answer = answer_of(table, position, TABLE_GIVE_UP_AGREE_SUFFIX)
    assert answer.status_code == 200, answer.text
    return answer


def says_no(table, position):
    answer = answer_of(table, position, TABLE_GIVE_UP_DECLINE_SUFFIX)
    assert answer.status_code == 200, answer.text
    return answer


def both_say_yes(table):
    says_yes(table, FOREHAND)
    return says_yes(table, REARHAND).json()["result"]


def playing_as(table, headers):
    answer = table.read_as(headers)
    assert answer.status_code == 200, answer.text
    return answer.json()["hand"]["playing"]


def declaring_as(table, headers):
    return table.read_as(headers).json()["hand"]["declaring"]


def everyone(table, read):
    return [read(table, headers) for headers in (table.watcher, *table.at.values())]


def shortenings_read(table):
    return everyone(table, lambda each, headers: playing_as(each, headers)["shortening"])


def refusals_read(table):
    return everyone(table, lambda each, headers: playing_as(each, headers)["shortening_refused_seat"])


def open_cards_read(table):
    return everyone(
        table,
        lambda each, headers: {
            (each_card["suit"], each_card["rank"]) for each_card in declaring_as(each, headers)["open_cards"]
        },
    )


@contextmanager
def everyones_streams(table):
    """One open stream per viewer, the watcher first: each as (position or None for the watcher, decoded messages)."""
    viewers = [(None, table.watcher), *table.at.items()]
    with streams_of(table.skat, table.table_id, [(headers, None) for _, headers in viewers]) as streams:
        yield [(position, stream) for (position, _), stream in zip(viewers, streams, strict=True)]


def own_cards_of(position):
    return set() if position is None else wire_cards(CARDS_BY_SEAT[SEAT[position]])


def declarers_cards():
    return wire_cards(CARDS_BY_SEAT[SEAT[MIDDLEHAND]])


def undecided_herz_at_22(table):
    table.with_deal(HEAVY_DEAL)
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


def herz_at_22_with_42_points_against(table):
    undecided_herz_at_22(table)
    table.played_out(HEAVY_TWO_TRICKS)


def herz_hand_with_63_points_against(table):
    table.with_deal(HEAVY_DEAL)
    table.declared_hand_game()
    table.played_out(HEAVY_THREE_TRICKS)


def herz_hand_won_by_tricks_and_skat(table):
    table.declared_hand_game()
    table.played_out(SEVEN_TRICKS)


def null_before_a_trick(table):
    table.with_deal(NULL_DEAL)
    table.declared_hand_game(GameToken.NULL)
    table.played_out(NULL_TWO_TRICKS)


class TestTheDeclarerShortens:
    @pytest.mark.parametrize("claim", [None, NONE, SCHNEIDER, SCHWARZ])
    def test_the_request_is_stored_and_every_viewer_reads_who_asked_with_the_level_and_nobody_has_answered(
        self, herz_hand, claim
    ):
        before = herz_hand.record

        answer = shortens(herz_hand, claim)

        assert herz_hand.record.version == before.version + 1
        assert herz_hand.record.hand is not None
        assert herz_hand.record.game_list == ()
        assert answer.json()["hand"]["playing"]["shortening"] == asked(claim or NONE)
        assert shortenings_read(herz_hand) == [asked(claim or NONE)] * 4
        assert everyone(herz_hand, lambda each, headers: playing_as(each, headers)["give_up"]) == [None] * 4

    def test_the_request_discloses_no_card_to_anyone_and_play_goes_on_for_the_player_on_turn(self, herz_hand):
        with everyones_streams(herz_hand) as streams:
            shortens(herz_hand)
            frames = [(position, next(stream)) for position, stream in streams]

        assert [cards_in(frame) == own_cards_of(position) for position, frame in frames] == [True] * 4
        assert open_cards_read(herz_hand) == [set()] * 4
        assert playing_as(herz_hand, herz_hand.at[FOREHAND])["legal_cards"] != []

    def test_asking_again_for_the_same_level_changes_nothing_and_another_level_is_pending(self, herz_hand):
        shortens(herz_hand, SCHNEIDER)
        before = herz_hand.record

        assert shorten(herz_hand, claim=SCHNEIDER).status_code == 200
        assert herz_hand.record == before
        herz_hand.refused_act(
            TABLE_SHORTEN_SUFFIX, herz_hand.at[MIDDLEHAND], Refusal.REQUEST_PENDING, body={"claim": SCHWARZ}
        )

    def test_a_retry_with_the_same_id_and_version_changes_the_table_once(self, herz_hand):
        body = {"command_id": "command-shorten", "version": herz_hand.record.version}
        first = shorten(herz_hand, body=body)
        stored = herz_hand.record

        again = shorten(herz_hand, body=body)

        assert (again.status_code, again.json()) == (200, first.json())
        assert herz_hand.record == stored


class TestBothOpponentsSayYes:
    def test_the_first_yes_is_read_by_everyone_and_the_second_ends_the_game_at_the_shorten_outcome(self, herz_hand):
        shortens(herz_hand)

        answer = says_yes(herz_hand, FOREHAND)

        assert answer.json()["hand"]["playing"]["shortening"] == asked(NONE, SEAT[FOREHAND])
        assert shortenings_read(herz_hand) == [asked(NONE, SEAT[FOREHAND])] * 4
        assert herz_hand.record.hand is not None

        result = says_yes(herz_hand, REARHAND).json()["result"]

        assert (result["won"], result["game_value"], result["schneider"], result["schwarz"]) == (True, 30, False, False)
        assert ending_of(result) == ("shortened", SEAT[MIDDLEHAND])
        assert herz_hand.record.hand is None
        (entry,) = herz_hand.record.game_list
        assert (entry.ending, entry.ended_by_seat, entry.won) == (GameEnding.SHORTENED, SEAT[MIDDLEHAND], True)
        assert herz_hand.endings_in_every_view() == {("shortened", SEAT[MIDDLEHAND])}

    @pytest.mark.parametrize(
        ("claim", "value", "levels"),
        [
            pytest.param(NONE, 30, (False, False), id="no-demand"),
            pytest.param(SCHNEIDER, 40, (True, False), id="schneider-demanded"),
            pytest.param(SCHWARZ, 50, (True, True), id="schwarz-demanded"),
        ],
    )
    @pytest.mark.parametrize("first", OPPONENTS)
    def test_the_game_is_won_by_the_declaration_and_the_demanded_level_whoever_answers_first(
        self, herz_hand, claim, value, levels, first
    ):
        shortens(herz_hand, claim)
        says_yes(herz_hand, first)
        says_yes(herz_hand, REARHAND if first is FOREHAND else FOREHAND)

        result = herz_hand.result()

        assert (result["won"], result["game_value"], (result["schneider"], result["schwarz"])) == (
            True,
            value,
            levels,
        )

    @pytest.mark.parametrize(
        ("scene", "claim", "expected"),
        [
            pytest.param(
                herz_at_22_with_42_points_against,
                NONE,
                {"won": False, "opponents_points": 42, "declarer_points": 78},
                id="already-lost-stays-lost",
            ),
            pytest.param(
                herz_hand_with_63_points_against,
                NONE,
                {"won": False, "opponents_points": 63, "declarer_points": 57},
                id="already-lost-with-sixty-three",
            ),
            pytest.param(
                herz_hand_won_by_tricks_and_skat,
                NONE,
                {"won": True, "opponents_points": 50, "declarer_points": 70, "game_value": 30},
                id="already-won-keeps-its-real-result",
            ),
            pytest.param(
                herz_hand_won_by_tricks_and_skat,
                SCHNEIDER,
                {"won": True, "game_value": 40, "schneider": True},
                id="already-won-with-a-demand-counts-the-level",
            ),
            pytest.param(
                null_before_a_trick,
                NONE,
                {"won": True, "game_value": 35, "declarer_points": 101},
                id="null-without-a-demand",
            ),
        ],
    )
    def test_the_engines_settlement_decides_a_game_already_decided(self, table, scene, claim, expected):
        scene(table)
        shortens(table, claim)

        result = both_say_yes(table)

        assert {key: result[key] for key in expected} == expected
        assert ending_of(result) == ("shortened", SEAT[MIDDLEHAND])

    def test_every_stream_carries_the_same_result_and_no_card_after_the_second_yes(self, herz_hand):
        shortens(herz_hand)
        says_yes(herz_hand, FOREHAND)
        with everyones_streams(herz_hand) as streams:
            says_yes(herz_hand, REARHAND)
            frames = [next(stream) for _, stream in streams]

        assert [cards_in(frame) for frame in frames] == [set()] * 4
        assert {str(frame["result"]) for frame in frames} == {str(frames[0]["result"])}
        assert ending_of(frames[0]["result"]) == ("shortened", SEAT[MIDDLEHAND])
        assert {cards_in_text(read.text) == set() for read in map(herz_hand.read_as, herz_hand.at.values())} == {True}

    def test_the_same_opponents_yes_twice_is_refused_as_already_answered_and_the_game_goes_on(self, herz_hand):
        shortens(herz_hand)
        says_yes(herz_hand, FOREHAND)

        herz_hand.refused_act(TABLE_GIVE_UP_AGREE_SUFFIX, herz_hand.at[FOREHAND], Refusal.ALREADY_ANSWERED)

        assert herz_hand.record.hand is not None
        assert shortenings_read(herz_hand) == [asked(NONE, SEAT[FOREHAND])] * 4

    def test_a_yes_retried_with_the_same_id_and_version_answers_the_same_and_ends_the_game_once(self, herz_hand):
        shortens(herz_hand)
        says_yes(herz_hand, FOREHAND)
        body = {"command_id": "command-yes", "version": herz_hand.record.version}
        first = herz_hand.act(TABLE_GIVE_UP_AGREE_SUFFIX, herz_hand.at[REARHAND], body=body)
        stored = herz_hand.record

        again = herz_hand.act(TABLE_GIVE_UP_AGREE_SUFFIX, herz_hand.at[REARHAND], body=body)

        assert (again.status_code, again.json()) == (200, first.json())
        assert herz_hand.record == stored
        assert len(herz_hand.record.game_list) == 1


class TestAnOpponentSaysNo:
    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_attempt_ends_with_one_version_and_play_goes_on(self, herz_hand, position):
        shortens(herz_hand)
        before = herz_hand.record

        answer = says_no(herz_hand, position)

        assert herz_hand.record.version == before.version + 1
        assert herz_hand.record.hand is not None
        assert herz_hand.record.game_list == ()
        assert answer.json()["hand"]["playing"]["shortening"] is None
        assert shortenings_read(herz_hand) == [None] * 4
        assert refusals_read(herz_hand) == [SEAT[position]] * 4
        assert playing_as(herz_hand, herz_hand.at[FOREHAND])["legal_cards"] != []

    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_declarers_cards_are_open_to_every_viewer_and_nothing_else_is(self, herz_hand, position):
        shortens(herz_hand)

        says_no(herz_hand, position)

        assert open_cards_read(herz_hand) == [declarers_cards()] * 4
        viewers = {None: herz_hand.watcher, **herz_hand.at}
        for position, headers in viewers.items():
            assert cards_in_text(herz_hand.read_as(headers).text) == own_cards_of(position) | declarers_cards()

    def test_the_second_opponents_yes_after_the_first_ones_no_finds_no_request(self, herz_hand):
        shortens(herz_hand)
        says_no(herz_hand, FOREHAND)

        herz_hand.refused_act(TABLE_GIVE_UP_AGREE_SUFFIX, herz_hand.at[REARHAND], Refusal.NO_REQUEST)

    def test_a_no_after_the_other_opponents_yes_ends_the_attempt_and_the_yes_is_forgotten(self, herz_hand):
        shortens(herz_hand)
        says_yes(herz_hand, FOREHAND)

        says_no(herz_hand, REARHAND)

        assert shortenings_read(herz_hand) == [None] * 4
        assert refusals_read(herz_hand) == [SEAT[REARHAND]] * 4
        shortens(herz_hand)
        assert shortenings_read(herz_hand) == [asked()] * 4

    def test_the_declarer_asking_again_after_a_no_is_a_new_attempt_that_the_old_no_does_not_end(self, herz_hand):
        shortens(herz_hand)
        says_no(herz_hand, FOREHAND)

        shortens(herz_hand, SCHNEIDER)

        assert shortenings_read(herz_hand) == [asked(SCHNEIDER)] * 4
        assert refusals_read(herz_hand) == [SEAT[FOREHAND]] * 4
        says_yes(herz_hand, FOREHAND)
        says_yes(herz_hand, REARHAND)
        assert herz_hand.result()["game_value"] == 40

    def test_the_cards_stay_open_as_they_are_played_and_the_game_is_scored_by_its_play_alone(self, herz_hand):
        shortens(herz_hand)
        says_no(herz_hand, FOREHAND)

        herz_hand.played_out(HERZ_GAME[:3])

        assert open_cards_read(herz_hand) == [declarers_cards() - wire_cards([HERZ_GAME[1]])] * 4

        herz_hand.played_out(HERZ_GAME[3:])

        result = herz_hand.result()
        assert (result["won"], result["declarer_points"], result["opponents_points"]) == (True, 70, 50)
        assert ending_of(result) == ("played-out", None)

    def test_the_next_hand_starts_with_nothing_open_and_no_request(self, server):
        table = Table(server)
        table.declared_hand_game()
        shortens(table)
        says_no(table, FOREHAND)
        table.played_out(HERZ_GAME)

        with streams_of(server, table.table_id, [(headers, None) for headers in table.at.values()]):
            for number, headers in enumerate(table.at.values()):
                server.client.cookies.clear()
                assert tap_weiter(server, headers, table.table_id, f"command-weiter-{number}").status_code == 200

        assert table.record.hand is not None
        assert everyone(table, lambda each, headers: each.read_as(headers).json()["hand"]["playing"]) == [None] * 4
        assert everyone(table, lambda each, headers: each.read_as(headers).json()["hand"]["declaring"]) == [None] * 4

    def test_every_stream_carries_the_declarers_cards_after_the_no_and_no_other_hidden_card(self, herz_hand):
        shortens(herz_hand)
        with everyones_streams(herz_hand) as streams:
            says_no(herz_hand, REARHAND)
            frames = [(position, next(stream)) for position, stream in streams]

        for position, frame in frames:
            assert cards_in(frame) == own_cards_of(position) | declarers_cards()
            assert frame["hand"]["playing"]["shortening_refused_seat"] == SEAT[REARHAND]


class TestWhatTheDeclarerMayAsk:
    @pytest.mark.parametrize(
        ("scene", "claim", "reason"),
        [
            pytest.param(herz_hand_with_63_points_against, SCHNEIDER, PlayRefusal.CLAIM_OUT_OF_REACH, id="schneider"),
            pytest.param(herz_hand_with_63_points_against, SCHWARZ, PlayRefusal.CLAIM_OUT_OF_REACH, id="schwarz"),
            pytest.param(null_before_a_trick, SCHNEIDER, PlayRefusal.CLAIM_OUT_OF_REACH, id="null-schneider"),
            pytest.param(null_before_a_trick, SCHWARZ, PlayRefusal.CLAIM_OUT_OF_REACH, id="null-schwarz"),
        ],
    )
    def test_a_level_out_of_reach_is_refused_before_anyone_is_asked(self, table, scene, claim, reason):
        scene(table)

        table.refused_act(TABLE_SHORTEN_SUFFIX, table.at[MIDDLEHAND], reason, body={"claim": claim})

        assert shortenings_read(table) == [None] * 4

    @pytest.mark.parametrize("position", OPPONENTS)
    def test_an_opponent_is_not_the_declarer(self, herz_hand, position):
        herz_hand.refused_act(TABLE_SHORTEN_SUFFIX, herz_hand.at[position], Refusal.NOT_DECLARER)

    def test_the_declarer_cannot_answer_his_own_request(self, herz_hand):
        shortens(herz_hand)

        for suffix in (TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX):
            herz_hand.refused_act(suffix, herz_hand.at[MIDDLEHAND], PlayRefusal.NOT_AN_OPPONENT)

    @pytest.mark.parametrize("route", [TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX])
    def test_an_answer_with_nothing_asked_has_no_request(self, herz_hand, route):
        herz_hand.refused_act(route, herz_hand.at[FOREHAND], Refusal.NO_REQUEST)

    def test_a_chair_open_a_ramsch_and_a_table_between_hands_have_no_shortening(self, skat, herz_hand):
        assert herz_hand.skat.stand(herz_hand.at[REARHAND], herz_hand.table_id).status_code == 200
        herz_hand.refused_act(TABLE_SHORTEN_SUFFIX, herz_hand.at[MIDDLEHAND], Refusal.SEAT_OPEN)

        ramsch = Table(
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
        for position in (MIDDLEHAND, REARHAND, FOREHAND):
            ramsch.passes(position)
        ramsch.refused_act(TABLE_SHORTEN_SUFFIX, ramsch.at[MIDDLEHAND], Refusal.WRONG_PHASE)

        ended = Table(skat)
        ended.declared_hand_game()
        assert ended.act(TABLE_THROW_DOWN_SUFFIX, ended.at[MIDDLEHAND]).status_code == 200
        ended.refused_act(TABLE_SHORTEN_SUFFIX, ended.at[MIDDLEHAND], Refusal.NO_HAND)

    def test_a_shortening_while_an_opponents_give_up_waits_for_the_declarer_is_pending(self, herz_hand):
        assert herz_hand.act(TABLE_GIVE_UP_SUFFIX, herz_hand.at[FOREHAND]).status_code == 200

        herz_hand.refused_act(TABLE_SHORTEN_SUFFIX, herz_hand.at[MIDDLEHAND], Refusal.REQUEST_PENDING)

    def test_a_shortening_while_the_declarers_own_give_up_stands_is_pending_and_so_is_the_give_up_the_other_way(
        self, herz_hand
    ):
        herz_hand.played_out(EIGHT_CARDS)
        assert herz_hand.act(TABLE_GIVE_UP_SUFFIX).status_code == 200
        herz_hand.refused_act(TABLE_SHORTEN_SUFFIX, herz_hand.at[MIDDLEHAND], Refusal.REQUEST_PENDING)
        says_no(herz_hand, FOREHAND)
        says_no(herz_hand, REARHAND)

        shortens(herz_hand)

        herz_hand.refused_act(TABLE_GIVE_UP_SUFFIX, herz_hand.at[MIDDLEHAND], Refusal.REQUEST_PENDING)
        herz_hand.refused_act(TABLE_GIVE_UP_SUFFIX, herz_hand.at[FOREHAND], Refusal.REQUEST_PENDING)

    def test_a_throw_down_ends_the_hand_with_a_request_standing(self, herz_hand):
        shortens(herz_hand)

        assert herz_hand.act(TABLE_THROW_DOWN_SUFFIX, herz_hand.at[MIDDLEHAND]).status_code == 200

        assert herz_hand.record.hand is None


class TestARequestCrossingAPlayedCard:
    def test_a_card_ends_the_request_with_the_first_yes_and_a_late_answer_finds_no_request(self, herz_hand):
        shortens(herz_hand)
        says_yes(herz_hand, FOREHAND)

        herz_hand.accepted(HERZ_GAME[0])

        assert shortenings_read(herz_hand) == [None] * 4
        assert open_cards_read(herz_hand) == [set()] * 4
        herz_hand.refused_act(TABLE_GIVE_UP_AGREE_SUFFIX, herz_hand.at[REARHAND], Refusal.NO_REQUEST)
        herz_hand.refused_act(TABLE_GIVE_UP_DECLINE_SUFFIX, herz_hand.at[REARHAND], Refusal.NO_REQUEST)

    def test_a_card_after_a_no_keeps_the_cards_open(self, herz_hand):
        shortens(herz_hand)
        says_no(herz_hand, FOREHAND)

        herz_hand.accepted(HERZ_GAME[0])

        assert refusals_read(herz_hand) == [SEAT[FOREHAND]] * 4
        assert open_cards_read(herz_hand) == [declarers_cards()] * 4


class TestWhenAChairChangesHands:
    def test_an_agreeing_opponent_standing_up_takes_his_yes_and_the_request_stands(self, herz_hand):
        shortens(herz_hand)
        says_yes(herz_hand, FOREHAND)

        assert herz_hand.skat.stand(herz_hand.at[FOREHAND], herz_hand.table_id).status_code == 200

        assert shortenings_read(herz_hand) == [asked()] * 4

    def test_the_other_opponent_standing_up_changes_nothing_of_the_yes(self, herz_hand):
        shortens(herz_hand)
        says_yes(herz_hand, FOREHAND)

        assert herz_hand.skat.stand(herz_hand.at[REARHAND], herz_hand.table_id).status_code == 200

        assert shortenings_read(herz_hand) == [asked(NONE, SEAT[FOREHAND])] * 4

    def test_the_declarer_standing_up_takes_his_request(self, herz_hand):
        shortens(herz_hand)

        assert herz_hand.skat.stand(herz_hand.at[MIDDLEHAND], herz_hand.table_id).status_code == 200

        assert shortenings_read(herz_hand) == [None] * 4


class TestThroughTheMcpTools:
    """An agent declarer shortens; agent opponents answer."""

    @pytest.fixture
    def skat(self, hold, issuer):
        skat = Skat(lambda: hold, issuer_transports=issuer.transports)
        with skat.client:
            yield skat

    def test_the_agent_declarer_shortens_with_a_demand_and_the_persons_yes_ends_the_game(self, skat, agent):
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()

        answer = agent.call(
            SHORTEN_GAME_TOOL,
            table_id=table.table_id,
            command_id="agent-shorten-0001",
            version=table.record.version,
            claim=SCHNEIDER,
        )

        assert not answer.is_error, answer.text
        assert agent.read(table.table_id).json()["hand"]["playing"]["shortening"] == asked(SCHNEIDER)
        says_yes(table, FOREHAND)
        says_yes(table, REARHAND)
        result = agent.read(table.table_id).json()["result"]
        assert (result["won"], result["game_value"], result["schneider"]) == (True, 40, True)
        assert ending_of(result) == ("shortened", SEAT[MIDDLEHAND])

    def test_the_agent_declarers_unreached_demand_is_a_failed_result(self, skat, agent):
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.with_deal(HEAVY_DEAL)
        table.declared_hand_game()
        table.played_out(HEAVY_THREE_TRICKS)
        skat.client.cookies.clear()

        answer = agent.call(
            SHORTEN_GAME_TOOL,
            table_id=table.table_id,
            command_id="agent-shorten-0002",
            version=table.record.version,
            claim=SCHNEIDER,
        )

        assert answer.is_error
        assert answer.json()["reason"] == PlayRefusal.CLAIM_OUT_OF_REACH

    @pytest.mark.parametrize("tool", [AGREE_TO_GIVE_UP_TOOL, DECLINE_GIVE_UP_TOOL])
    def test_an_agent_opponent_answers_the_shortening_with_the_give_up_answer_tools(self, skat, agent, tool):
        table = AgentTable(skat, agent, FOREHAND)
        table.declared_hand_game()
        assert shorten(table).status_code == 200
        skat.client.cookies.clear()

        answer = agent.call(tool, table_id=table.table_id, command_id="agent-answer-0001", version=table.record.version)

        assert not answer.is_error, answer.text
        playing = agent.read(table.table_id).json()["hand"]["playing"]
        if tool == AGREE_TO_GIVE_UP_TOOL:
            assert playing["shortening"] == asked(NONE, SEAT[FOREHAND])
        else:
            assert (playing["shortening"], playing["shortening_refused_seat"]) == (None, SEAT[FOREHAND])
