import pytest

from skat.engine.deal import Position
from skat.engine.tricks import PlayRefusal
from skat.table.records import Refusal
from skat.web.mcp import AGREE_TO_GIVE_UP_TOOL, DECLINE_GIVE_UP_TOOL, PLAY_OPEN_TOOL
from skat.web.playing import (
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_PLAY_OPEN_SUFFIX,
    TABLE_SHORTEN_SUFFIX,
    TABLE_THROW_DOWN_SUFFIX,
)
from tests.support.payload_cards import cards_in, wire_cards
from tests.web.support.giving_up import SEAT, everyones_streams, own_cards_of, playing_as
from tests.web.support.open_play import (
    NINE_TRICKS,
    asked_to_play_open,
    declarer_accepts,
    declarer_plays_on,
    open_hands_read,
    open_play_read,
    opponents_cards,
    plays_open,
    waiting_for,
)
from tests.web.support.playing import HERZ_GAME, Table, ending_of
from tests.web.support.shortening import (
    everyone,
    herz_hand_with_63_points_against,
    herz_hand_won_by_tricks_and_skat,
    shortens,
)
from tests.web.support.skat import AgentTable, Skat

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
OPPONENTS = [pytest.param(FOREHAND, id="forehand"), pytest.param(REARHAND, id="rearhand")]


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


class TestTheDeclarerCouldTakeNoFurtherTrick:
    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_game_ends_at_once_by_the_opponents_seat_and_every_viewer_reads_the_ending(self, herz_hand, position):
        herz_hand.played_out(NINE_TRICKS)

        answer = plays_open(herz_hand, position)

        assert answer.status_code == 200, answer.text
        assert herz_hand.record.hand is None
        assert herz_hand.endings_in_every_view() == {("played-open", SEAT[position])}
        assert answer.json()["result"]["declarer_points"] == herz_hand.result()["declarer_points"]

    def test_the_rest_of_the_game_goes_to_the_opponents(self, herz_hand):
        herz_hand.played_out(NINE_TRICKS)

        plays_open(herz_hand, FOREHAND)

        result = herz_hand.result()
        assert (result["won"], result["declarer_points"], result["opponents_points"]) == (True, 70, 50)
        (entry,) = herz_hand.record.game_list
        assert (entry.declarer_points, entry.won) == (70, True)

    def test_a_retry_with_the_same_id_and_version_ends_the_game_once(self, herz_hand):
        herz_hand.played_out(NINE_TRICKS)
        body = {"command_id": "command-open", "version": herz_hand.record.version}
        first = plays_open(herz_hand, FOREHAND, body=body)
        stored = herz_hand.record

        again = plays_open(herz_hand, FOREHAND, body=body)

        assert (again.status_code, again.json()) == (200, first.json())
        assert herz_hand.record == stored


class TestAWrongOpenPlay:
    def test_the_declarer_is_asked_and_every_viewer_reads_who_played_open_and_no_card_moves(self, herz_hand):
        before = herz_hand.record

        answer = asked_to_play_open(herz_hand, FOREHAND)

        assert herz_hand.record.version == before.version + 1
        assert herz_hand.record.hand is not None
        assert herz_hand.record.game_list == ()
        assert answer.json()["hand"]["playing"]["open_play_seat"] == SEAT[FOREHAND]
        assert open_play_read(herz_hand) == waiting_for(FOREHAND)
        assert everyone(herz_hand, lambda each, headers: playing_as(each, headers)["give_up"]) == [None] * 4

    def test_while_the_declarer_decides_no_card_throw_down_give_up_or_shortening_is_taken(self, herz_hand):
        asked_to_play_open(herz_hand, FOREHAND)

        for suffix, position in (
            (TABLE_THROW_DOWN_SUFFIX, MIDDLEHAND),
            (TABLE_SHORTEN_SUFFIX, MIDDLEHAND),
            (TABLE_PLAY_OPEN_SUFFIX, REARHAND),
        ):
            herz_hand.refused_act(suffix, herz_hand.at[position], Refusal.REQUEST_PENDING)
        herz_hand.refused(herz_hand.at[FOREHAND], HERZ_GAME[0], Refusal.REQUEST_PENDING)


class TestWhoMayPlayOpen:
    def test_the_declarer_cannot_play_open_and_nothing_changes(self, herz_hand):
        herz_hand.refused_act(TABLE_PLAY_OPEN_SUFFIX, herz_hand.at[MIDDLEHAND], PlayRefusal.NOT_AN_OPPONENT)

    def test_a_standing_give_up_of_the_declarer_is_pending(self, herz_hand):
        herz_hand.played_out(HERZ_GAME[:4])
        assert herz_hand.act(TABLE_GIVE_UP_SUFFIX).status_code == 200

        herz_hand.refused_act(TABLE_PLAY_OPEN_SUFFIX, herz_hand.at[FOREHAND], Refusal.REQUEST_PENDING)

    def test_a_standing_shortening_is_pending(self, herz_hand):
        shortens(herz_hand)

        herz_hand.refused_act(TABLE_PLAY_OPEN_SUFFIX, herz_hand.at[FOREHAND], Refusal.REQUEST_PENDING)

    def test_a_dealt_hand_before_its_game_is_declared_has_nothing_to_play_open_in(self, table):
        table.refused_act(TABLE_PLAY_OPEN_SUFFIX, table.at[FOREHAND], Refusal.WRONG_PHASE)

    def test_a_table_between_hands_has_no_game_to_play_open_in(self, herz_hand):
        herz_hand.played_out(HERZ_GAME)

        herz_hand.refused_act(TABLE_PLAY_OPEN_SUFFIX, herz_hand.at[FOREHAND], Refusal.NO_HAND)


SCENES = [
    pytest.param(
        lambda table: table.declared_hand_game(),
        {"won": True, "game_value": 30, "schneider": False},
        id="undecided-is-won-by-its-declaration",
    ),
    pytest.param(
        herz_hand_won_by_tricks_and_skat,
        {"won": True, "opponents_points": 50, "declarer_points": 70, "game_value": 30},
        id="already-won-keeps-its-real-result",
    ),
    pytest.param(
        herz_hand_with_63_points_against,
        {"won": False, "opponents_points": 63, "declarer_points": 57},
        id="already-lost-counts-the-opponents-points-so-far",
    ),
]


class TestTheDeclarerAccepts:
    @pytest.mark.parametrize("position", OPPONENTS)
    @pytest.mark.parametrize(("scene", "expected"), SCENES)
    def test_the_game_ends_at_once_scored_by_the_three_branches_of_an_opponents_give_up(
        self, table, scene, expected, position
    ):
        scene(table)
        asked_to_play_open(table, position)

        result = declarer_accepts(table).json()["result"]

        assert {key: result[key] for key in expected} == expected
        assert table.record.hand is None
        assert table.endings_in_every_view() == {("played-open", SEAT[position])}
        (entry,) = table.record.game_list
        assert (entry.declarer_points, entry.won) == (result["declarer_points"], result["won"])

    def test_nobody_but_the_declarer_answers_a_wrong_open_play(self, herz_hand):
        asked_to_play_open(herz_hand, FOREHAND)

        for suffix in (TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX):
            for position in (FOREHAND, REARHAND):
                herz_hand.refused_act(suffix, herz_hand.at[position], Refusal.NOT_DECLARER)

    def test_a_retry_of_the_yes_with_the_same_id_and_version_ends_the_game_once(self, herz_hand):
        asked_to_play_open(herz_hand, FOREHAND)
        body = {"command_id": "command-accept", "version": herz_hand.record.version}
        first = herz_hand.act(TABLE_GIVE_UP_AGREE_SUFFIX, herz_hand.at[MIDDLEHAND], body=body)
        stored = herz_hand.record

        again = herz_hand.act(TABLE_GIVE_UP_AGREE_SUFFIX, herz_hand.at[MIDDLEHAND], body=body)

        assert (again.status_code, again.json()) == (200, first.json())
        assert herz_hand.record == stored


class TestTheDeclarerPlaysOn:
    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_game_goes_on_and_the_opponents_cards_are_open_to_every_viewer(self, herz_hand, position):
        asked_to_play_open(herz_hand, position)
        before = herz_hand.record

        answer = declarer_plays_on(herz_hand)

        assert herz_hand.record.version == before.version + 1
        assert herz_hand.record.hand is not None
        assert herz_hand.record.game_list == ()
        assert answer.json()["hand"]["playing"]["open_play_seat"] is None
        assert open_play_read(herz_hand) == [None] * 4
        assert open_hands_read(herz_hand) == [{SEAT[position]: opponents_cards(position)}] * 4
        assert playing_as(herz_hand, herz_hand.at[FOREHAND])["legal_cards"] != []

    def test_nothing_is_shown_while_the_declarer_decides_and_nothing_else_after_his_no(self, herz_hand):
        with everyones_streams(herz_hand) as streams:
            asked_to_play_open(herz_hand, REARHAND)
            asked = [(position, next(stream)) for position, stream in streams]
            declarer_plays_on(herz_hand)
            answered = [(position, next(stream)) for position, stream in streams]

        for position, frame in asked:
            assert cards_in(frame) == own_cards_of(position)
        for position, frame in answered:
            assert cards_in(frame) == own_cards_of(position) | opponents_cards(REARHAND)
            assert frame["hand"]["playing"]["open_hands"][0]["seat"] == SEAT[REARHAND]

    def test_the_cards_stay_open_as_they_are_played_and_the_game_is_scored_by_its_play_alone(self, herz_hand):
        asked_to_play_open(herz_hand, FOREHAND)
        declarer_plays_on(herz_hand)

        herz_hand.played_out(HERZ_GAME[:3])

        assert (
            open_hands_read(herz_hand) == [{SEAT[FOREHAND]: opponents_cards(FOREHAND) - wire_cards([HERZ_GAME[0]])}] * 4
        )

        herz_hand.played_out(HERZ_GAME[3:])

        result = herz_hand.result()
        assert (result["won"], result["declarer_points"], result["opponents_points"]) == (True, 70, 50)
        assert ending_of(result) == ("played-out", None)

    def test_both_opponents_playing_open_leave_both_hands_open_and_the_same_opponent_again_adds_nothing(
        self, herz_hand
    ):
        for position in (REARHAND, FOREHAND, FOREHAND):
            asked_to_play_open(herz_hand, position)
            declarer_plays_on(herz_hand)

        assert (
            open_hands_read(herz_hand)
            == [{SEAT[REARHAND]: opponents_cards(REARHAND), SEAT[FOREHAND]: opponents_cards(FOREHAND)}] * 4
        )

    def test_an_open_play_that_is_right_later_still_ends_the_game_with_the_cards_open(self, herz_hand):
        asked_to_play_open(herz_hand, FOREHAND)
        declarer_plays_on(herz_hand)
        herz_hand.played_out(NINE_TRICKS)

        plays_open(herz_hand, FOREHAND)

        assert herz_hand.endings_in_every_view() == {("played-open", SEAT[FOREHAND])}

    def test_the_next_hand_starts_with_nothing_open(self, herz_hand):
        asked_to_play_open(herz_hand, FOREHAND)
        declarer_plays_on(herz_hand)

        herz_hand.played_out(HERZ_GAME)

        assert herz_hand.record.progress.played_open == frozenset()
        assert herz_hand.record.progress.give_up is None


def restarted(skat, hold, **options):
    """The same stores under a freshly built app, as after a restart."""
    return Skat(lambda: hold, store=skat.store, stores=skat.stores, **options)


class TestAcrossARestart:
    @pytest.fixture
    def skat(self, hold):
        return Skat(lambda: hold)

    def test_a_waiting_open_play_is_read_after_a_restart_and_the_declarers_yes_ends_the_game(
        self, skat, hold, herz_hand
    ):
        asked_to_play_open(herz_hand, FOREHAND)

        herz_hand.skat = restarted(skat, hold)

        assert open_play_read(herz_hand) == waiting_for(FOREHAND)
        declarer_accepts(herz_hand)
        assert herz_hand.endings_in_every_view() == {("played-open", SEAT[FOREHAND])}

    def test_a_no_keeps_the_opponents_cards_open_after_a_restart_while_play_goes_on(self, skat, hold, herz_hand):
        asked_to_play_open(herz_hand, FOREHAND)
        declarer_plays_on(herz_hand)

        herz_hand.skat = restarted(skat, hold)

        assert open_hands_read(herz_hand) == [{SEAT[FOREHAND]: opponents_cards(FOREHAND)}] * 4
        herz_hand.accepted(HERZ_GAME[0])
        assert (
            open_hands_read(herz_hand) == [{SEAT[FOREHAND]: opponents_cards(FOREHAND) - wire_cards([HERZ_GAME[0]])}] * 4
        )


class TestThroughTheMcpTools:
    @pytest.fixture
    def skat(self, hold, issuer):
        skat = Skat(lambda: hold, issuer_transports=issuer.transports)
        with skat.client:
            yield skat

    def test_an_agent_opponent_plays_open_and_the_person_declarer_accepts(self, skat, agent):
        table = AgentTable(skat, agent, FOREHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()

        answer = agent.take_step(PLAY_OPEN_TOOL, table, command_id="agent-open-0001")

        assert not answer.is_error, answer.text
        assert agent.read(table.table_id).json()["hand"]["playing"]["open_play_seat"] == SEAT[FOREHAND]
        declarer_accepts(table)
        assert ending_of(agent.read(table.table_id).json()["result"]) == ("played-open", SEAT[FOREHAND])

    def test_an_agent_opponent_ends_the_game_by_a_right_open_play(self, skat, agent):
        table = AgentTable(skat, agent, FOREHAND)
        table.declared_hand_game()
        table.played_out(NINE_TRICKS)
        skat.client.cookies.clear()

        answer = agent.take_step(PLAY_OPEN_TOOL, table, command_id="agent-open-0002")

        assert not answer.is_error, answer.text
        assert ending_of(agent.read(table.table_id).json()["result"]) == ("played-open", SEAT[FOREHAND])

    @pytest.mark.parametrize(
        ("tool", "ending"),
        [
            pytest.param(AGREE_TO_GIVE_UP_TOOL, ("played-open", SEAT[FOREHAND]), id="accepts"),
            pytest.param(DECLINE_GIVE_UP_TOOL, None, id="plays-on"),
        ],
    )
    def test_an_agent_declarer_answers_the_opponents_open_play_with_the_give_up_answer_tools(
        self, skat, agent, tool, ending
    ):
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.declared_hand_game()
        asked_to_play_open(table, FOREHAND)
        skat.client.cookies.clear()

        answer = agent.take_step(tool, table, command_id="agent-answer-0001")

        assert not answer.is_error, answer.text
        read = agent.read(table.table_id).json()
        if ending is None:
            assert [each["seat"] for each in read["hand"]["playing"]["open_hands"]] == [SEAT[FOREHAND]]
        else:
            assert ending_of(read["result"]) == ending

    def test_the_agent_declarer_cannot_play_open(self, skat, agent):
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()

        answer = agent.take_step(PLAY_OPEN_TOOL, table, command_id="agent-open-0003")

        assert answer.is_error
        assert answer.json()["reason"] == PlayRefusal.NOT_AN_OPPONENT
