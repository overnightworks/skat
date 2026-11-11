from functools import partial

import pytest

from skat.engine.deal import Deal, Position, next_dealer
from skat.engine.tricks import PlayRefusal
from skat.table.records import Refusal
from skat.web.declaring import GameToken
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from skat.web.playing import (
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_THROW_DOWN_SUFFIX,
)
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import TABLES_PATH, AnnouncementToken
from tests.support.payload_cards import DEALER_SEAT, KNOWN_DEAL, cards_in_text
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import DECLARER_SEAT, Table, card, cards, ending_of, game_of, reason_of
from tests.web.support.presence import OvertakenStore, occupied_seats
from tests.web.support.skat import Skat, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
OPPONENTS = [pytest.param(FOREHAND, id="forehand"), pytest.param(REARHAND, id="rearhand")]
# Seats: the declarer (middlehand) sits in seat 1, rearhand in seat 2, forehand in seat 3.
ASKED_BY_THE_DECLARER = {"asking_seat": 1, "declined_seat": None}
HERZ_GAME = game_of(
    "S7 S9 D7 / H7 DJ CJ / S8 ST D8 / SQ D9 C7 / SK DT C8",
    "SA DQ C9 / SJ HJ CT / H8 HQ CQ / HK CK H9 / HA CA HT",
)
# The declarer holds eight cards once he has played to the second trick.
EIGHT_CARDS = HERZ_GAME[:4]
# After seven tricks the declarer has taken 0 + 10 + 3 + 14 + 14 + 14 = 55 card points, and the skat (D K, D A) adds
# 4 + 11: 70 points win the game without Schneider.
SEVEN_TRICKS = HERZ_GAME[:21]
# Forehand leads the third trick with S8; the declarer answers it with ST.
THIRD_TRICK_LED = HERZ_GAME[:7]
HERZ_HAND_LOST_AT_30 = {
    "won": False,
    "game_value": 30,
    "settled_value": 30,
    "score": -60,
    "multiplier": 3,
    "list_bonus": -50,
    "announcement_missed": False,
    "declarer_points": 0,
    "opponents_points": 120,
}
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


@pytest.fixture
def eight_cards(herz_hand):
    herz_hand.played_out(EIGHT_CARDS)
    return herz_hand


@pytest.fixture
def asked(eight_cards):
    ask(eight_cards)
    return eight_cards


def ask(table, headers=None, *, body=None):
    answer = table.act(TABLE_GIVE_UP_SUFFIX, headers, body=body)
    assert answer.status_code == 200, answer.text
    return answer


def agree(table, position, *, body=None):
    return table.act(TABLE_GIVE_UP_AGREE_SUFFIX, table.at[position], body=body)


def decline(table, position, *, body=None):
    return table.act(TABLE_GIVE_UP_DECLINE_SUFFIX, table.at[position], body=body)


def request_of(table, headers):
    answer = table.read_as(headers)
    assert answer.status_code == 200, answer.text
    return answer.json()["hand"]["playing"]["give_up"]


def everyone_reads(table):
    return [request_of(table, headers) for headers in (table.watcher, *table.at.values())]


def lost_at_30(answer):
    result = answer.json()["result"]
    assert {key: result[key] for key in HERZ_HAND_LOST_AT_30} == HERZ_HAND_LOST_AT_30


def say(table, position, word):
    answer = table.act(TABLE_KONTRA_SUFFIX, table.at[position], body={"word": word})
    assert answer.status_code == 200, answer.text


def kontra_of(table):
    return table.read_as(table.watcher).json()["hand"]["playing"]["kontra"]


@pytest.fixture
def kontra_table(skat):
    options = {"kontra": {"sayer": "any-opponent", "reach": "up-to-hirsch", "deadline": "own-card"}}
    table = Table(skat, options=options)
    table.declared_hand_game()
    return table


class TestKontraAndTheRequestAreIndependent:
    def test_a_request_asked_after_kontra_keeps_the_word_and_the_yes_doubles_the_score(self, kontra_table):
        say(kontra_table, FOREHAND, "kontra")
        kontra_table.played_out(EIGHT_CARDS)

        ask(kontra_table)

        assert kontra_of(kontra_table)["factor"] == 2
        assert request_of(kontra_table, kontra_table.watcher) == ASKED_BY_THE_DECLARER
        result = agree(kontra_table, REARHAND).json()["result"]
        assert (result["kontra"]["word"], result["score"], result["list_bonus"]) == ("kontra", -120, -50)
        assert [entry.kontra_word for entry in kontra_table.record.game_list] == ["kontra"]

    def test_a_word_said_while_the_request_stands_keeps_it_and_the_yes_doubles_by_every_word(self, kontra_table):
        say(kontra_table, FOREHAND, "kontra")
        kontra_table.played_out(HERZ_GAME[:1])
        say(kontra_table, MIDDLEHAND, "re")
        kontra_table.played_out(HERZ_GAME[1:4])
        ask(kontra_table)

        say(kontra_table, FOREHAND, "supra")

        assert kontra_of(kontra_table)["factor"] == 8
        assert request_of(kontra_table, kontra_table.watcher) == ASKED_BY_THE_DECLARER
        result = agree(kontra_table, REARHAND).json()["result"]
        assert (result["kontra"]["word"], result["score"]) == ("supra", -480)


class TestTheDeclarerAsks:
    def test_with_eight_cards_the_request_is_stored_and_every_viewer_reads_it(self, eight_cards):
        before = eight_cards.record

        answer = ask(eight_cards)

        assert eight_cards.record.hand is not None
        assert eight_cards.record.version == before.version + 1
        assert eight_cards.record.game_list == ()
        assert answer.json()["hand"]["playing"]["give_up"] == ASKED_BY_THE_DECLARER
        assert everyone_reads(eight_cards) == [ASKED_BY_THE_DECLARER] * 4

    def test_with_nine_cards_the_game_is_lost_at_once_and_nothing_is_asked(self, herz_hand):
        herz_hand.played_out(EIGHT_CARDS[:3])

        lost_at_30(ask(herz_hand))

        assert herz_hand.record.hand is None

    def test_asking_again_while_the_request_stands_changes_nothing(self, asked):
        before = asked.record

        answer = ask(asked)

        assert asked.record == before
        assert answer.json()["version"] == before.version

    def test_asking_again_after_both_said_no_asks_without_a_no(self, asked):
        decline(asked, FOREHAND)
        decline(asked, REARHAND)
        assert everyone_reads(asked) == [None] * 4

        ask(asked)

        assert everyone_reads(asked) == [ASKED_BY_THE_DECLARER] * 4

    def test_asking_again_after_a_card_asks_without_a_no(self, asked):
        decline(asked, FOREHAND)
        asked.accepted(card("DJ"))

        ask(asked)

        assert everyone_reads(asked) == [ASKED_BY_THE_DECLARER] * 4

    def test_the_skat_cards_that_change_no_matador_change_nothing_the_viewers_read(self, skat):
        swapped = Deal(
            forehand=KNOWN_DEAL.forehand,
            middlehand=KNOWN_DEAL.middlehand,
            rearhand=tuple(card("DA") if each == card("D9") else each for each in KNOWN_DEAL.rearhand),
            skat=(card("DK"), card("D9")),
        )
        reads = []
        for deal in (KNOWN_DEAL, swapped):
            table = Table(skat)
            table.with_deal(deal)
            table.declared_hand_game()
            table.played_out(EIGHT_CARDS)
            ask(table)
            decline(table, FOREHAND)
            reads.append(everyone_reads(table))

        assert reads[0] == reads[1] == [{"asking_seat": 1, "declined_seat": 3}] * 4


class TestAnOpponentSaysYes:
    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_game_is_lost_as_declared_and_the_declarers_completed_tricks_alone_count(self, asked, position):
        answer = agree(asked, position)

        assert answer.status_code == 200, answer.text
        lost_at_30(answer)
        assert asked.record.hand is None
        assert len(asked.record.game_list) == 1
        assert asked.result() == answer.json()["result"]

    @pytest.mark.parametrize("position", OPPONENTS)
    def test_the_game_is_given_up_by_the_asking_declarer_and_not_the_opponent_who_said_yes(self, asked, position):
        assert asked.result() is None

        answer = agree(asked, position)

        assert ending_of(answer.json()["result"]) == ("given-up", DECLARER_SEAT)
        assert asked.endings_in_every_view() == {("given-up", DECLARER_SEAT)}

    def test_a_yes_after_the_other_opponents_no_ends_the_game_the_same_way(self, asked):
        decline(asked, REARHAND)

        agree(asked, FOREHAND)

        assert asked.endings_in_every_view() == {("given-up", DECLARER_SEAT)}

    def test_a_game_his_tricks_and_the_skat_already_win_is_still_given_up(self, herz_hand):
        herz_hand.played_out(SEVEN_TRICKS)
        ask(herz_hand)

        answer = agree(herz_hand, FOREHAND)

        assert answer.json()["result"]["won"] is True
        assert ending_of(answer.json()["result"]) == ("given-up", DECLARER_SEAT)

    def test_a_game_his_tricks_and_the_skat_already_win_ends_as_won_with_the_skat_counted(self, herz_hand):
        herz_hand.played_out(SEVEN_TRICKS)
        ask(herz_hand)

        result = agree(herz_hand, FOREHAND).json()["result"]

        assert (result["won"], result["game_value"], result["score"], result["list_bonus"]) == (True, 30, 30, 50)
        assert (result["declarer_points"], result["opponents_points"]) == (70, 50)

    def test_a_game_announced_schneider_is_not_yet_won_at_70_points(self, table):
        table.declared_hand_game(announcement=AnnouncementToken.SCHNEIDER)
        table.played_out(SEVEN_TRICKS)
        ask(table)

        result = agree(table, REARHAND).json()["result"]

        assert (result["won"], result["multiplier"], result["game_value"], result["score"]) == (False, 5, 50, -100)
        assert (result["list_bonus"], result["announcement_missed"]) == (-50, True)

    def test_a_bid_over_the_value_is_lost_at_the_next_multiple_of_the_base_value(self, table):
        table.declared_hand_game(bid=33)
        table.played_out(EIGHT_CARDS)
        ask(table)

        result = agree(table, FOREHAND).json()["result"]

        assert {key: result[key] for key in ("overbid", "game_value", "settled_value", "score")} == {
            "overbid": True,
            "game_value": 30,
            "settled_value": 40,
            "score": -80,
        }
        assert result["announcement_missed"] is False

    @pytest.mark.parametrize(
        ("put_back", "value", "score"),
        [pytest.param(None, 35, -70, id="null-hand"), pytest.param("DA DK", 23, -46, id="null")],
    )
    def test_a_null_is_lost_at_its_fixed_value_without_matadors(self, table, put_back, value, score):
        table.with_deal(NULL_DEAL)
        if put_back is None:
            table.declared_hand_game(GameToken.NULL)
        else:
            table.declared_after_putting_back(cards(put_back), GameToken.NULL, ouvert=False)
        table.played_out(NULL_TWO_TRICKS)
        ask(table)

        result = agree(table, FOREHAND).json()["result"]

        assert (result["won"], result["matadors"], result["game_value"], result["score"]) == (
            False,
            None,
            value,
            score,
        )

    def test_the_opponent_who_said_no_may_still_say_yes(self, asked):
        decline(asked, FOREHAND)

        lost_at_30(agree(asked, FOREHAND))

    def test_a_yes_after_the_other_opponents_no_ends_the_game(self, asked):
        decline(asked, FOREHAND)

        lost_at_30(agree(asked, REARHAND))

    def test_a_throw_down_while_the_request_stands_ends_the_game_and_the_request_goes_with_the_hand(self, asked):
        answer = asked.act(TABLE_THROW_DOWN_SUFFIX)

        assert answer.status_code == 200, answer.text
        assert asked.record.hand is None
        assert asked.record.progress.give_up is None
        assert len(asked.record.game_list) == 1


class TestAnOpponentSaysNo:
    def test_one_no_keeps_the_request_and_names_his_seat(self, asked):
        before = asked.record.version

        answer = decline(asked, FOREHAND)

        assert answer.status_code == 200, answer.text
        assert asked.record.version == before + 1
        assert everyone_reads(asked) == [{"asking_seat": 1, "declined_seat": 3}] * 4

    def test_both_noes_end_the_request_and_the_game_goes_on(self, asked):
        before = asked.record.version
        decline(asked, FOREHAND)

        decline(asked, REARHAND)

        assert asked.record.version == before + 2
        assert asked.record.hand is not None
        assert everyone_reads(asked) == [None] * 4

    def test_the_same_opponent_saying_no_twice_changes_nothing(self, asked):
        decline(asked, FOREHAND)
        before = asked.record

        again = decline(asked, FOREHAND)

        assert again.status_code == 200
        assert asked.record == before


class TestACardEndsTheRequest:
    @pytest.mark.parametrize(
        ("played_before", "next_card"),
        [
            pytest.param(EIGHT_CARDS, "DJ", id="the-opponent-on-turn"),
            pytest.param(THIRD_TRICK_LED, "ST", id="the-declarer"),
        ],
    )
    def test_the_card_is_taken_and_a_yes_after_it_has_nothing_to_answer(self, herz_hand, played_before, next_card):
        herz_hand.played_out(played_before)
        ask(herz_hand)

        herz_hand.accepted(card(next_card))

        assert everyone_reads(herz_hand) == [None] * 4
        herz_hand.refused_act(TABLE_GIVE_UP_AGREE_SUFFIX, herz_hand.at[FOREHAND], Refusal.NO_REQUEST)


class TestRefusals:
    @pytest.mark.parametrize("route", [TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX])
    @pytest.mark.parametrize("position", OPPONENTS)
    def test_an_answer_with_nothing_asked_has_no_request(self, eight_cards, route, position):
        eight_cards.refused_act(route, eight_cards.at[position], Refusal.NO_REQUEST)

    @pytest.mark.parametrize("route", [TABLE_GIVE_UP_AGREE_SUFFIX, TABLE_GIVE_UP_DECLINE_SUFFIX])
    def test_the_declarer_is_not_an_opponent_of_his_own_request(self, asked, route):
        asked.refused_act(route, asked.at[MIDDLEHAND], PlayRefusal.NOT_AN_OPPONENT)

    def test_a_yes_on_the_version_before_the_partners_no_is_stale(self, asked):
        before = asked.record.version
        decline(asked, REARHAND)

        asked.refused_act(
            TABLE_GIVE_UP_AGREE_SUFFIX, asked.at[FOREHAND], Refusal.STALE_VERSION, body={"version": before}
        )


@pytest.fixture(
    params=[
        pytest.param((TABLE_GIVE_UP_SUFFIX, False), id="give-up"),
        pytest.param((TABLE_GIVE_UP_AGREE_SUFFIX, True), id="agree"),
        pytest.param((TABLE_GIVE_UP_DECLINE_SUFFIX, True), id="decline"),
    ]
)
def answered_route(request, eight_cards):
    """A route of the request and a table where it can be taken: the answers need the request asked first."""
    suffix, needs_request = request.param
    if needs_request:
        ask(eight_cards)
    return suffix


def caller_of(table, route):
    """The declarer asks; an opponent answers."""
    return table.at[MIDDLEHAND if route == TABLE_GIVE_UP_SUFFIX else FOREHAND]


class TestRetries:
    def test_the_same_id_and_version_answer_the_same_and_change_the_table_once(self, eight_cards, answered_route):
        body = {"command_id": "command-consent", "version": eight_cards.record.version}
        first = eight_cards.act(answered_route, caller_of(eight_cards, answered_route), body=body)
        stored = eight_cards.record

        again = eight_cards.act(answered_route, caller_of(eight_cards, answered_route), body=body)

        assert again.status_code == 200
        assert again.json() == first.json()
        assert eight_cards.record == stored

    def test_a_refused_retry_returns_the_same_refusal(self, eight_cards, answered_route):
        body = {"command_id": "command-consent"}
        first = eight_cards.act(answered_route, eight_cards.watcher, body=body)

        again = eight_cards.act(answered_route, eight_cards.watcher, body=body)

        assert (first.status_code, reason_of(first)) == (409, Refusal.NOT_SEATED)
        assert (again.status_code, again.json()) == (first.status_code, first.json())

    def test_the_same_id_with_another_version_is_reused(self, eight_cards, answered_route):
        version = eight_cards.record.version
        headers = caller_of(eight_cards, answered_route)
        eight_cards.act(answered_route, headers, body={"command_id": "command-consent", "version": version})

        again = eight_cards.act(answered_route, headers, body={"command_id": "command-consent", "version": version - 1})

        assert again.status_code == 409
        assert "reused" in again.json()["detail"]

    def test_the_same_id_on_another_route_is_reused(self, eight_cards, answered_route):
        body = {"command_id": "command-consent", "version": eight_cards.record.version}
        headers = caller_of(eight_cards, answered_route)
        eight_cards.act(answered_route, headers, body=body)

        again = eight_cards.act(TABLE_THROW_DOWN_SUFFIX, headers, body=body)

        assert again.status_code == 409
        assert "reused" in again.json()["detail"]


def everybody_taps_weiter(table):
    with streams_of(table.skat, table.table_id, [(headers, None) for headers in table.at.values()]):
        for headers in table.at.values():
            table.skat.client.cookies.clear()
            answer = table.skat.client.post(
                f"{TABLES_PATH}/{table.table_id}{TABLE_READY_SUFFIX}",
                json={"command_id": table.fresh_id(), "ordinal": 1},
                headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
            )
            assert answer.status_code == 200, answer.text


class TestAfterTheYes:
    def test_all_three_readies_deal_the_next_hand_and_a_yes_retried_then_is_replayed(self, server):
        table = Table(server)
        table.declared_hand_game()
        table.played_out(EIGHT_CARDS)
        ask(table)
        body = {"command_id": "command-consent", "version": table.record.version}
        first = agree(table, FOREHAND, body=body)

        everybody_taps_weiter(table)
        dealt = table.record
        again = agree(table, FOREHAND, body=body)

        assert dealt.hand is not None
        assert dealt.dealer == next_dealer(DEALER_SEAT)
        assert (again.status_code, again.json()["version"]) == (200, dealt.version)
        assert first.json()["result"] is not None
        assert again.json()["result"] is None
        assert table.record == dealt
        assert len(table.record.game_list) == 1

    def test_an_old_expiry_reaching_the_table_right_after_the_yes_committed_leaves_the_fresh_hold_alone(
        self, hold, time
    ):
        store = OvertakenStore()
        server = Skat(lambda: hold, store=store, chair_clock=time.clock, chair_scheduler=time)
        with server.client:
            table = Table(server)
            with streams_of(server, table.table_id, [(table.at[FOREHAND], None)]):
                pass
            table.declared_hand_game()
            table.played_out(EIGHT_CARDS)
            ask(table)
            server.client.portal.call(time.advance, hold.settings.chair_hold_seconds - 1)
            store.after_commit = partial(server.client.portal.call, time.advance, 1)

            agree(table, FOREHAND)

            assert occupied_seats(server, table.table_id) == {1, 2, 3}
            server.client.portal.call(time.advance, hold.settings.chair_hold_seconds - 1)
            assert occupied_seats(server, table.table_id) == {1, 2, 3}
            server.client.portal.call(time.advance, 2)
            assert occupied_seats(server, table.table_id) == set()


class TestWhatViewersSee:
    def test_the_stream_of_a_watcher_carries_the_request_and_the_no(self, herz_hand):
        herz_hand.played_out(EIGHT_CARDS)
        with streams_of(herz_hand.skat, herz_hand.table_id, [(herz_hand.watcher, None)]) as (watcher,):
            ask(herz_hand)
            assert next(watcher)["hand"]["playing"]["give_up"] == ASKED_BY_THE_DECLARER

            decline(herz_hand, REARHAND)
            assert next(watcher)["hand"]["playing"]["give_up"] == {"asking_seat": 1, "declined_seat": 2}

    def test_after_the_yes_every_viewer_reads_one_result_and_no_card_of_an_ouvert_hand(self, table):
        table.declared_grand_ouvert()
        table.played_out(cards("S7 S9 D7 H7"))
        ask(table)
        assert everyone_reads(table) == [ASKED_BY_THE_DECLARER] * 4

        agree(table, FOREHAND)

        reads = [table.read_as(headers) for headers in (table.watcher, *table.at.values())]
        assert {tuple(sorted(cards_in_text(read.text))) for read in reads} == {()}
        assert len({str(read.json()["result"]) for read in reads}) == 1
