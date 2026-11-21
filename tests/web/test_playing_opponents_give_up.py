import pytest

from skat.engine.deal import Deal, Position, next_dealer
from skat.engine.tricks import PlayRefusal
from skat.table.game_list import GameEnding
from skat.table.records import Refusal
from skat.web.declaration_tokens import GameToken
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
from tests.support.payload_cards import DEALER_SEAT, KNOWN_DEAL, cards_in, cards_in_text
from tests.web.support.calling import IssuerSkat
from tests.web.support.giving_up import (
    NULL_DEAL,
    NULL_TWO_TRICKS,
    SEAT,
    everyones_streams,
    own_cards_of,
    playing_as,
)
from tests.web.support.playing import EIGHT_CARDS, Table, card, cards, ending_of, gains, game_of, three_pass
from tests.web.support.series import tap_weiter
from tests.web.support.shortening import (
    herz_at_22_with_42_points_against,
    herz_hand_with_63_points_against,
    herz_hand_won_by_tricks_and_skat,
    null_hand_before_a_trick,
    undecided_herz_at_22,
)
from tests.web.support.skat import AgentTable, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
OPPONENTS = [pytest.param(FOREHAND, id="forehand"), pytest.param(REARHAND, id="rearhand")]
HERZ_GAME = game_of(
    "S7 S9 D7 / H7 DJ CJ / S8 ST D8 / SQ D9 C7 / SK DT C8",
    "SA DQ C9 / SJ HJ CT / H8 HQ CQ / HK CK H9 / HA CA HT",
)
# The declarer holds eight cards once he has played to the second trick, led with H7; rearhand is on turn.
# After seven tricks the declarer has taken 0 + 10 + 3 + 14 + 14 + 14 = 55 card points, and the skat (D K, D A) adds
# 4 + 11: 70 points win the game without Schneider.
SEVEN_TRICKS = HERZ_GAME[:21]
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


PARTNER_AGREES = {"give_up": {"partner_agrees": True}}
KONTRA = {"kontra": {"sayer": "any-opponent", "reach": "up-to-hirsch", "deadline": "own-card"}}


@pytest.fixture
def kontra_table(skat):
    table = Table(skat, options=KONTRA)
    table.declared_hand_game()
    return table


@pytest.fixture
def partner_table(skat):
    """A Herz Hand at a table whose special rule wants the partner's yes to an opponent's give-up."""
    table = Table(skat, options=PARTNER_AGREES)
    table.declared_hand_game()
    return table


@pytest.fixture
def partner_kontra_table(skat):
    table = Table(skat, options=PARTNER_AGREES | KONTRA)
    table.declared_hand_game()
    return table


def asked_by(position):
    return {"asking_seat": SEAT[position], "declined_seat": None}


def partner_of(position):
    return REARHAND if position is FOREHAND else FOREHAND


def give_up(table, position, *, body=None):
    return table.act(TABLE_GIVE_UP_SUFFIX, table.at[position], body=body)


def gives_up(table, position):
    answer = give_up(table, position)
    assert answer.status_code == 200, answer.text
    return answer


def ended_by_giving_up(table, position):
    """The opponent gives up at a table that plays the ISkO: the game ends with his act."""
    return gives_up(table, position).json()["result"]


def agree(table, position=REARHAND, *, body=None):
    return table.act(TABLE_GIVE_UP_AGREE_SUFFIX, table.at[position], body=body)


def decline(table, position=REARHAND, *, body=None):
    return table.act(TABLE_GIVE_UP_DECLINE_SUFFIX, table.at[position], body=body)


def partner_agreed(table, position=REARHAND):
    answer = agree(table, position)
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def everyone_reads(table):
    return [playing_as(table, headers)["give_up"] for headers in (table.watcher, *table.at.values())]


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


def undecided_herz_hand(table):
    table.declared_hand_game()


def null_before_a_trick(table):
    table.with_deal(NULL_DEAL)
    table.declared_after_putting_back(cards("DA DK"), GameToken.NULL, ouvert=False)
    table.played_out(NULL_TWO_TRICKS)


class TestAnOpponentGivesUpUnderTheIsko:
    """ISkO 4.4.3: an opponent's give-up ends the game at once and binds his partner; nobody is asked."""

    @pytest.mark.parametrize("position", OPPONENTS)
    @pytest.mark.parametrize(
        "played_before",
        [
            pytest.param((), id="forehand-on-turn"),
            pytest.param(HERZ_GAME[:1], id="the-declarer-on-turn"),
            pytest.param(HERZ_GAME[:2], id="rearhand-on-turn"),
        ],
    )
    def test_the_game_ends_with_his_act_won_as_declared_and_the_ending_names_him(
        self, herz_hand, position, played_before
    ):
        herz_hand.played_out(played_before)

        result = ended_by_giving_up(herz_hand, position)

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

        result = ended_by_giving_up(table, FOREHAND)

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
            results.append(ended_by_giving_up(table, position))

        assert [ending_of(result)[1] for result in results] == [SEAT[FOREHAND], SEAT[REARHAND]]
        assert {key: value for key, value in results[0].items() if key != "ended_by_seat"} == {
            key: value for key, value in results[1].items() if key != "ended_by_seat"
        }

    def test_two_deals_differing_in_the_skat_alone_end_the_same(self, skat):
        swapped = Deal(
            forehand=KNOWN_DEAL.forehand,
            middlehand=KNOWN_DEAL.middlehand,
            rearhand=tuple(card("DA") if each == card("D9") else each for each in KNOWN_DEAL.rearhand),
            skat=(card("DK"), card("D9")),
        )
        results = []
        for deal in (KNOWN_DEAL, swapped):
            table = Table(skat)
            table.with_deal(deal)
            table.declared_hand_game()
            table.played_out(EIGHT_CARDS)
            results.append(shown(ended_by_giving_up(table, FOREHAND), HERZ_HAND_RESULT))

        assert results[0] == results[1] == HERZ_HAND_RESULT

    def test_every_viewer_reads_the_same_result_and_no_card_after_the_end(self, table):
        table.declared_grand_ouvert()
        table.played_out(cards("S7 S9 D7 H7"))

        ended_by_giving_up(table, FOREHAND)

        reads = [table.read_as(headers) for headers in (table.watcher, *table.at.values())]
        assert {tuple(sorted(cards_in_text(read.text))) for read in reads} == {()}
        assert len({str(read.json()["result"]) for read in reads}) == 1

    def test_every_stream_carries_the_same_result_with_no_card(self, herz_hand):
        with everyones_streams(herz_hand) as streams:
            gives_up(herz_hand, FOREHAND)

            frames = [next(frame for frame in stream if frame["result"] is not None) for _, stream in streams]
        assert [cards_in(frame) for frame in frames] == [set()] * 4
        assert {str(frame["result"]) for frame in frames} == {str(frames[0]["result"])}
        assert ending_of(frames[0]["result"]) == ("given-up", SEAT[FOREHAND])

    def test_the_words_said_before_double_the_score(self, kontra_table):
        answer = kontra_table.act(TABLE_KONTRA_SUFFIX, kontra_table.at[FOREHAND], body={"word": "kontra"})
        assert answer.status_code == 200, answer.text

        result = ended_by_giving_up(kontra_table, REARHAND)

        assert (result["kontra"]["steps"][-1]["word"], result["score"]) == ("kontra", 60)

    def test_all_three_tapping_weiter_deal_the_next_hand(self, server):
        table = Table(server)
        table.declared_hand_game()
        ended_by_giving_up(table, FOREHAND)

        with streams_of(server, table.table_id, [(headers, None) for headers in table.at.values()]):
            for number, headers in enumerate(table.at.values()):
                server.client.cookies.clear()
                assert tap_weiter(server, headers, table.table_id, f"command-weiter-{number}").status_code == 200

        assert table.record.hand is not None
        assert table.record.dealer == next_dealer(DEALER_SEAT)

    def test_a_give_up_while_the_declarers_own_request_stands_is_pending(self, eight_cards):
        gives_up(eight_cards, MIDDLEHAND)

        eight_cards.refused_act(TABLE_GIVE_UP_SUFFIX, eight_cards.at[FOREHAND], Refusal.REQUEST_PENDING)
        assert everyone_reads(eight_cards) == [asked_by(MIDDLEHAND)] * 4

    @pytest.mark.parametrize("route", [TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX])
    @pytest.mark.parametrize("position", [FOREHAND, MIDDLEHAND, REARHAND], ids=lambda position: position.name)
    def test_an_answer_with_nothing_asked_has_no_request(self, herz_hand, route, position):
        herz_hand.refused_act(route, herz_hand.at[position], Refusal.NO_REQUEST)


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
        ended_by_giving_up(herz_hand, FOREHAND)

        herz_hand.refused_act(TABLE_GIVE_UP_SUFFIX, herz_hand.at[FOREHAND], Refusal.NO_HAND)

    def test_an_opponent_retrying_his_give_up_with_the_same_id_and_version_changes_the_table_once(self, herz_hand):
        body = {"command_id": "command-ask", "version": herz_hand.record.version}
        first = give_up(herz_hand, FOREHAND, body=body)
        stored_record = herz_hand.record

        again = give_up(herz_hand, FOREHAND, body=body)

        assert (again.status_code, again.json()) == (200, first.json())
        assert herz_hand.record == stored_record
        assert len(herz_hand.record.game_list) == 1


class TestThePartnerIsAsked:
    """The special rule "Partner muss zustimmen": an opponent's give-up ends the game only with his partner's yes."""

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
        self, partner_table, position, played_before, on_turn
    ):
        partner_table.played_out(played_before)
        before = partner_table.record

        answer = gives_up(partner_table, position)

        assert partner_table.record.version == before.version + 1
        assert partner_table.record.hand is not None
        assert partner_table.record.game_list == ()
        assert answer.json()["hand"]["playing"]["give_up"] == asked_by(position)
        assert everyone_reads(partner_table) == [asked_by(position)] * 4
        assert playing_as(partner_table, partner_table.at[on_turn])["legal_cards"] == []

    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_partners_yes_ends_the_game_won_as_declared_by_the_opponent_who_asked(self, partner_table, position):
        gives_up(partner_table, position)

        result = partner_agreed(partner_table, partner_of(position))

        assert shown(result, HERZ_HAND_RESULT) == HERZ_HAND_RESULT
        assert ending_of(result) == ("given-up", SEAT[position])
        assert partner_table.record.hand is None
        assert len(partner_table.record.game_list) == 1

    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_partners_no_keeps_the_game_going_with_one_version(self, partner_table, position):
        partner_table.played_out(EIGHT_CARDS)
        gives_up(partner_table, position)
        before = partner_table.record

        answer = decline(partner_table, partner_of(position))

        assert answer.status_code == 200, answer.text
        assert partner_table.record.version == before.version + 1
        assert partner_table.record.hand is not None
        assert partner_table.record.progress.give_up is None
        assert everyone_reads(partner_table) == [None] * 4
        assert playing_as(partner_table, partner_table.at[REARHAND])["legal_cards"] != []

    def test_the_game_played_on_after_the_no_is_scored_by_its_play_alone(self, partner_table):
        gives_up(partner_table, FOREHAND)
        assert decline(partner_table).status_code == 200

        partner_table.played_out(HERZ_GAME)

        result = partner_table.result()
        expected = HERZ_HAND_RESULT | {"declarer_points": 70, "opponents_points": 50}
        assert shown(result, expected) == expected
        assert ending_of(result) == ("played-out", None)

    @pytest.mark.parametrize("position", OPPONENTS)
    def test_an_opponent_may_give_up_again_after_the_no_and_the_request_is_new(self, partner_table, position):
        gives_up(partner_table, FOREHAND)
        assert decline(partner_table).status_code == 200
        before = partner_table.record.version

        gives_up(partner_table, position)

        assert partner_table.record.version == before + 1
        assert everyone_reads(partner_table) == [asked_by(position)] * 4

    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_partners_give_up_and_his_own_again_change_nothing(self, partner_table, position):
        gives_up(partner_table, position)
        before = partner_table.record

        for each in (partner_of(position), position):
            again = give_up(partner_table, each)

            assert again.status_code == 200, again.text
            assert partner_table.record == before
            assert everyone_reads(partner_table) == [asked_by(position)] * 4

    @pytest.mark.parametrize(
        ("answer", "entries"), [pytest.param(agree, 1, id="yes"), pytest.param(decline, 0, id="no")]
    )
    def test_an_answer_retried_with_the_same_id_and_version_answers_the_same_and_changes_the_table_once(
        self, partner_table, answer, entries
    ):
        gives_up(partner_table, FOREHAND)
        body = {"command_id": "command-answer", "version": partner_table.record.version}
        first = answer(partner_table, body=body)
        stored_record = partner_table.record

        again = answer(partner_table, body=body)

        assert (again.status_code, again.json()) == (200, first.json())
        assert partner_table.record == stored_record
        assert len(partner_table.record.game_list) == entries

    def test_the_same_id_with_another_version_is_reused(self, partner_table):
        gives_up(partner_table, FOREHAND)
        version = partner_table.record.version
        gives_up_again = {"command_id": "command-ask", "version": version}
        assert give_up(partner_table, REARHAND, body=gives_up_again).status_code == 200

        again = give_up(partner_table, REARHAND, body={"command_id": "command-ask", "version": version - 1})

        assert again.status_code == 409
        assert "reused" in again.json()["detail"]


class TestWhileTheGameWaitsForThePartner:
    @pytest.fixture
    def waiting(self, partner_table):
        partner_table.played_out(EIGHT_CARDS)
        gives_up(partner_table, FOREHAND)
        return partner_table

    @pytest.mark.parametrize(
        ("position", "played"),
        [
            pytest.param(MIDDLEHAND, "H8", id="the-declarer"),
            pytest.param(REARHAND, "D7", id="rearhand-on-turn"),
            pytest.param(FOREHAND, "C9", id="forehand"),
        ],
    )
    def test_a_card_from_each_seat_is_pending_before_the_engine_refuses_it(self, waiting, position, played):
        waiting.refused(waiting.at[position], card(played), Refusal.REQUEST_PENDING)

        assert playing_as(waiting, waiting.at[position])["legal_cards"] == []

    @pytest.mark.parametrize("position", [MIDDLEHAND, REARHAND, FOREHAND], ids=lambda position: position.name)
    def test_a_throw_down_from_each_side_is_pending(self, waiting, position):
        waiting.refused_act(TABLE_THROW_DOWN_SUFFIX, waiting.at[position], Refusal.REQUEST_PENDING)

    def test_the_declarers_give_up_is_pending(self, waiting):
        waiting.refused_act(TABLE_GIVE_UP_SUFFIX, waiting.at[MIDDLEHAND], Refusal.REQUEST_PENDING)

    @pytest.mark.parametrize("route", [TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX])
    def test_the_declarer_answering_is_not_an_opponent(self, waiting, route):
        waiting.refused_act(route, waiting.at[MIDDLEHAND], PlayRefusal.NOT_AN_OPPONENT)

    @pytest.mark.parametrize("route", [TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX])
    def test_the_opponent_answering_his_own_give_up_has_already_answered(self, waiting, route):
        waiting.refused_act(route, waiting.at[FOREHAND], Refusal.ALREADY_ANSWERED)


class TestWhatTheViewsOfferWhileItWaits:
    def test_no_viewer_has_a_card_or_a_word_to_play_and_all_come_back_after_the_no(self, partner_kontra_table):
        gives_up(partner_kontra_table, REARHAND)

        for headers in partner_kontra_table.at.values():
            playing = playing_as(partner_kontra_table, headers)
            assert (playing["legal_cards"], playing["kontra"]["my_word"]) == ([], None)
        assert everyone_reads(partner_kontra_table) == [asked_by(REARHAND)] * 4

        assert decline(partner_kontra_table, FOREHAND).status_code == 200

        assert playing_as(partner_kontra_table, partner_kontra_table.at[FOREHAND])["legal_cards"] != []
        assert playing_as(partner_kontra_table, partner_kontra_table.at[FOREHAND])["kontra"]["my_word"] == "kontra"
        assert everyone_reads(partner_kontra_table) == [None] * 4

    def test_every_stream_carries_the_request_with_no_card_or_word_to_play_and_then_the_no(self, partner_kontra_table):
        with everyones_streams(partner_kontra_table) as streams:
            gives_up(partner_kontra_table, REARHAND)
            waiting = [
                (position, next(frame for frame in stream if frame["hand"]["playing"]["give_up"] is not None))
                for position, stream in streams
            ]

            assert decline(partner_kontra_table, FOREHAND).status_code == 200
            playing_on = [(position, next(stream)) for position, stream in streams]

        for position, frame in waiting:
            playing = frame["hand"]["playing"]
            assert playing["give_up"] == asked_by(REARHAND)
            assert (playing["legal_cards"], playing["kontra"]["my_word"]) == ([], None)
            assert cards_in(frame) == own_cards_of(position)
        for position, frame in playing_on:
            assert frame["hand"]["playing"]["give_up"] is None
            assert cards_in(frame) == own_cards_of(position)
        (forehand,) = (frame["hand"]["playing"] for position, frame in playing_on if position is FOREHAND)
        assert (forehand["legal_cards"] != [], forehand["kontra"]["my_word"]) == (True, "kontra")

    def test_a_word_and_the_answer_of_no_word_are_pending_on_the_routes(self, partner_kontra_table):
        gives_up(partner_kontra_table, FOREHAND)

        partner_kontra_table.refused_act(
            TABLE_KONTRA_SUFFIX, partner_kontra_table.at[REARHAND], Refusal.REQUEST_PENDING, body={"word": "kontra"}
        )
        partner_kontra_table.refused_act(
            TABLE_NO_WORD_SUFFIX, partner_kontra_table.at[REARHAND], Refusal.REQUEST_PENDING
        )


class TestThroughTheMcpTools(IssuerSkat):
    """An agent opponent gives up for his side; an agent partner answers his partner's give-up."""

    def give_up_as(self, agent, table):
        skat_client = table.skat.client
        skat_client.cookies.clear()
        return agent.call(
            GIVE_UP_GAME_TOOL, table_id=table.table_id, command_id="agent-give-up-0001", version=table.record.version
        )

    @pytest.fixture
    def partner_asked(self, skat, agent):
        """The agent holds the rearhand chair; the person in the forehand chair, its partner, has given up."""
        table = AgentTable(skat, agent, REARHAND, options=PARTNER_AGREES)
        table.declared_hand_game()
        assert table.act(TABLE_GIVE_UP_SUFFIX, table.at[FOREHAND]).status_code == 200
        skat.client.cookies.clear()
        return table

    def answer(self, agent, table, tool, *, command_id="agent-answer-0001"):
        return agent.call(tool, table_id=table.table_id, command_id=command_id, version=table.record.version)

    def test_the_agent_opponents_give_up_ends_the_game_won_for_the_declarer(self, skat, agent):
        table = AgentTable(skat, agent, FOREHAND)
        table.declared_hand_game()

        answer = self.give_up_as(agent, table)

        assert not answer.is_error, answer.text
        result = agent.read(table.table_id).json()["result"]
        assert (result["won"], result["declarer_points"]) == (True, 120)
        assert ending_of(result) == ("given-up", 3)

    def test_the_agent_opponents_give_up_waits_for_the_partner_with_no_card_to_play(self, skat, agent):
        table = AgentTable(skat, agent, FOREHAND, options=PARTNER_AGREES)
        table.declared_hand_game()

        answer = self.give_up_as(agent, table)

        assert not answer.is_error, answer.text
        playing = agent.read(table.table_id).json()["hand"]["playing"]
        assert playing["give_up"] == {"asking_seat": 3, "declined_seat": None}
        assert playing["legal_cards"] == []
        assert table.act(TABLE_GIVE_UP_AGREE_SUFFIX, table.at[REARHAND]).status_code == 200
        assert ending_of(agent.read(table.table_id).json()["result"]) == ("given-up", 3)

    def test_the_agent_partners_yes_ends_the_game_under_its_partners_name(self, agent, partner_asked):
        answer = self.answer(agent, partner_asked, AGREE_TO_GIVE_UP_TOOL)

        assert not answer.is_error, answer.text
        result = agent.read(partner_asked.table_id).json()["result"]
        assert (result["won"], result["list_bonus"]) == (True, 50)
        assert ending_of(result) == ("given-up", 3)
        assert len(partner_asked.record.game_list) == 1

    def test_the_agent_partners_no_keeps_the_game_going(self, agent, partner_asked):
        answer = self.answer(agent, partner_asked, DECLINE_GIVE_UP_TOOL)

        assert not answer.is_error, answer.text
        assert agent.read(partner_asked.table_id).json()["hand"]["playing"]["give_up"] is None
        assert partner_asked.record.hand is not None
        assert partner_asked.read_as(partner_asked.at[FOREHAND]).json()["hand"]["playing"]["legal_cards"] != []
