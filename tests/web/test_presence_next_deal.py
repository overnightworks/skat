from dataclasses import replace
from functools import partial

import pytest
from structlog.testing import capture_logs

from skat.engine.bidding import Bid, Pass
from skat.engine.cards import DECK
from skat.engine.deal import Position, next_dealer, positions_from
from skat.engine.declaration import Announcement, Declare
from skat.engine.games import GameKind
from skat.engine.tricks import CardPlayed, play_card
from skat.table.hand_state import playing_of
from skat.table.records import Actor, CreateTable, HandProgress, SitDown, TableId
from skat.table.service import TableService
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.presence import NEXT_DEAL_PAUSE_SECONDS
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS, TABLES_PATH
from tests.support.fake_tables import FakeTableStore
from tests.support.payload_cards import DEALER_SEAT, cards_in, seated_three, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.presence import (
    FAILURE_NAMING_AN_ACCOUNT,
    NAMED_FAILURE,
    OTHER_TABLE,
    TABLE,
    THIRD_PASS_COMMAND,
    OvertakenStore,
    connect,
    end_the_first_game,
    occupied_seats,
    pass_hand_in,
    post_pass,
    run,
)
from tests.web.support.skat import Skat, streams_of
from tests.web.support.streams import OPENER, VISITOR, next_view, run_on_a_loop_of_its_own, stream_of

CLEO = Actor(account_id="cleo", display_name="Cleo")


def view_of_version(messages, version):
    return next(view for view in messages if view["version"] >= version)


def advance(server, time, seconds):
    server.client.portal.call(time.advance, seconds)


class TestNextDealPause:
    def test_a_second_request_during_the_pause_starts_no_second_timer(self, holding, time, deals):
        holding.deal_soon(TABLE)
        holding.deal_soon(TABLE)

        assert time.pending == 1
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))
        assert len(deals.calls) == 1

    def test_a_restart_replaces_the_pending_pause_and_a_later_request_leaves_the_new_one_alone(
        self, holding, time, deals
    ):
        holding.deal_soon(TABLE)
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS - 1))

        holding.restart_deal_pause(TABLE)
        holding.deal_soon(TABLE)
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS - 0.001))
        assert deals.calls == []

        run(time.advance(0.001))
        assert len(deals.calls) == 1

    def test_each_table_has_its_own_pause(self, holding, time):
        holding.deal_soon(TABLE)
        holding.deal_soon(OTHER_TABLE)

        assert time.pending == 2

    def test_asks_for_the_deal_with_who_is_connected_when_the_pause_ends(self, holding, time, deals):
        holding.deal_soon(TABLE)
        connect(holding, TABLE, "anna", lambda: None)

        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))

        assert deals.calls == [(TABLE, frozenset({"anna"}))]

    def test_who_is_connected_is_read_once_the_deal_holds_the_row(self, holding, time, deals):
        async def anna_returns_while_the_deal_waits():
            await holding.subscribe(TABLE, "anna", lambda: None)

        deals.meanwhile = anna_returns_while_the_deal_waits
        holding.deal_soon(TABLE)

        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))

        assert deals.calls == [(TABLE, frozenset({"anna"}))]

    def test_a_deal_wakes_the_table_and_a_refused_deal_wakes_nobody(self, holding, time, deals, wakes):
        connect(holding, TABLE, "anna", wakes.callback("anna"))
        before = wakes.counts["anna"]

        holding.deal_soon(TABLE)
        deals.dealt = False
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))
        assert wakes.counts["anna"] == before

        holding.deal_soon(TABLE)
        deals.dealt = True
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))
        assert wakes.counts["anna"] == before + 1

    def test_a_request_while_the_deal_runs_starts_a_fresh_pause_after_it(self, holding, time, deals):
        async def another_request():
            deals.meanwhile = None
            holding.deal_soon(TABLE)

        deals.meanwhile = another_request
        holding.deal_soon(TABLE)

        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))

        assert time.pending == 1

    def test_a_failed_deal_is_logged_by_name_wakes_nobody_and_leaves_the_next_request_free(
        self, holding, time, deals, wakes
    ):
        connect(holding, TABLE, "anna", wakes.callback("anna"))
        before = wakes.counts["anna"]
        deals.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]

        holding.deal_soon(TABLE)
        with capture_logs() as logs:
            run(time.advance(NEXT_DEAL_PAUSE_SECONDS))

        assert wakes.counts["anna"] == before
        assert [(log["log_level"], log["error"]) for log in logs] == [NAMED_FAILURE]
        assert "anna" not in str(logs)
        holding.deal_soon(TABLE)
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS))
        assert wakes.counts["anna"] == before + 1

    def test_the_server_stopping_during_the_pause_cancels_the_deal_and_a_later_request_starts_none(
        self, holding, time, deals
    ):
        holding.deal_soon(TABLE)

        holding.stop()
        holding.deal_soon(OTHER_TABLE)
        run(time.advance(NEXT_DEAL_PAUSE_SECONDS * 2))

        assert (time.pending, deals.calls) == (0, [])


class TestDealNow:
    def test_asks_for_the_deal_at_once_with_who_is_connected_and_starts_no_timer(self, holding, time, deals):
        connect(holding, TABLE, "anna", lambda: None)

        run(holding.deal_now(TABLE))

        assert (deals.calls, time.pending) == ([(TABLE, frozenset({"anna"}))], 0)

    def test_a_deal_wakes_the_table_and_a_refused_deal_wakes_nobody(self, holding, deals, wakes):
        connect(holding, TABLE, "anna", wakes.callback("anna"))
        before = wakes.counts["anna"]

        deals.dealt = False
        run(holding.deal_now(TABLE))
        assert wakes.counts["anna"] == before

        deals.dealt = True
        run(holding.deal_now(TABLE))
        assert wakes.counts["anna"] == before + 1

    def test_a_failed_deal_is_logged_by_name_and_wakes_nobody(self, holding, deals, wakes):
        connect(holding, TABLE, "anna", wakes.callback("anna"))
        before = wakes.counts["anna"]
        deals.failures = [ConnectionError(FAILURE_NAMING_AN_ACCOUNT)]

        with capture_logs() as logs:
            run(holding.deal_now(TABLE))

        assert wakes.counts["anna"] == before
        assert [(log["log_level"], log["error"]) for log in logs] == [NAMED_FAILURE]
        assert "anna" not in str(logs)

    def test_once_the_server_stopped_it_asks_with_nobody_connected(self, holding, deals):
        connect(holding, TABLE, "anna", lambda: None)
        holding.stop()

        run(holding.deal_now(TABLE))

        assert deals.calls == [(TABLE, frozenset())]


class TestNextHandComes:
    def test_the_next_dealer_deals_when_the_pause_ends_and_not_a_moment_before(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]) as streams:
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS - 0.001)
            assert server.store.tables[table_id] == passed_in

            advance(server, time, 0.001)
            record = server.store.tables[table_id]
            assert record.dealer == next_dealer(DEALER_SEAT)
            assert [len(cards) for cards in record.hand.hands.values()] == [10, 10, 10]
            assert record.progress == HandProgress()
            assert record.version == passed_in.version + 1
            for messages in streams:
                view = view_of_version(messages, record.version)
                assert view["passed_in"] is None
                position = next(chair["hand"]["position"] for chair in view["chairs"] if chair["is_mine"])
                assert cards_in(view) == wire_cards(getattr(record.hand, position))

    def test_a_stream_opening_during_the_pause_neither_cuts_it_short_nor_stretches_it(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]
            pending = time.pending
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS / 2)

            with streams_of(server, table_id, people[3:]):
                assert time.pending == pending
                advance(server, time, NEXT_DEAL_PAUSE_SECONDS / 2 - 0.001)
                assert server.store.tables[table_id] == passed_in

                advance(server, time, 0.001)
                assert server.store.tables[table_id].version == passed_in.version + 1

                advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)
                assert server.store.tables[table_id].version == passed_in.version + 1

    def test_a_member_away_when_the_pause_ends_keeps_the_table_waiting_and_their_hold_running(self, server, hold, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:2]):
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS)
            assert server.store.tables[table_id] == passed_in

            advance(server, time, hold.settings.chair_hold_seconds - NEXT_DEAL_PAUSE_SECONDS - 1)
            assert occupied_seats(server, table_id) == {1, 2, 3}
            assert server.store.tables[table_id] == passed_in

    def test_a_returning_member_gets_a_fresh_pause_and_then_the_deal_and_keeps_the_chair(self, server, hold, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:2]):
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS + 10)

            with streams_of(server, table_id, people[2:3]):
                advance(server, time, NEXT_DEAL_PAUSE_SECONDS - 0.001)
                assert server.store.tables[table_id] == passed_in

                advance(server, time, 0.001)
                assert server.store.tables[table_id].version == passed_in.version + 1

                advance(server, time, hold.settings.chair_hold_seconds)
                assert occupied_seats(server, table_id) == {1, 2, 3}

    def test_the_hold_of_an_away_member_frees_the_chair_with_no_deal_and_the_filling_sit_deals_at_once(
        self, server, hold, time
    ):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:2]):
            pass_hand_in(server, table_id, people)
            advance(server, time, hold.settings.chair_hold_seconds + 1)
            assert occupied_seats(server, table_id) == {1, 2}
            assert server.store.tables[table_id].hand is None

            server.client.cookies.clear()
            answer = server.sit(people[3][0], table_id, 3, command_id="command-sit-away")

        assert answer.status_code == 200, answer.text
        record = server.store.tables[table_id]
        assert record.hand is not None
        assert record.dealer == next_dealer(DEALER_SEAT)

    def test_standing_up_during_the_pause_is_allowed_and_the_pause_then_deals_nothing(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            pass_hand_in(server, table_id, people)

            standing = server.stand(people[0][0], table_id)
            server.client.cookies.clear()
            assert standing.status_code == 200, standing.text
            after_standing = server.store.tables[table_id]

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS)

            assert server.store.tables[table_id] == after_standing
            assert after_standing.hand is None

    def test_a_later_hands_end_restarts_the_pause_and_the_earlier_hands_timer_does_nothing(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            pass_hand_in(server, table_id, people)
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS / 4)

            server.stand(people[0][0], table_id)
            server.client.cookies.clear()
            server.sit(people[0][0], table_id, 1, command_id="command-sit-again")
            server.client.cookies.clear()
            assert server.store.tables[table_id].hand is not None
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS / 2)

            next_dealers_turn_order = (2, 3, 1)
            pass_hand_in(server, table_id, people, seats_in_turn=next_dealers_turn_order)
            later_hand_passed_in = server.store.tables[table_id]
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS / 4)
            assert server.store.tables[table_id] == later_hand_passed_in

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 3 / 4 - 0.001)
            assert server.store.tables[table_id] == later_hand_passed_in

            advance(server, time, 0.001)
            assert server.store.tables[table_id].version == later_hand_passed_in.version + 1

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)
            assert server.store.tables[table_id].version == later_hand_passed_in.version + 1

    def test_a_retry_of_the_third_pass_during_the_pause_and_after_the_deal_starts_no_timer_and_no_deal(
        self, server, time
    ):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            version = server.store.tables[table_id].version
            post_pass(server, table_id, people[0][0], command_id="pass-seat-1", version=version)
            post_pass(server, table_id, people[1][0], command_id="pass-seat-2", version=version + 1)
            first = post_pass(server, table_id, people[2][0], command_id=THIRD_PASS_COMMAND, version=version + 2)
            pending = time.pending

            during = post_pass(server, table_id, people[2][0], command_id=THIRD_PASS_COMMAND, version=version + 2)
            assert (first.status_code, during.status_code, time.pending) == (200, 200, pending)

            advance(server, time, NEXT_DEAL_PAUSE_SECONDS)
            dealt = server.store.tables[table_id]
            assert dealt.hand is not None

            pending_after_deal = time.pending
            after = post_pass(server, table_id, people[2][0], command_id=THIRD_PASS_COMMAND, version=version + 2)
            assert after.status_code == 200
            assert after.json()["hand"] is not None
            assert after.json()["passed_in"] is None
            assert time.pending == pending_after_deal
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)

            assert during.json() == first.json()
            assert server.store.tables[table_id] == dealt

    @pytest.mark.parametrize("seated", [True, False], ids=["a-hand-runs", "never-dealt"])
    def test_a_stream_opening_when_no_hand_was_passed_in_changes_nothing(self, server, time, seated):
        if seated:
            table_id, people = seated_three(server)
        else:
            people = [server.member()]
            table_id = server.create(people[0][0]).json()["id"]
        server.client.cookies.clear()
        before = server.store.tables[table_id]

        with streams_of(server, table_id, people[:1]):
            assert time.pending == 0
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)

            assert server.store.tables[table_id] == before

    def test_a_store_failure_in_the_deal_is_named_changes_nothing_and_the_next_stream_opening_deals(self, hold, time):
        store = OvertakenStore()
        server = Skat(lambda: hold, store=store, chair_clock=time.clock, chair_scheduler=time)

        def store_goes_down():
            raise ConnectionError(FAILURE_NAMING_AN_ACCOUNT)

        with server.client:
            table_id, people = seated_three(server)
            server.client.cookies.clear()
            with streams_of(server, table_id, people[:3]):
                pass_hand_in(server, table_id, people)
                passed_in = store.tables[table_id]
                store.meanwhile = store_goes_down

                with capture_logs() as logs:
                    advance(server, time, NEXT_DEAL_PAUSE_SECONDS)

                assert store.tables[table_id] == passed_in
                assert [(log["log_level"], log["error"]) for log in logs] == [NAMED_FAILURE]
                assert "anna" not in str(logs)

                with streams_of(server, table_id, people[3:]):
                    advance(server, time, NEXT_DEAL_PAUSE_SECONDS)

                    assert store.tables[table_id].version == passed_in.version + 1

    def test_the_server_stopping_during_the_pause_deals_nothing(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            pass_hand_in(server, table_id, people)
            passed_in = server.store.tables[table_id]

            server.client.portal.call(server.app.state.stop_streams)
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)

            assert (time.pending, server.store.tables[table_id]) == (0, passed_in)

    def test_the_server_stopping_while_the_deal_waits_for_the_row_writes_no_deal(self, hold, time):
        store = OvertakenStore()
        server = Skat(lambda: hold, store=store, chair_clock=time.clock, chair_scheduler=time)

        with server.client:
            table_id, people = seated_three(server)
            server.client.cookies.clear()
            with streams_of(server, table_id, people[:3]):
                pass_hand_in(server, table_id, people)
                passed_in = store.tables[table_id]
                store.meanwhile = lambda: server.client.portal.call(server.app.state.stop_streams)

                advance(server, time, NEXT_DEAL_PAUSE_SECONDS)

                assert store.tables[table_id] == passed_in


def twenty_nine_cards_played(server, table_id, people):
    """Seat 1, the middlehand, plays a Herz Hand game at 18 to its end; each card is the first in deck order the
    engine accepts. The first twenty-nine are stored directly; the returned call plays the thirtieth through the
    card route."""
    record = server.store.tables[table_id]
    declared = HandProgress(
        auction=(Bid(Position.MIDDLEHAND, 18), Pass(Position.FOREHAND), Pass(Position.REARHAND)),
        declaring=(Declare(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE),),
    )
    state = playing_of(replace(record, progress=declared))
    plays = []
    while state.result is None:
        held = state.hands[state.turn]
        card = next(each for each in DECK if each in held and play_card(state, state.turn, each).refusal is None)
        plays.append(CardPlayed(state.turn, card))
        state = play_card(state, state.turn, card).state
    server.store.tables[table_id] = replace(record, progress=replace(declared, plays=tuple(plays[:-1])))
    last = plays[-1]
    seat = {position: seat for seat, position in positions_from(record.dealer).items()}[last.position]

    def play_last():
        answer = server.client.post(
            f"{TABLES_PATH}/{table_id}{TABLE_CARD_SUFFIX}",
            json={
                "command_id": "card-last",
                "version": server.store.tables[table_id].version,
                "suit": SUIT_TOKENS[last.card.suit],
                "rank": RANK_TOKENS[last.card.rank],
            },
            headers={"origin": TEST_PUBLIC_ORIGIN, **people[seat - 1][0]},
        )
        server.client.cookies.clear()
        assert answer.status_code == 200, answer.text
        assert server.store.tables[table_id].hand is None

    return play_last


def last_card_played(server, table_id, people):
    twenty_nine_cards_played(server, table_id, people)()


class TestAfterAPlayedGame:
    def test_with_all_three_connected_no_next_hand_is_dealt_on_a_stream_opening_or_a_reconnect(self, server, time):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        with streams_of(server, table_id, people[:3]):
            last_card_played(server, table_id, people)
            ended = server.store.tables[table_id]
            advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)

            with streams_of(server, table_id, people[:3]):
                advance(server, time, NEXT_DEAL_PAUSE_SECONDS * 2)

        assert server.store.tables[table_id] == ended

    def test_a_member_away_at_the_last_card_gets_a_fresh_hold_and_the_connected_keep_their_chairs(
        self, server, hold, time
    ):
        table_id, people = seated_three(server)
        server.client.cookies.clear()
        hold_seconds = hold.settings.chair_hold_seconds
        with streams_of(server, table_id, people[2:3]):
            pass
        with streams_of(server, table_id, people[:2]):
            advance(server, time, hold_seconds / 2)
            last_card_played(server, table_id, people)

            advance(server, time, hold_seconds - 1)
            assert occupied_seats(server, table_id) == {1, 2, 3}

            advance(server, time, 2)
            assert occupied_seats(server, table_id) == {1, 2}


class TestHoldWhenAPlayedGameEnds:
    def test_an_old_expiry_reaching_the_table_right_after_the_thirtieth_card_committed_leaves_the_fresh_hold_alone(
        self, hold, time
    ):
        store = OvertakenStore()
        server = Skat(lambda: hold, store=store, chair_clock=time.clock, chair_scheduler=time)
        with server.client:
            table_id, people = seated_three(server)
            with streams_of(server, table_id, people[:1]):
                pass
            server.client.cookies.clear()
            play_last = twenty_nine_cards_played(server, table_id, people)
            advance(server, time, hold.settings.chair_hold_seconds - 1)
            store.after_commit = partial(advance, server, time, 1)

            play_last()

            assert occupied_seats(server, table_id) == {1, 2, 3}
            advance(server, time, hold.settings.chair_hold_seconds - 1)
            assert occupied_seats(server, table_id) == {1, 2, 3}
            advance(server, time, 2)
            assert occupied_seats(server, table_id) == set()


class TestNextDealTrigger:
    """The stream's half of the next deal: its first view of a passed-in table asks for the deal."""

    @pytest.fixture
    def store(self):
        return FakeTableStore()

    @pytest.fixture
    def table(self, store):
        service = TableService(store, new_table_id=lambda: TableId("1" * 32))
        table_id = service.create(OPENER, CreateTable(command_id="command-1")).id
        service.sit(VISITOR, SitDown("command-2", table_id, 2), frozenset())
        return service, table_id

    def passed_in(self, store, table_id):
        steps = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
        store.tables[table_id] = replace(store.tables[table_id], dealer=1, hand=None, progress=HandProgress(steps))

    def test_the_first_view_of_a_passed_in_table_starts_one_pause_and_a_later_view_starts_none(
        self, store, table, holding, time, deals
    ):
        service, table_id = table
        self.passed_in(store, table_id)
        deals.dealt = False

        async def scenario():
            stream = stream_of(holding, service, OPENER, table_id)
            await next_view(stream)
            assert time.pending == 1
            await time.advance(NEXT_DEAL_PAUSE_SECONDS)
            assert time.pending == 0
            holding.wake_table(table_id)
            await next_view(stream)
            assert time.pending == 0
            await stream.aclose()

        run_on_a_loop_of_its_own(scenario())

        assert [call[0] for call in deals.calls] == [table_id]

    def test_the_first_view_of_a_pending_result_asks_for_the_deal_at_once_and_a_later_view_does_not(
        self, store, table, holding, time, deals
    ):
        service, table_id = table
        service.sit(CLEO, SitDown("command-3", table_id, 3), frozenset())
        end_the_first_game(store, table_id)
        deals.dealt = False

        async def scenario():
            stream = stream_of(holding, service, OPENER, table_id)
            await next_view(stream)
            assert (len(deals.calls), time.pending) == (1, 0)
            holding.wake_table(table_id)
            await next_view(stream)
            await stream.aclose()

        run_on_a_loop_of_its_own(scenario())

        assert deals.calls == [(table_id, frozenset({OPENER.account_id}))]
