from functools import partial

import pytest

from skat.engine.deal import Position
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_HOLD_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import TABLE_DECLARING_DECLARE_SUFFIX, GameToken
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.kontra import TABLE_KONTRA_SUFFIX, TABLE_NO_WORD_SUFFIX
from skat.web.playing import TABLE_GIVE_UP_SUFFIX, TABLE_THROW_DOWN_SUFFIX
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import with_known_deal
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import HERZ_GAME, Table, cards
from tests.web.support.presence import view_of_version
from tests.web.support.series import tap_weiter
from tests.web.support.skat import streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# Seat 2 deals: seat 3 is forehand, seat 1 middlehand (the declarer) and seat 2 rearhand.
SEAT = {FOREHAND: 3, MIDDLEHAND: 1, REARHAND: 2}
KONTRA_RE, WITH_STANDINGS, UP_TO_HIRSCH = "kontra-re", "kontra-re-standings", "up-to-hirsch"
ANY, BIDDERS = "any-opponent", "bidders-only"


def kontra_options(sayer=ANY, reach=KONTRA_RE, deadline="own-card"):
    return {"kontra": {"sayer": sayer, "reach": reach, "deadline": deadline}}


@pytest.fixture
def open_table(server, monkeypatch):
    """A table for the three people and a watcher, opened through the API with the options a test names."""

    def open_with(sayer=ANY, reach=KONTRA_RE, deadline="own-card"):
        monkeypatch.setattr(server, "create", partial(server.create, options=kontra_options(sayer, reach, deadline)))
        return Table(server)

    return open_with


@pytest.fixture
def herz_hand(open_table):
    table = open_table()
    table.declared_hand_game()
    return table


def say(table, position, word, *, headers=None, **changed):
    return table.act(TABLE_KONTRA_SUFFIX, headers or table.at[position], body={"word": word, **changed})


def said(table, position, word):
    answer = say(table, position, word)
    assert answer.status_code == 200, answer.text
    return answer


def refused(table, position, word, reason, *, headers=None):
    table.refused_act(TABLE_KONTRA_SUFFIX, headers or table.at[position], reason, body={"word": word})


def answered_no_word(table, position):
    answer = table.act(TABLE_NO_WORD_SUFFIX, table.at[position])
    assert answer.status_code == 200, answer.text
    return answer


def kontra_view(table, headers):
    return table.read_as(headers).json()["hand"]["playing"]["kontra"]


def play(table, *steps):
    """Cards of the Herz Hand game, in order, and words between them: a number plays that many cards."""
    game = iter(HERZ_GAME)
    for step in steps:
        if isinstance(step, int):
            for _ in range(step):
                table.accepted(next(game))
        else:
            said(table, *step)


def shown(result, *keys):
    return {key: result[key] for key in keys}


def gains_of(result):
    return [each["gain"] for each in result["gains"]]


SCORE_KEYS = ("settled_value", "game_value", "score", "list_bonus", "won", "overbid")


class TestTheDoubledScoreOfAPlayedGame:
    @pytest.mark.parametrize(
        ("reach", "steps", "kontra", "score", "list_bonus", "gains"),
        [
            pytest.param(KONTRA_RE, [(FOREHAND, "kontra"), 30], [("kontra", 2)], 60, 50, [110, 0, 0], id="1-kontra"),
            pytest.param(
                KONTRA_RE,
                [(FOREHAND, "kontra"), 1, (MIDDLEHAND, "re"), 29],
                [("kontra", 2), ("re", 4)],
                120,
                50,
                [170, 0, 0],
                id="2-re",
            ),
            pytest.param(
                UP_TO_HIRSCH,
                [(FOREHAND, "kontra"), 1, (MIDDLEHAND, "re"), 2, (FOREHAND, "supra"), (MIDDLEHAND, "hirsch"), 27],
                [("kontra", 2), ("re", 4), ("supra", 8), ("hirsch", 16)],
                480,
                50,
                [530, 0, 0],
                id="3-hirsch",
            ),
            pytest.param(
                WITH_STANDINGS, [(FOREHAND, "kontra"), 30], [("kontra", 2)], 60, 100, [160, 0, 0], id="5-standings"
            ),
        ],
    )
    def test_the_result_names_each_word_said_with_its_factor_and_scores_the_game_doubled(
        self, open_table, reach, steps, kontra, score, list_bonus, gains
    ):
        table = open_table(reach=reach)
        table.declared_hand_game()

        play(table, *steps)

        result = table.result()
        assert result["kontra"] == {"steps": [{"word": word, "factor": factor} for word, factor in kontra]}
        assert shown(result, *SCORE_KEYS) == {
            "settled_value": 30,
            "game_value": 30,
            "score": score,
            "list_bonus": list_bonus,
            "won": True,
            "overbid": False,
        }
        assert gains_of(result) == gains

    def test_a_game_without_a_word_names_no_doubling(self, herz_hand):
        play(herz_hand, 30)

        result = herz_hand.result()
        assert (result["kontra"], result["score"], gains_of(result)) == (None, 30, [80, 0, 0])

    @pytest.mark.parametrize(
        ("reach", "steps", "score", "list_bonus", "gains"),
        [
            pytest.param(
                WITH_STANDINGS,
                [(FOREHAND, "kontra"), (MIDDLEHAND, "re")],
                -240,
                -200,
                [-440, 160, 160],
                id="6-standings-given-up",
            ),
            pytest.param(KONTRA_RE, [(FOREHAND, "kontra")], -120, -50, [-170, 40, 40], id="7-given-up"),
        ],
    )
    def test_a_give_up_after_a_word_is_doubled_like_any_game(self, open_table, reach, steps, score, list_bonus, gains):
        table = open_table(reach=reach)
        table.declared_hand_game()
        play(table, *steps)

        answer = table.act(TABLE_GIVE_UP_SUFFIX)

        assert answer.status_code == 200, answer.text
        result = answer.json()["result"]
        assert (result["score"], result["list_bonus"], gains_of(result)) == (score, list_bonus, gains)

    def test_a_throw_down_after_a_word_is_doubled_like_any_game(self, herz_hand):
        said(herz_hand, FOREHAND, "kontra")

        answer = herz_hand.act(TABLE_THROW_DOWN_SUFFIX)

        result = answer.json()["result"]
        # Thrown down with ten cards the game scores -100 without a word.
        assert (result["score"], result["list_bonus"], gains_of(result)) == (-200, -50, [-250, 40, 40])

    def test_a_won_null_is_doubled_at_its_own_value(self, open_table):
        table = open_table()
        table.declared_after_putting_back(cards("H7 H8"), GameToken.NULL)
        said(table, FOREHAND, "kontra")

        answer = table.act(TABLE_THROW_DOWN_SUFFIX, table.at[FOREHAND])

        result = answer.json()["result"]
        assert (result["game_value"], result["score"], gains_of(result)) == (23, 46, [96, 0, 0])

    def test_an_overbid_game_keeps_its_value_and_doubles_its_list_score(self, open_table):
        table = open_table()
        table.declared_hand_game(bid=36)
        said(table, FOREHAND, "kontra")

        answer = table.act(TABLE_GIVE_UP_SUFFIX)

        result = answer.json()["result"]
        # Ohne 1, Spiel and Hand make 30 under a bid of 36: the value is raised to 40, lost doubled makes -80.
        assert shown(result, "overbid", "game_value", "settled_value", "score") == {
            "overbid": True,
            "game_value": 30,
            "settled_value": 40,
            "score": -160,
        }

    def test_the_chairs_totals_and_the_list_follow_the_doubled_game(self, herz_hand):
        play(herz_hand, (FOREHAND, "kontra"), 30)

        view = herz_hand.read_as(herz_hand.watcher).json()
        entries = herz_hand.skat.client.get(
            f"{TABLES_PATH}/{herz_hand.table_id}{TABLE_LIST_SUFFIX}", headers=herz_hand.watcher
        ).json()["entries"]

        assert [chair["total"] for chair in view["chairs"]] == [110, 0, 0]
        assert [(entry["score"], entry["settled_value"], entry["kontra_word"]) for entry in entries] == [
            (60, 30, "kontra")
        ]

    @pytest.mark.parametrize(
        ("steps", "word"),
        [
            pytest.param([(FOREHAND, "kontra"), (MIDDLEHAND, "re")], "re", id="doubled"),
            pytest.param([], None, id="undoubled"),
        ],
    )
    def test_a_list_row_names_the_last_word_or_none(self, herz_hand, steps, word):
        play(herz_hand, *steps)
        herz_hand.act(TABLE_GIVE_UP_SUFFIX)

        entries = herz_hand.skat.client.get(
            f"{TABLES_PATH}/{herz_hand.table_id}{TABLE_LIST_SUFFIX}", headers=herz_hand.watcher
        ).json()["entries"]

        assert [entry["kontra_word"] for entry in entries] == [word]


class TestTheFirstCardDeadline:
    @pytest.fixture
    def first_card_hand(self, open_table):
        table = open_table(deadline="first-card")
        table.declared_hand_game()
        return table

    def first_card_refused(self, table, reason="words-due"):
        table.refused(table.at[FOREHAND], HERZ_GAME[0], reason)

    def test_the_first_card_is_refused_until_both_opponents_said_a_word_or_answered_no_word(self, first_card_hand):
        table = first_card_hand
        self.first_card_refused(table)

        answered_no_word(table, FOREHAND)
        self.first_card_refused(table)
        answered_no_word(table, REARHAND)

        table.accepted(HERZ_GAME[0])

    def test_the_view_of_every_viewer_tells_that_the_first_card_waits_on_a_word_until_the_words_are_in(
        self, first_card_hand
    ):
        table = first_card_hand
        viewers = (table.at[FOREHAND], table.at[MIDDLEHAND], table.watcher)
        waiting = [kontra_view(table, headers)["first_card_waits"] for headers in viewers]
        answered_no_word(table, FOREHAND)
        answered_no_word(table, REARHAND)
        decided = [kontra_view(table, headers)["first_card_waits"] for headers in viewers]

        assert (waiting, decided) == ([True] * 3, [False] * 3)

    def test_a_no_word_answer_is_a_decline_the_opponent_cannot_take_back_by_saying_kontra(self, first_card_hand):
        answered_no_word(first_card_hand, FOREHAND)
        before = first_card_hand.record

        answered_no_word(first_card_hand, FOREHAND)
        refused(first_card_hand, FOREHAND, "kontra", "not-your-word")

        assert first_card_hand.record == before

    def test_the_declarer_owes_re_to_a_kontra_and_the_opponent_left_with_no_word_is_not_awaited(self, first_card_hand):
        table = first_card_hand
        said(table, FOREHAND, "kontra")
        self.first_card_refused(table)

        said(table, MIDDLEHAND, "re")

        table.accepted(HERZ_GAME[0])

    def test_the_declarers_no_word_answer_to_a_kontra_clears_the_first_card(self, first_card_hand):
        said(first_card_hand, FOREHAND, "kontra")

        answered_no_word(first_card_hand, MIDDLEHAND)

        first_card_hand.accepted(HERZ_GAME[0])

    def test_where_the_table_asks_it_the_answer_of_an_opponent_who_never_bid_is_refused_and_he_is_not_awaited(
        self, open_table
    ):
        table = open_table(BIDDERS, deadline="first-card")
        contested_auction(table)
        self.first_card_refused(table)

        table.refused_act(TABLE_NO_WORD_SUFFIX, table.at[REARHAND], "did-not-bid")
        answered_no_word(table, FOREHAND)

        table.accepted(HERZ_GAME[0])

    def test_the_table_with_the_time_of_the_own_card_plays_the_first_card_at_once(self, herz_hand):
        herz_hand.accepted(HERZ_GAME[0])
        assert kontra_view(herz_hand, herz_hand.watcher)["first_card_waits"] is False


class TestTheDeadlines:
    def test_forehand_who_led_says_no_kontra(self, herz_hand):
        play(herz_hand, 1)

        refused(herz_hand, FOREHAND, "kontra", "too-late")

    def test_rearhand_says_kontra_before_his_own_card_after_forehand_led(self, herz_hand):
        play(herz_hand, 2)

        said(herz_hand, REARHAND, "kontra")

        assert kontra_view(herz_hand, herz_hand.at[REARHAND])["factor"] == 2

    def test_the_declarer_who_played_his_next_card_says_no_re(self, herz_hand):
        play(herz_hand, (FOREHAND, "kontra"), 2)

        refused(herz_hand, MIDDLEHAND, "re", "too-late")

    def test_a_word_waits_for_nobody_and_play_goes_on_without_it(self, herz_hand):
        play(herz_hand, (FOREHAND, "kontra"), 3)

        assert kontra_view(herz_hand, herz_hand.at[FOREHAND])["factor"] == 2
        assert herz_hand.read_as(herz_hand.at[FOREHAND]).json()["hand"]["playing"]["turn_seat"] == SEAT[MIDDLEHAND]


class TestWhoSaysWhichWord:
    def test_the_words_in_the_wrong_hands_are_refused(self, herz_hand):
        refused(herz_hand, MIDDLEHAND, "kontra", "not-your-word")
        refused(herz_hand, FOREHAND, "re", "not-your-word")
        said(herz_hand, FOREHAND, "kontra")
        refused(herz_hand, FOREHAND, "re", "not-your-word")
        refused(herz_hand, REARHAND, "re", "not-your-word")
        refused(herz_hand, REARHAND, "kontra", "not-your-word")

    def test_a_word_beyond_the_reach_of_the_table_is_refused(self, herz_hand):
        play(herz_hand, (FOREHAND, "kontra"), 1, (MIDDLEHAND, "re"))

        refused(herz_hand, FOREHAND, "supra", "beyond-reach")

    def test_where_the_table_asks_it_an_opponent_who_never_bid_says_no_kontra(self, open_table):
        table = open_table(sayer=BIDDERS)
        contested_auction(table)

        refused(table, REARHAND, "kontra", "did-not-bid")
        assert kontra_view(table, table.at[REARHAND])["my_word"] is None
        assert kontra_view(table, table.at[FOREHAND])["my_word"] == "kontra"
        said(table, FOREHAND, "kontra")

    def test_at_a_table_for_any_opponent_rearhand_says_kontra_however_the_auction_went(self, herz_hand):
        said(herz_hand, REARHAND, "kontra")

    def test_a_watcher_is_not_seated(self, herz_hand):
        refused(herz_hand, None, "kontra", "not-seated", headers=herz_hand.watcher)

        assert kontra_view(herz_hand, herz_hand.watcher)["my_word"] is None


class TestAnsweringNoWord:
    def test_an_opponent_answers_and_only_its_own_view_says_so_while_the_word_stays_open(self, herz_hand):
        before = herz_hand.record.version

        answer = answered_no_word(herz_hand, FOREHAND)

        assert herz_hand.record.version == before + 1
        assert [(each.position, each.word.value) for each in herz_hand.record.progress.no_words] == [
            (FOREHAND, "kontra")
        ]
        own = answer.json()["hand"]["playing"]["kontra"]
        assert (own["my_word"], own["my_word_answered"]) == ("kontra", True)
        others = {
            name: kontra_view(herz_hand, headers)
            for name, headers in (("rearhand", herz_hand.at[REARHAND]), ("watcher", herz_hand.watcher))
        }
        assert {name: view["my_word_answered"] for name, view in others.items()} == {
            "rearhand": False,
            "watcher": False,
        }
        assert others["rearhand"]["my_word"] == "kontra"

    def test_a_watcher_cannot_answer_no_word(self, herz_hand):
        herz_hand.refused_act(TABLE_NO_WORD_SUFFIX, herz_hand.watcher, "not-seated")


def contested_auction(table):
    """Middlehand bids 18, forehand holds, middlehand bids 20, both opponents pass; middlehand declares Herz Hand."""

    def step(position, suffix, **body):
        answer = table.act(suffix, table.at[position], body=body)
        assert answer.status_code == 200, answer.text

    step(MIDDLEHAND, TABLE_AUCTION_BID_SUFFIX, value=18)
    step(FOREHAND, TABLE_AUCTION_HOLD_SUFFIX)
    step(MIDDLEHAND, TABLE_AUCTION_BID_SUFFIX, value=20)
    step(FOREHAND, TABLE_AUCTION_PASS_SUFFIX)
    step(REARHAND, TABLE_AUCTION_PASS_SUFFIX)
    step(
        MIDDLEHAND,
        TABLE_DECLARING_DECLARE_SUFFIX,
        game="herz",
        hand=True,
        ouvert=False,
        announcement="none",
    )


class TestTheOtherRefusals:
    def test_a_word_before_the_game_is_declared_is_in_the_wrong_phase(self, open_table):
        table = open_table()

        refused(table, FOREHAND, "kontra", "wrong-phase")
        table.middlehand_wins()
        refused(table, FOREHAND, "kontra", "wrong-phase")

    def test_a_word_where_no_hand_runs_has_no_hand(self, open_table):
        table = open_table()
        table.declared_hand_game()
        table.act(TABLE_GIVE_UP_SUFFIX)

        refused(table, FOREHAND, "kontra", "no-hand")

    def test_a_word_before_the_first_deal_has_no_hand(self, server):
        opener, _ = server.member()
        table_id = server.create(opener, options=kontra_options()).json()["id"]

        answer = server.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_KONTRA_SUFFIX}",
            json={"command_id": "word-0001", "version": 1, "word": "kontra"},
            headers={"origin": TEST_PUBLIC_ORIGIN, **opener},
        )

        assert (answer.status_code, answer.json()["reason"]) == (409, "no-hand")

    def test_a_table_without_kontra_refuses_every_word_and_shows_none(self, server):
        table = Table(server)
        table.declared_hand_game()

        refused(table, FOREHAND, "kontra", "rule-off")
        views = [table.read_as(headers).json() for headers in (*table.at.values(), table.watcher)]
        assert [view["hand"]["playing"]["kontra"] for view in views] == [None] * 4
        assert views[0]["options"]["kontra"] is None

    def test_a_stale_version_is_refused(self, herz_hand):
        answer = say(herz_hand, FOREHAND, "kontra", version=herz_hand.record.version - 1)

        assert (answer.status_code, answer.json()["reason"]) == (409, "stale-version")

    def test_a_word_outside_the_four_is_refused_before_the_table_hears_it(self, herz_hand):
        answer = say(herz_hand, FOREHAND, "bock")

        assert answer.status_code == 422


class TestRetries:
    def test_the_same_id_word_and_version_changes_nothing_twice(self, herz_hand):
        version = herz_hand.record.version
        first = say(herz_hand, FOREHAND, "kontra", command_id="word-0001", version=version)

        again = say(herz_hand, FOREHAND, "kontra", command_id="word-0001", version=version)

        assert (again.status_code, again.json()) == (first.status_code, first.json())
        assert len(herz_hand.record.progress.words) == 1
        assert herz_hand.record.version == version + 1

    def test_a_refused_word_retried_gets_the_same_refusal_and_spends_the_id(self, herz_hand):
        version = herz_hand.record.version
        first = say(herz_hand, MIDDLEHAND, "kontra", command_id="word-0001", version=version)

        again = say(herz_hand, MIDDLEHAND, "kontra", command_id="word-0001", version=version)

        assert (first.status_code, again.status_code) == (409, 409)
        assert again.json() == first.json() == {"reason": "not-your-word", "holder_name": None}

    def test_the_same_id_with_another_word_is_a_reused_id(self, herz_hand):
        version = herz_hand.record.version
        say(herz_hand, FOREHAND, "kontra", command_id="word-0001", version=version)

        again = say(herz_hand, FOREHAND, "re", command_id="word-0001", version=version)

        assert (again.status_code, "reason" in again.json()) == (409, False)


class TestWhatEveryViewerSees:
    def test_every_viewer_and_stream_gets_the_words_and_only_the_own_chair_its_word(self, server, open_table):
        table = open_table()
        table.declared_hand_game()
        people = [(headers, None) for headers in (*table.at.values(), table.watcher)]
        with streams_of(server, table.table_id, people) as streams:
            said(table, FOREHAND, "kontra")
            version = table.record.version

            streamed = [view_of_version(messages, version)["hand"]["playing"]["kontra"] for messages in streams]

        read = [kontra_view(table, headers) for headers, _ in people]
        assert streamed == read
        assert {str([each["said"], each["factor"]]) for each in read} == {
            str([[{"seat": SEAT[FOREHAND], "word": "kontra"}], 2])
        }
        assert [each["my_word"] for each in read] == [None, "re", None, None]

    def test_the_next_hand_starts_without_a_word_and_both_opponents_may_say_kontra(self, server, open_table):
        table = open_table()
        table.declared_hand_game()
        play(table, (FOREHAND, "kontra"), 1, (MIDDLEHAND, "re"))
        table.act(TABLE_GIVE_UP_SUFFIX)
        people = [(headers, None) for headers in table.at.values()]
        with streams_of(server, table.table_id, people):
            for headers, _ in people:
                answer = tap_weiter(server, headers, table.table_id, table.fresh_id())
                assert answer.status_code == 200, answer.text
                server.client.cookies.clear()
        with_known_deal(server, table.table_id)
        table.declared_hand_game()

        assert table.record.progress.words == ()
        assert [(kontra_view(table, table.at[position])) for position in (FOREHAND, REARHAND)] == [
            {"said": [], "factor": 1, "my_word": "kontra", "my_word_answered": False, "first_card_waits": False}
        ] * 2


class TestOpeningATable:
    @pytest.mark.parametrize(
        "options",
        [
            pytest.param(kontra_options(), id="kontra"),
            pytest.param(kontra_options(BIDDERS, UP_TO_HIRSCH), id="bidders-up-to-hirsch"),
            pytest.param(kontra_options(ANY, WITH_STANDINGS), id="standings"),
            pytest.param(kontra_options(deadline="first-card"), id="first-card"),
        ],
    )
    def test_the_answer_carries_the_options_as_sent(self, server, options):
        opener, _ = server.member()

        answer = server.create(opener, options=options)

        assert answer.status_code == 200, answer.text
        assert answer.json()["options"] == {"show_running_points": False, "bock": None, "ramsch": None, **options}

    @pytest.mark.parametrize(
        "options", [pytest.param({}, id="no-kontra"), pytest.param({"kontra": None}, id="kontra-null")]
    )
    def test_a_table_without_kontra_plays_the_isko(self, server, options):
        opener, _ = server.member()

        answer = server.create(opener, options=options)

        assert answer.json()["options"]["kontra"] is None

    def test_a_retry_with_the_same_options_is_the_first_table_and_with_other_options_a_reused_id(self, server):
        opener, _ = server.member()
        first = server.create(opener, options=kontra_options())

        same = server.create(opener, options=kontra_options())
        other = server.create(opener, options=kontra_options(BIDDERS))

        assert same.json()["id"] == first.json()["id"]
        assert other.status_code == 409

    def test_a_table_opened_without_kontra_keeps_the_receipt_text_older_receipts_have(self, server):
        opener, account = server.member()
        first = server.create(opener, series_length=36)

        again = server.create(opener, series_length=36)

        assert again.json()["id"] == first.json()["id"]
        receipt = server.store.receipts[(account.id, "command-0001")]
        assert receipt.payload == '{"series_length":36}'

    @pytest.mark.parametrize(
        "options",
        [
            pytest.param(kontra_options(deadline="at-the-end"), id="unknown-deadline"),
            pytest.param(kontra_options(sayer="everyone"), id="unknown-sayer"),
            pytest.param(kontra_options(reach="all-words"), id="unknown-reach"),
            pytest.param({"kontra": {"sayer": ANY, "reach": KONTRA_RE}}, id="missing-deadline"),
            pytest.param({"kontra": {"reach": KONTRA_RE, "deadline": "own-card"}}, id="missing-sayer"),
            pytest.param({"kontra": {**kontra_options()["kontra"], "extra": 1}}, id="extra-key"),
            pytest.param({"kontra": {}}, id="empty"),
        ],
    )
    def test_a_request_that_does_not_name_all_three_choices_validly_opens_no_table(self, server, options):
        opener, _ = server.member()

        answer = server.create(opener, options=options)

        assert answer.status_code == 422
        assert server.store.tables == {}
