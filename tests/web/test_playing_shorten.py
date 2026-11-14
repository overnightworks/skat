import pytest

from skat.engine.tricks import PlayRefusal
from skat.table.game_list import GameEnding
from skat.table.records import Refusal
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.mcp import AGREE_TO_GIVE_UP_TOOL, DECLINE_GIVE_UP_TOOL, READ_SERIES_LIST_TOOL, SHORTEN_GAME_TOOL
from skat.web.playing import (
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_SHORTEN_SUFFIX,
    TABLE_THROW_DOWN_SUFFIX,
)
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import cards_in, cards_in_text, wire_cards
from tests.web.support.agent import Agent
from tests.web.support.giving_up import (
    HEAVY_DEAL,
    HEAVY_THREE_TRICKS,
    SEAT,
    assert_the_request_ended_and_play_goes_on,
    everyones_streams,
    own_cards_of,
    playing_as,
)
from tests.web.support.playing import HERZ_GAME, Table, ending_of
from tests.web.support.series import tap_weiter
from tests.web.support.shortening import (
    FOREHAND,
    MIDDLEHAND,
    NONE,
    REARHAND,
    SCHNEIDER,
    SCHWARZ,
    SETTLED_GAMES,
    asked,
    both_say_yes,
    declarers_cards,
    everyone,
    herz_hand_with_63_points_against,
    null_before_a_trick,
    open_cards_read,
    refusals_read,
    says_no,
    says_yes,
    shorten,
    shortenings_read,
    shortens,
)
from tests.web.support.skat import AgentTable, Skat, streams_of

OPPONENTS = [pytest.param(FOREHAND, id="forehand"), pytest.param(REARHAND, id="rearhand")]
# The declarer holds eight cards once he has played to the second trick.
EIGHT_CARDS = HERZ_GAME[:4]


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


# The opponent who says no, and whom of the other opponents said yes before.
NO_AFTER_YES = pytest.mark.parametrize(
    ("no", "earlier_yes"),
    [
        pytest.param(FOREHAND, (), id="forehand-no"),
        pytest.param(REARHAND, (), id="rearhand-no"),
        pytest.param(FOREHAND, (REARHAND,), id="forehand-no-after-rearhand-yes"),
        pytest.param(REARHAND, (FOREHAND,), id="rearhand-no-after-forehand-yes"),
    ],
)


def list_entry_of(table):
    answer = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher)
    assert answer.status_code == 200, answer.text
    (entry,) = answer.json()["entries"]
    return entry


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
            frames = [
                (position, next(frame for frame in stream if frame["hand"]["playing"]["shortening"] is not None))
                for position, stream in streams
            ]

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

    @SETTLED_GAMES
    def test_the_engines_settlement_decides_a_game_already_decided_and_the_list_entry_counts_the_same_points(
        self, table, scene, claim, expected
    ):
        scene(table)
        shortens(table, claim)

        result = both_say_yes(table)

        assert {key: result[key] for key in expected} == expected
        assert ending_of(result) == ("shortened", SEAT[MIDDLEHAND])
        (entry,) = table.record.game_list
        assert (entry.declarer_points, entry.settled_value, entry.score) == (
            result["declarer_points"],
            result["settled_value"],
            result["score"],
        )
        listed = list_entry_of(table)
        assert (listed["declarer_points"], listed["settled_value"], listed["score"]) == (
            result["declarer_points"],
            result["settled_value"],
            result["score"],
        )

    def test_every_stream_carries_the_same_result_and_no_card_after_the_second_yes(self, herz_hand):
        shortens(herz_hand)
        says_yes(herz_hand, FOREHAND)
        with everyones_streams(herz_hand) as streams:
            says_yes(herz_hand, REARHAND)
            frames = [next(frame for frame in stream if frame["result"] is not None) for _, stream in streams]

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

        assert_the_request_ended_and_play_goes_on(herz_hand, before, answer, "shortening")
        assert shortenings_read(herz_hand) == [None] * 4
        assert refusals_read(herz_hand) == [SEAT[position]] * 4

    @NO_AFTER_YES
    def test_the_declarers_cards_are_open_to_every_viewer_and_nothing_else_is(self, herz_hand, no, earlier_yes):
        shortens(herz_hand)
        for opponent in earlier_yes:
            says_yes(herz_hand, opponent)

        says_no(herz_hand, no)

        assert open_cards_read(herz_hand) == [declarers_cards()] * 4
        viewers = {None: herz_hand.watcher, **herz_hand.at}
        for viewer, headers in viewers.items():
            assert cards_in_text(herz_hand.read_as(headers).text) == own_cards_of(viewer) | declarers_cards()

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

    @NO_AFTER_YES
    def test_every_stream_carries_the_declarers_cards_after_the_no_and_no_other_hidden_card(
        self, herz_hand, no, earlier_yes
    ):
        shortens(herz_hand)
        for opponent in earlier_yes:
            says_yes(herz_hand, opponent)
        with everyones_streams(herz_hand) as streams:
            says_no(herz_hand, no)
            frames = [
                (
                    position,
                    next(frame for frame in stream if frame["hand"]["playing"]["shortening_refused_seat"] is not None),
                )
                for position, stream in streams
            ]

        for position, frame in frames:
            assert cards_in(frame) == own_cards_of(position) | declarers_cards()
            assert frame["hand"]["playing"]["shortening_refused_seat"] == SEAT[no]
            assert frame["hand"]["playing"]["shortening"] is None


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


def restarted(skat, hold, **options):
    """The same stores under a freshly built app, as after a restart."""
    return Skat(lambda: hold, store=skat.store, stores=skat.stores, **options)


class TestARequestAcrossARestart:
    @pytest.fixture
    def skat(self, hold):
        return Skat(lambda: hold)

    @pytest.mark.parametrize(
        ("earlier_yes", "agreed", "then_yes"),
        [
            pytest.param((), None, (FOREHAND, REARHAND), id="unanswered"),
            pytest.param((FOREHAND,), SEAT[FOREHAND], (REARHAND,), id="one-yes"),
        ],
    )
    def test_an_unanswered_request_and_a_yes_are_read_after_a_restart_and_the_last_yes_ends_the_game(
        self, skat, hold, herz_hand, earlier_yes, agreed, then_yes
    ):
        shortens(herz_hand, SCHNEIDER)
        for opponent in earlier_yes:
            says_yes(herz_hand, opponent)

        herz_hand.skat = restarted(skat, hold)

        assert shortenings_read(herz_hand) == [asked(SCHNEIDER, agreed)] * 4
        for opponent in then_yes:
            says_yes(herz_hand, opponent)
        result = herz_hand.result()
        assert (result["won"], result["game_value"], result["schneider"]) == (True, 40, True)
        assert ending_of(result) == ("shortened", SEAT[MIDDLEHAND])

    def test_a_no_keeps_the_declarers_cards_open_after_a_restart_while_play_goes_on(self, skat, hold, herz_hand):
        shortens(herz_hand)
        says_no(herz_hand, FOREHAND)

        herz_hand.skat = restarted(skat, hold)

        assert open_cards_read(herz_hand) == [declarers_cards()] * 4
        assert refusals_read(herz_hand) == [SEAT[FOREHAND]] * 4
        herz_hand.accepted(HERZ_GAME[0])
        assert open_cards_read(herz_hand) == [declarers_cards()] * 4


class TestThroughTheMcpTools:
    """An agent declarer shortens; agent opponents answer."""

    @pytest.fixture
    def skat(self, hold, issuer):
        skat = Skat(lambda: hold, issuer_transports=issuer.transports)
        with skat.client:
            yield skat

    @pytest.fixture
    def declarer_asked(self, skat, agent):
        """The agent holds the declarer's chair and has shortened the game through the tool."""
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()
        answer = agent.take_step(SHORTEN_GAME_TOOL, table, command_id="agent-shorten-0001", claim=SCHNEIDER)
        assert not answer.is_error, answer.text
        return table

    @pytest.fixture
    def opponent_asked(self, skat, agent):
        """The agent holds the forehand chair, on turn; the person in the middlehand chair has shortened the game."""
        table = AgentTable(skat, agent, FOREHAND)
        table.declared_hand_game()
        shortens(table)
        skat.client.cookies.clear()
        return table

    def test_the_agent_declarer_shortens_with_a_demand_and_the_persons_yes_ends_the_game(self, agent, declarer_asked):
        assert agent.read(declarer_asked.table_id).json()["hand"]["playing"]["shortening"] == asked(SCHNEIDER)

        both_say_yes(declarer_asked)

        result = agent.read(declarer_asked.table_id).json()["result"]
        assert (result["won"], result["game_value"], result["schneider"]) == (True, 40, True)
        assert ending_of(result) == ("shortened", SEAT[MIDDLEHAND])

    @SETTLED_GAMES
    def test_the_engines_settlement_reaches_the_agent_and_its_list_entry_counts_the_same_points(
        self, skat, agent, scene, claim, expected
    ):
        table = AgentTable(skat, agent, MIDDLEHAND)
        scene(table)
        skat.client.cookies.clear()

        answer = agent.take_step(SHORTEN_GAME_TOOL, table, command_id="agent-shorten-0004", claim=claim)
        assert not answer.is_error, answer.text
        both_say_yes(table)

        result = agent.read(table.table_id).json()["result"]
        assert {key: result[key] for key in expected} == expected
        assert ending_of(result) == ("shortened", SEAT[MIDDLEHAND])
        (entry,) = table.record.game_list
        assert entry.declarer_points == result["declarer_points"]
        listed = agent.call(READ_SERIES_LIST_TOOL, table_id=table.table_id).json()["entries"]
        assert [(each["declarer_points"], each["settled_value"], each["score"]) for each in listed] == [
            (result["declarer_points"], result["settled_value"], result["score"])
        ]

    def test_the_agent_declarers_unreached_demand_is_a_failed_result(self, skat, agent):
        table = AgentTable(skat, agent, MIDDLEHAND)
        table.with_deal(HEAVY_DEAL)
        table.declared_hand_game()
        table.played_out(HEAVY_THREE_TRICKS)
        skat.client.cookies.clear()

        answer = agent.take_step(SHORTEN_GAME_TOOL, table, command_id="agent-shorten-0002", claim=SCHNEIDER)

        assert answer.is_error
        assert answer.json()["reason"] == PlayRefusal.CLAIM_OUT_OF_REACH
        assert shortenings_read(table) == [None] * 4

    @pytest.mark.parametrize(
        ("tool", "view"),
        [
            pytest.param(AGREE_TO_GIVE_UP_TOOL, {"shortening": asked(NONE, SEAT[FOREHAND])}, id="yes"),
            pytest.param(
                DECLINE_GIVE_UP_TOOL,
                {"shortening": None, "shortening_refused_seat": SEAT[FOREHAND]},
                id="no",
            ),
        ],
    )
    def test_an_agent_opponent_answers_the_shortening_with_the_give_up_answer_tools(
        self, agent, opponent_asked, tool, view
    ):
        answer = agent.take_step(tool, opponent_asked, command_id="agent-answer-0001")

        assert not answer.is_error, answer.text
        playing = agent.read(opponent_asked.table_id).json()["hand"]["playing"]
        assert {key: playing[key] for key in view} == view

    @pytest.mark.parametrize(
        "earlier_yes",
        [pytest.param((), id="first-answer"), pytest.param((REARHAND,), id="after-the-persons-yes")],
    )
    def test_the_agent_opponents_no_opens_the_declarers_cards_to_the_agent_and_every_viewer(
        self, agent, opponent_asked, earlier_yes
    ):
        for opponent in earlier_yes:
            says_yes(opponent_asked, opponent)
        opponent_asked.skat.client.cookies.clear()

        answer = agent.take_step(DECLINE_GIVE_UP_TOOL, opponent_asked, command_id="agent-answer-0002")

        assert not answer.is_error, answer.text
        assert open_cards_read(opponent_asked) == [declarers_cards()] * 4
        assert cards_in_text(agent.read(opponent_asked.table_id).text) == own_cards_of(FOREHAND) | declarers_cards()

    def test_a_card_played_by_the_agent_after_its_yes_ends_the_request_and_late_answers_find_none(
        self, agent, opponent_asked
    ):
        answer = agent.take_step(AGREE_TO_GIVE_UP_TOOL, opponent_asked, command_id="agent-answer-0003")
        assert not answer.is_error, answer.text

        played = agent.play(opponent_asked, HERZ_GAME[0], command_id="agent-move-0002")

        assert not played.is_error, played.text
        assert agent.read(opponent_asked.table_id).json()["hand"]["playing"]["shortening"] is None
        opponent_asked.refused_act(TABLE_GIVE_UP_AGREE_SUFFIX, opponent_asked.at[REARHAND], Refusal.NO_REQUEST)
        late = agent.take_step(AGREE_TO_GIVE_UP_TOOL, opponent_asked, command_id="agent-answer-0004")
        assert late.is_error
        assert late.json()["reason"] == Refusal.NO_REQUEST

    def test_a_card_played_by_a_person_ends_the_agent_declarers_request_with_nothing_opened(
        self, agent, declarer_asked
    ):
        says_yes(declarer_asked, FOREHAND)

        declarer_asked.accepted(HERZ_GAME[0])

        view = agent.read(declarer_asked.table_id).json()["hand"]
        assert (view["playing"]["shortening"], view["declaring"]["open_cards"]) == (None, [])

    @pytest.mark.parametrize(
        ("tool", "reason"),
        [
            pytest.param(AGREE_TO_GIVE_UP_TOOL, PlayRefusal.NOT_AN_OPPONENT, id="yes"),
            pytest.param(DECLINE_GIVE_UP_TOOL, PlayRefusal.NOT_AN_OPPONENT, id="no"),
        ],
    )
    def test_the_agent_declarer_cannot_answer_its_own_request(self, agent, declarer_asked, tool, reason):
        answer = agent.take_step(tool, declarer_asked, command_id="agent-answer-0005")

        assert answer.is_error
        assert answer.json()["reason"] == reason
        assert shortenings_read(declarer_asked) == [asked(SCHNEIDER)] * 4

    def test_the_agent_opponent_is_not_the_declarer_and_cannot_say_yes_twice(self, agent, opponent_asked):
        refused = agent.take_step(SHORTEN_GAME_TOOL, opponent_asked, command_id="agent-shorten-0005")
        assert refused.is_error
        assert refused.json()["reason"] == Refusal.NOT_DECLARER
        assert not agent.take_step(AGREE_TO_GIVE_UP_TOOL, opponent_asked, command_id="agent-answer-0006").is_error

        again = agent.take_step(AGREE_TO_GIVE_UP_TOOL, opponent_asked, command_id="agent-answer-0007")

        assert again.is_error
        assert again.json()["reason"] == Refusal.ALREADY_ANSWERED
        assert shortenings_read(opponent_asked) == [asked(NONE, SEAT[FOREHAND])] * 4

    def test_an_answer_with_nothing_asked_has_no_request(self, skat, agent):
        table = AgentTable(skat, agent, FOREHAND)
        table.declared_hand_game()
        skat.client.cookies.clear()

        answer = agent.take_step(AGREE_TO_GIVE_UP_TOOL, table, command_id="agent-answer-0008")

        assert answer.is_error
        assert answer.json()["reason"] == Refusal.NO_REQUEST

    @pytest.mark.parametrize(
        ("agent_says_yes_first", "agreed"),
        [pytest.param(False, None, id="unanswered"), pytest.param(True, SEAT[FOREHAND], id="one-yes")],
    )
    def test_the_request_and_the_yes_are_read_through_the_tools_after_a_restart(
        self, hold, issuer, skat, agent, opponent_asked, agent_says_yes_first, agreed
    ):
        if agent_says_yes_first:
            agree = agent.take_step(AGREE_TO_GIVE_UP_TOOL, opponent_asked, command_id="agent-answer-0009")
            assert not agree.is_error, agree.text
        after = restarted(skat, hold, issuer_transports=issuer.transports)
        opponent_asked.skat = after

        with after.client:
            returned = Agent(after, issuer)
            playing = returned.read(opponent_asked.table_id).json()["hand"]["playing"]
            assert playing["shortening"] == asked(NONE, agreed)
            if not agent_says_yes_first:
                agree = returned.take_step(AGREE_TO_GIVE_UP_TOOL, opponent_asked, command_id="agent-answer-0010")
                assert not agree.is_error, agree.text
            says_yes(opponent_asked, REARHAND)
            result = returned.read(opponent_asked.table_id).json()["result"]

        assert ending_of(result) == ("shortened", SEAT[MIDDLEHAND])
