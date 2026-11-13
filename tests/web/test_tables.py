import asyncio

import pytest

from skat.engine.bidding import Awaiting
from skat.engine.cards import Rank, Suit
from skat.engine.deal import Position, positions_from
from skat.table.service import TableService
from skat.web.auction import TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import TABLE_DECLARING_TAKE_SUFFIX
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from skat.web.playing import (
    TABLE_CARD_SUFFIX,
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_THROW_DOWN_SUFFIX,
)
from skat.web.presence import Presence
from skat.web.ready import TABLE_NEW_SERIES_SUFFIX, TABLE_READY_SUFFIX
from skat.web.seating import create_seating_router
from skat.web.series_end import TABLE_SERIES_END_AGREE_SUFFIX, TABLE_SERIES_END_REFUSE_SUFFIX
from skat.web.tables import (
    AWAITING_TOKENS,
    POSITION_TOKENS,
    RANK_TOKENS,
    SUIT_TOKENS,
    TABLE_PAGE_PREFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
    create_tables_router,
)
from skat.web.wakes import AccountTopic, WakeList
from tests.support.faulty_tables import FaultyTableTransactions
from tests.support.idle_presence import (
    idle_agent_lease,
    idle_empty_table,
    idle_hold,
    idle_next_deal,
    idle_presence,
)
from tests.support.page_build import fixture_page_build
from tests.support.payload_cards import (
    CARDS_BY_SEAT,
    DEALER_SEAT,
    SKAT_CARDS,
    cards_in_text,
    seated_three,
    wire_cards,
)
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import card, card_body
from tests.web.support.skat import FETCH, NAVIGATION, UNKNOWN_ID


class TestCreateTable:
    def test_seats_the_signed_in_opener_in_chair_one_and_answers_with_the_table(self, skat):
        headers, account = skat.member()

        answer = skat.create(headers)

        assert answer.status_code == 200
        assert answer.headers["cache-control"] == "no-store"
        chairs = [(c["seat"], c["occupant_name"], c["is_mine"]) for c in answer.json()["chairs"]]
        assert chairs == [
            (1, account.username, True),
            (2, None, False),
            (3, None, False),
        ]

    def test_wakes_the_account_of_the_opener_after_the_commit(self, skat):
        headers, opener = skat.member()
        heard = counting_account_wakes(skat, opener)

        skat.create(headers)

        assert heard == {opener.id: [1]}

    def test_answers_a_retry_with_the_same_table(self, skat):
        headers, _ = skat.member()

        first = skat.create(headers).json()

        assert skat.create(headers).json() == first
        assert len(skat.store.tables) == 1

    def test_refuses_a_command_id_that_comes_back_with_another_request(self, skat):
        headers, account = skat.member()
        skat.create(headers)
        receipt = skat.store.receipts[(account.id, "command-0001")]
        skat.store.receipts[(account.id, "command-0001")] = type(receipt)(
            receipt.account_id, receipt.command_id, "another-command", receipt.payload, receipt.table_id
        )

        assert skat.create(headers).status_code == 409
        assert len(skat.store.tables) == 1

    @pytest.mark.parametrize("extra", [{"chair": 2}, {"account_id": "someone-else"}, {"seat": 3, "username": "x"}])
    def test_refuses_a_request_that_names_a_chair_or_an_account_and_writes_nothing(self, skat, extra):
        headers, _ = skat.member()

        assert skat.create(headers, **extra).status_code == 422
        assert skat.store.tables == {}

    @pytest.mark.parametrize("command_id", ["", "short", "has space in it", "x" * 65])
    def test_refuses_a_malformed_command_id(self, skat, command_id):
        headers, _ = skat.member()

        assert skat.create(headers, command_id=command_id).status_code == 422
        assert skat.store.tables == {}

    def test_signed_out_writes_nothing_and_shows_no_table(self, skat):
        answer = skat.create(FETCH)

        assert answer.status_code == 401
        assert skat.store.tables == {}


class TestReadTable:
    def test_shows_another_member_the_table_with_the_opener_in_chair_one_and_no_chair_of_their_own(self, skat):
        opener_headers, opener = skat.member()
        table_id = skat.create(opener_headers).json()["id"]
        visitor_headers, _ = skat.member()

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=visitor_headers)

        assert answer.status_code == 200
        assert answer.headers["cache-control"] == "no-store"
        chairs = [(c["occupant_name"], c["is_mine"], c["ready"]) for c in answer.json()["chairs"]]
        assert chairs == [
            (opener.username, False, False),
            (None, False, False),
            (None, False, False),
        ]

    def test_shows_the_opener_the_same_table_after_a_reload(self, skat):
        headers, _ = skat.member()
        created = skat.create(headers).json()

        assert skat.client.get(f"{TABLES_PATH}/{created['id']}", headers=headers).json() == created

    def test_reads_who_is_connected_on_the_event_loop_that_owns_the_presence(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]
        threads_with_a_loop = []

        class ProbingPresence(Presence):
            def connected(self, read_table_id):
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    threads_with_a_loop.append(False)
                else:
                    threads_with_a_loop.append(True)
                return super().connected(read_table_id)

        skat.app.include_router(
            create_tables_router(
                TableService(skat.store),
                fixture_page_build(),
                ProbingPresence(idle_hold(), idle_next_deal(), idle_empty_table(), idle_agent_lease(), WakeList()),
                skat.stores.sessions,
                skat.config,
            )
        )
        # The probing router goes first so that it, not the composed one, answers the read.
        skat.app.router.routes.insert(0, skat.app.router.routes.pop())

        skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers)

        assert threads_with_a_loop == [True]

    @pytest.mark.parametrize("table_id", [UNKNOWN_ID, "not-an-id", "%27%3B--", "A" * 32])
    def test_an_unknown_or_malformed_id_is_not_found_without_a_database_message(self, skat, table_id):
        headers, _ = skat.member()

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers)

        assert answer.status_code == 404
        assert answer.json() == {"detail": "table not found"}

    def test_signed_out_gets_no_table_data(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=FETCH)

        assert answer.status_code == 401
        assert table_id not in answer.text

    def test_shows_a_seated_member_without_a_stream_as_away_to_every_other_viewer_and_names_no_account(self, skat):
        headers, account = skat.member()
        table_id = skat.create(headers).json()["id"]
        other_headers, other = skat.member()

        answers = [
            skat.client.get(f"{TABLES_PATH}/{table_id}", headers=viewer_headers)
            for viewer_headers in (other_headers, headers)
        ]

        assert [[c["is_away"] for c in answer.json()["chairs"]] for answer in answers] == [
            [True, False, False],
            [False, False, False],
        ]
        assert all(account.id not in answer.text and other.id not in answer.text for answer in answers)

    def test_gives_no_chair_a_total_before_the_first_game(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers)

        assert [chair["total"] for chair in answer.json()["chairs"]] == [None, None, None]


class TestTablePage:
    def test_serves_the_page_shell_to_a_member_for_any_id(self, skat):
        headers, _ = skat.member()

        for table_id in (UNKNOWN_ID, "anything"):
            answer = skat.client.get(f"{TABLE_PAGE_PREFIX}{table_id}", headers={**headers, **NAVIGATION})
            assert answer.status_code == 200
            assert answer.content == fixture_page_build().shell_in("de").content
            assert answer.headers["cache-control"] == "no-cache"

    def test_sends_a_signed_out_visitor_to_the_sign_in_page(self, skat):
        answer = skat.client.get(f"{TABLE_PAGE_PREFIX}{UNKNOWN_ID}", headers=NAVIGATION)

        assert answer.status_code == 302


def sit_at_seat_two(skat, headers, table_id):
    return skat.sit(headers, table_id, 2, command_id="command-act")


def stand_after_sitting(skat, headers, table_id):
    skat.sit(headers, table_id, 2)
    return skat.stand(headers, table_id, command_id="command-act")


class RecordingPresence(Presence):
    def __init__(self):
        super().__init__(idle_hold(), idle_next_deal(), idle_empty_table(), idle_agent_lease(), WakeList())
        self.woken = []

    def wake_table(self, table_id):
        self.woken.append(table_id)
        super().wake_table(table_id)


def answering_first(skat, tables, presence, wakes=None):
    """Route requests through tables and seating routers that have this service, presence and wake list, ahead of
    the composed ones.
    """
    composed = list(skat.app.router.routes)
    skat.app.include_router(create_seating_router(tables, presence, wakes or WakeList()))
    skat.app.include_router(
        create_tables_router(tables, fixture_page_build(), presence, skat.stores.sessions, skat.config)
    )
    skat.app.router.routes[:] = skat.app.router.routes[len(composed) :] + composed


def counting_account_wakes(skat, *accounts):
    """Seating routers over a wake list in which one stream listens to each account; returns what each hears."""
    wakes = WakeList()
    heard = {account.id: [] for account in accounts}
    for account in accounts:
        wakes.register([AccountTopic(account.id)], lambda account=account: heard[account.id].append(1))
    answering_first(skat, TableService(skat.store), idle_presence(wakes), wakes)
    return heard


@pytest.fixture
def table(skat):
    headers, owner = skat.member()
    return skat.create(headers).json()["id"], owner


class TestSitDown:
    def test_seats_the_member_in_the_chair_and_answers_with_the_table_they_see(self, skat, table):
        table_id, owner = table
        headers, account = skat.member()

        answer = skat.sit(headers, table_id, 2)

        assert answer.status_code == 200
        assert answer.headers["cache-control"] == "no-store"
        chairs = [(c["occupant_name"], c["is_mine"]) for c in answer.json()["chairs"]]
        assert chairs == [
            (owner.username, False),
            (account.username, True),
            (None, False),
        ]

    @pytest.mark.parametrize(
        "act", [pytest.param(sit_at_seat_two, id="sit"), pytest.param(stand_after_sitting, id="stand")]
    )
    def test_answers_an_occupant_with_a_connected_stream_as_present(self, skat, table, act):
        table_id, owner = table
        headers, _ = skat.member()
        presence = idle_presence()
        answering_first(skat, TableService(skat.store), presence)
        asyncio.run(presence.subscribe(table_id, owner.id, lambda: None))

        answer = act(skat, headers, table_id)

        assert answer.json()["chairs"][0]["is_away"] is False

    def test_the_second_one_for_a_chair_is_told_who_got_it(self, skat, table):
        table_id, owner = table
        headers, _ = skat.member()

        answer = skat.sit(headers, table_id, 1)

        assert answer.status_code == 409
        assert answer.json() == {"reason": "seat-taken", "holder_name": owner.username}

    def test_a_seated_member_asking_for_a_second_chair_is_refused_and_keeps_the_first(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)

        answer = skat.sit(headers, table_id, 3, command_id="command-second")

        assert answer.status_code == 409
        assert answer.json()["reason"] == "already-seated"
        mine = [c["is_mine"] for c in skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers).json()["chairs"]]
        assert mine == [False, True, False]

    def test_a_retry_with_the_same_command_id_answers_with_the_first_outcome_and_writes_nothing_more(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        first = skat.sit(headers, table_id, 2).json()
        written = dict(skat.store.tables)

        assert skat.sit(headers, table_id, 2).json() == first
        assert skat.store.tables == written

    def test_refuses_a_command_id_that_comes_back_with_another_chair(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)

        assert skat.sit(headers, table_id, 3).status_code == 409
        assert skat.sit(headers, table_id, 3).json() == {"detail": "command id reused with another request"}

    @pytest.mark.parametrize("seat", [0, 4, -1, "two", None, "2", 2.0, True])
    def test_refuses_a_seat_that_is_no_whole_chair_number_and_writes_nothing(self, skat, table, seat):
        table_id, _ = table
        headers, _ = skat.member()
        before = dict(skat.store.tables)

        assert skat.sit(headers, table_id, seat).status_code == 422
        assert skat.store.tables == before

    @pytest.mark.parametrize("extra", [{"account_id": "someone-else"}, {"username": "x"}])
    def test_refuses_a_request_that_names_an_account(self, skat, table, extra):
        table_id, _ = table
        headers, _ = skat.member()

        assert skat.sit(headers, table_id, 2, **extra).status_code == 422

    def test_signed_out_writes_nothing(self, skat, table):
        table_id, _ = table
        before = dict(skat.store.tables)

        assert skat.sit(FETCH, table_id, 2).status_code == 401
        assert skat.store.tables == before

    @pytest.mark.parametrize("table_id", [UNKNOWN_ID, "not-an-id", "A" * 32])
    def test_an_unknown_or_malformed_table_is_not_found_and_writes_nothing(self, skat, table_id):
        headers, _ = skat.member()

        answer = skat.sit(headers, table_id, 1)

        assert answer.status_code == 404
        assert answer.json() == {"detail": "table not found"}
        assert skat.store.tables == {}
        assert skat.store.receipts == {}

    def test_wakes_every_stream_of_the_table_after_the_commit(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        presence = RecordingPresence()
        answering_first(skat, TableService(skat.store), presence)

        skat.sit(headers, table_id, 2)

        assert presence.woken == [table_id]

    def test_a_refusal_changes_nothing_and_wakes_nobody(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        presence = RecordingPresence()
        answering_first(skat, TableService(skat.store), presence)

        skat.sit(headers, table_id, 1)

        assert presence.woken == []

    def test_wakes_the_account_of_the_sitter_and_no_other_after_the_commit(self, skat, table):
        table_id, owner = table
        headers, sitter = skat.member()
        heard = counting_account_wakes(skat, sitter, owner)

        skat.sit(headers, table_id, 2)

        assert heard == {sitter.id: [1], owner.id: []}

    def test_a_refusal_wakes_no_account(self, skat, table):
        table_id, _ = table
        headers, sitter = skat.member()
        heard = counting_account_wakes(skat, sitter)

        skat.sit(headers, table_id, 1)

        assert heard == {sitter.id: []}

    def test_a_failing_transaction_writes_and_publishes_nothing(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        presence = RecordingPresence()

        faulty = TableService(FaultyTableTransactions(skat.store, receipt_failure=RuntimeError("connection lost")))
        answering_first(skat, faulty, presence)
        before = (dict(skat.store.tables), dict(skat.store.receipts))

        with pytest.raises(RuntimeError, match="connection lost"):
            skat.sit(headers, table_id, 2)

        assert presence.woken == []
        state = (skat.store.tables, skat.store.receipts)
        assert state == before


class TestStandUp:
    def test_frees_the_own_chair_keeping_every_number(self, skat, table):
        table_id, owner = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 3)

        answer = skat.stand(headers, table_id)

        assert answer.status_code == 200
        chairs = [(c["seat"], c["occupant_name"], c["is_mine"]) for c in answer.json()["chairs"]]
        assert chairs == [
            (1, owner.username, False),
            (2, None, False),
            (3, None, False),
        ]

    def test_a_member_without_a_chair_is_refused_and_nothing_changes(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        before = dict(skat.store.tables)

        answer = skat.stand(headers, table_id)

        assert answer.status_code == 409
        assert answer.json() == {"reason": "not-seated", "holder_name": None}
        assert skat.store.tables == before

    def test_a_retry_answers_with_the_first_outcome(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)
        first = skat.stand(headers, table_id).json()

        assert skat.stand(headers, table_id).json() == first

    def test_refuses_a_command_id_that_a_sit_already_used(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)

        assert skat.stand(headers, table_id, command_id="command-sit").status_code == 409

    def test_signed_out_writes_nothing(self, skat, table):
        table_id, _ = table
        before = (dict(skat.store.tables), dict(skat.store.receipts))

        assert skat.stand(FETCH, table_id).status_code == 401
        state = (skat.store.tables, skat.store.receipts)
        assert state == before

    def test_an_unknown_table_is_not_found(self, skat):
        headers, _ = skat.member()

        assert skat.stand(headers, UNKNOWN_ID).status_code == 404

    def test_wakes_every_stream_of_the_table_after_the_commit(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)
        presence = RecordingPresence()
        answering_first(skat, TableService(skat.store), presence)

        skat.stand(headers, table_id, command_id="command-stand")

        assert presence.woken == [table_id]


HAND_KEYS = {
    "dealer_seat",
    "own_cards",
    "skat_count",
    "auction",
    "declaring",
    "playing",
    "ramsch",
    "waiting_seat",
    "pushing",
    "pushes",
}


def read(skat, headers, table_id):
    return skat.client.get(f"{TABLES_PATH}/{table_id}", headers=headers)


class TestHandInPayloads:
    def test_the_sit_that_deals_answers_the_sitter_with_their_own_ten_cards_and_no_other_card(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(skat.member()[0], table_id, 2, command_id="command-second")

        answer = skat.sit(headers, table_id, 3)

        stored = skat.store.tables[table_id]
        found = cards_in_text(answer.text)
        assert found == wire_cards(stored.hand.hands[positions_from(stored.dealer)[3]])
        assert not found & wire_cards(stored.hand.skat)
        hand = answer.json()["hand"]
        assert (hand["dealer_seat"], hand["skat_count"]) == (stored.dealer, 2)
        assert [(c["hand"]["card_count"]) for c in answer.json()["chairs"]] == [10, 10, 10]
        assert all(c["hand"]["position"] for c in answer.json()["chairs"])

    def test_writes_each_card_and_each_position_as_a_word_and_gives_the_hand_its_keys(self, skat):
        table_id, people = seated_three(skat)
        cleo_headers, _ = people[2]

        body = read(skat, cleo_headers, table_id).json()

        assert set(body["hand"]) == HAND_KEYS
        assert body["hand"]["own_cards"][0] == {"suit": "kreuz", "rank": "seven"}
        assert body["hand"]["own_cards"][-1] == {"suit": "pik", "rank": "eight"}
        assert [chair["hand"] for chair in body["chairs"]] == [
            {"position": "middlehand", "card_count": 10},
            {"position": "rearhand", "card_count": 10},
            {"position": "forehand", "card_count": 10},
        ]
        assert body["hand"]["dealer_seat"] == DEALER_SEAT

    @pytest.mark.parametrize(
        ("who", "own"),
        [
            pytest.param(0, CARDS_BY_SEAT[1], id="anna"),
            pytest.param(1, CARDS_BY_SEAT[2], id="ben"),
            pytest.param(2, CARDS_BY_SEAT[3], id="cleo"),
            pytest.param(3, (), id="dora-without-a-chair"),
        ],
    )
    def test_a_read_carries_exactly_the_readers_own_cards(self, skat, who, own):
        table_id, people = seated_three(skat)

        answer = read(skat, people[who][0], table_id)

        assert cards_in_text(answer.text) == wire_cards(own)
        assert not cards_in_text(answer.text) & wire_cards(SKAT_CARDS)

    @pytest.mark.parametrize("who", [0, 1, 2, 3], ids=["anna", "ben", "cleo", "dora-without-a-chair"])
    def test_no_viewer_gets_the_skats_cards_only_its_count(self, skat, who):
        table_id, people = seated_three(skat)

        body = read(skat, people[who][0], table_id)

        assert not cards_in_text(body.text) & wire_cards(SKAT_CARDS)
        assert body.json()["hand"]["skat_count"] == len(SKAT_CARDS)

    def test_a_viewer_without_a_chair_still_gets_every_position_and_the_dealers_seat(self, skat):
        table_id, people = seated_three(skat)
        dora_headers, _ = people[3]

        body = read(skat, dora_headers, table_id).json()

        assert [chair["hand"]["position"] for chair in body["chairs"]] == ["middlehand", "rearhand", "forehand"]
        assert body["hand"]["dealer_seat"] == DEALER_SEAT

    def test_a_replayed_sit_shows_the_replayers_own_cards_and_no_other_card(self, skat):
        table_id, people = seated_three(skat)
        cleo_headers, _ = people[2]

        answer = skat.sit(cleo_headers, table_id, 3, command_id="command-sit-3")

        assert cards_in_text(answer.text) == wire_cards(CARDS_BY_SEAT[3])

    def test_a_replayed_create_shows_the_creators_own_cards_and_no_other_card(self, skat):
        table_id, people = seated_three(skat)

        answer = skat.create(people[0][0])

        assert answer.json()["id"] == table_id
        assert cards_in_text(answer.text) == wire_cards(CARDS_BY_SEAT[1])

    def test_a_replayed_sit_of_someone_who_has_since_stood_up_carries_no_card(self, skat, table):
        table_id, _ = table
        dora_headers, _ = skat.member()
        skat.sit(dora_headers, table_id, 2, command_id="command-dora-sit")
        skat.stand(dora_headers, table_id)
        skat.sit(skat.member()[0], table_id, 2, command_id="command-ben")
        skat.sit(skat.member()[0], table_id, 3, command_id="command-cleo")

        answer = skat.sit(dora_headers, table_id, 2, command_id="command-dora-sit")

        assert answer.json()["hand"]["own_cards"] == []
        assert cards_in_text(answer.text) == set()

    def test_standing_up_during_a_hand_answers_with_the_keys_of_a_stand_up_between_hands_and_no_card_or_account(
        self, skat
    ):
        table_id, people = seated_three(skat)
        between = skat.create(people[3][0], command_id="command-between").json()["id"]
        between_hands = skat.stand(people[3][0], between, command_id="command-between-stand")

        answer = skat.stand(people[0][0], table_id, command_id="command-leave")

        assert (answer.status_code, set(answer.json())) == (200, set(between_hands.json()))
        assert answer.json()["hand"]["waiting_seat"] == 1
        assert cards_in_text(answer.text) == set()
        assert all(account.id not in answer.text for _, account in people)

    def test_a_table_without_a_hand_has_no_hand_on_the_table_or_on_any_chair(self, skat, table):
        table_id, _ = table
        headers, _ = skat.member()
        skat.sit(headers, table_id, 2)

        answers = [skat.create(headers), read(skat, headers, table_id), skat.stand(headers, table_id)]

        for answer in answers:
            body = answer.json()
            assert body["hand"] is None
            assert [chair["hand"] for chair in body["chairs"]] == [None, None, None]


class TestTokens:
    @pytest.mark.parametrize(
        ("tokens", "members"),
        [
            pytest.param(SUIT_TOKENS, Suit, id="suits"),
            pytest.param(RANK_TOKENS, Rank, id="ranks"),
            pytest.param(POSITION_TOKENS, Position, id="positions"),
            pytest.param(AWAITING_TOKENS, Awaiting, id="awaiting"),
        ],
    )
    def test_every_member_has_exactly_one_token_and_no_two_share_one(self, tokens, members):
        assert set(tokens) == set(members)
        assert len(set(tokens.values())) == len(members)


class TestADealtTableWhoseChairsAllOpened:
    def test_the_last_person_standing_up_during_a_hand_leaves_the_table_frozen_and_no_empty_end_follows(
        self, server, time, hold
    ):
        table_id, people = seated_three(server)
        for number, (headers, _) in enumerate(people[:3], start=1):
            stood = server.stand(headers, table_id, command_id=f"command-leave-{number}")
            assert stood.status_code == 200, stood.text
        before = dict(server.store.tables)

        server.client.portal.call(time.advance, hold.settings.empty_table_seconds)

        record = server.store.tables[table_id]
        assert server.store.tables == before
        assert (record.hand is not None, [chair.occupant for chair in record.chairs]) == (True, [None, None, None])
        assert read(server, people[0][0], table_id).json()["hand"]["waiting_seat"] == 1


class TestAnEmptyTableEnds:
    @pytest.fixture
    def ended(self, server, time, hold):
        """A table its opener left alone for the whole wait: the opener's headers, the table's id and the wait."""
        headers, _ = server.member()
        table_id = server.create(headers).json()["id"]
        server.client.portal.call(time.advance, hold.settings.empty_table_seconds)
        return headers, table_id, hold.settings.empty_table_seconds

    def test_a_created_table_starts_one_wait_and_a_retry_neither_restarts_nor_adds_one(self, server, time):
        headers, _ = server.member()

        first = server.create(headers)
        again = server.create(headers)

        assert again.json() == first.json()
        assert time.pending == 1
        assert first.json()["ended"] is None

    def test_a_create_retry_read_while_the_table_ends_leaves_no_wait_behind(self, server):
        class EndingDuringTheView:
            """The service whose view read is overtaken by the table's end, which the presence answers on the loop."""

            def __init__(self, tables, ending):
                self._tables = tables
                self._ending = ending

            def __getattr__(self, name):
                return getattr(self._tables, name)

            def view(self, actor, table_id, connected_accounts):
                view = self._tables.view(actor, table_id, connected_accounts)
                server.client.portal.call(self._ending, table_id)
                return view

        presence = idle_presence()
        answering_first(server, EndingDuringTheView(TableService(server.store), presence.waits.drop), presence)
        headers, _ = server.member()

        answer = server.create(headers)

        table_id = answer.json()["id"]
        assert answer.status_code == 200, answer.text
        assert presence.waits.is_current(table_id, server.store.tables[table_id].version) is False

    def test_the_ended_table_answers_with_the_reason_and_the_wait_and_names_nobody(self, server, ended):
        headers, table_id, seconds = ended

        answer = server.client.get(f"{TABLES_PATH}/{table_id}", headers=headers).json()

        assert answer["ended"] == {"reason": "empty", "empty_seconds": seconds}
        assert answer["chairs"] == []
        assert answer["watchers"] == 0
        assert [answer["hand"], answer["result"], answer["passed_in"]] == [None, None, None]

    def test_a_create_retry_returns_the_ended_table_and_starts_no_wait(self, server, time, ended):
        headers, table_id, seconds = ended
        tables_before = dict(server.store.tables)

        again = server.create(headers).json()

        assert again["id"] == table_id
        assert again["ended"]["empty_seconds"] == seconds
        assert server.store.tables == tables_before
        assert time.pending == 0

    @pytest.mark.parametrize(
        ("suffix", "body"),
        [
            pytest.param(TABLE_SIT_SUFFIX, {"seat": 2}, id="sit"),
            pytest.param(TABLE_STAND_SUFFIX, {}, id="stand"),
            pytest.param(TABLE_AUCTION_PASS_SUFFIX, {"version": 1}, id="auction"),
            pytest.param(TABLE_DECLARING_TAKE_SUFFIX, {"version": 1}, id="declaring"),
            pytest.param(TABLE_CARD_SUFFIX, {"version": 1, **card_body(card("C7"))}, id="card"),
            pytest.param(TABLE_GIVE_UP_SUFFIX, {"version": 1}, id="give-up"),
            pytest.param(TABLE_GIVE_UP_AGREE_SUFFIX, {"version": 1}, id="give-up-agree"),
            pytest.param(TABLE_GIVE_UP_DECLINE_SUFFIX, {"version": 1}, id="give-up-decline"),
            pytest.param(TABLE_THROW_DOWN_SUFFIX, {"version": 1}, id="throw-down"),
            pytest.param(TABLE_KONTRA_SUFFIX, {"version": 1, "word": "kontra"}, id="kontra"),
            pytest.param(TABLE_READY_SUFFIX, {"ordinal": 1}, id="ready"),
            pytest.param(TABLE_NEW_SERIES_SUFFIX, {}, id="new-series"),
            pytest.param(TABLE_SERIES_END_AGREE_SUFFIX, {}, id="series-end-agree"),
            pytest.param(TABLE_SERIES_END_REFUSE_SUFFIX, {}, id="series-end-refuse"),
        ],
    )
    def test_a_command_at_the_ended_table_is_not_found_and_writes_nothing(self, server, ended, suffix, body):
        headers, table_id, _ = ended
        written = (dict(server.store.tables), dict(server.store.receipts))

        answer = server.client.post(
            f"{TABLES_PATH}/{table_id}{suffix}",
            json={"command_id": "command-at-end", **body},
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

        assert answer.status_code == 404
        assert server.store.tables == written[0]
        assert server.store.receipts == written[1]
