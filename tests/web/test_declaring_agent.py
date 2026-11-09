import copy

import pytest

from skat.engine.bidding import VALID_BIDS
from skat.engine.deal import Position, positions_from
from skat.engine.declaration import Announcement, Declaration, DeclarationRefusal
from skat.engine.games import GameKind
from skat.table.declaring import DECLARING_STEP_COMMAND
from skat.table.hand_state import declaring_of
from skat.table.records import Refusal
from skat.web.declaring import (
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
)
from skat.web.mcp import (
    AGENT_GROUP,
    AUCTION_BID_TOOL,
    AUCTION_PLAY_TOOL,
    DECLARE_GAME_TOOL,
    PLAY_CARD_TOOL,
    PUT_BACK_CARDS_TOOL,
    TAKE_SKAT_TOOL,
)
from skat.web.tables import TABLES_PATH, AnnouncementToken, GameToken
from tests.support.payload_cards import (
    DEALER_SEAT,
    FOREHAND_CARDS,
    MIDDLEHAND_CARDS,
    SKAT_CARDS,
    cards_in,
    wire_cards,
)
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.agent import SUBJECT, Agent, person_passes
from tests.web.support.playing import card_body
from tests.web.support.skat import FETCH, UNKNOWN_ID, Skat, streams_of

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
PUT_BACK_CARDS = (MIDDLEHAND_CARDS[0], SKAT_CARDS[0])
STEP_SUFFIXES = (TABLE_DECLARING_TAKE_SUFFIX, TABLE_DECLARING_PUT_BACK_SUFFIX, TABLE_DECLARING_DECLARE_SUFFIX)
RETIRED_UNION_SUFFIX = "/declaration"


@pytest.fixture
def skat(hold, issuer):
    skat = Skat(lambda: hold, issuer_transports=issuer.transports)
    with skat.client:
        yield skat


def declare_fields(game=GameToken.HERZ, *, hand=False, ouvert=False, announcement=AnnouncementToken.NONE):
    return {"game": game, "hand": hand, "ouvert": ouvert, "announcement": announcement}


def put_back_fields(*cards):
    return {"cards": [card_body(each) for each in cards]}


def seat_of(position):
    return next(seat for seat, held in positions_from(DEALER_SEAT).items() if held is position)


def hand_of(view):
    return view["hand"]


def stored(skat):
    return copy.deepcopy((skat.store.tables, skat.store.receipts))


def direct_view(table, position):
    answer = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}", headers=table.at[position])
    table.skat.client.cookies.clear()
    return answer.json()


def other_viewers(table):
    return {"forehand": table.at[FOREHAND], "rearhand": table.at[REARHAND], "watcher": table.watcher}


def skat_cards_seen_by_others(table, cards=SKAT_CARDS):
    return {
        name: wire_cards(cards) & cards_in(table.read_as(headers).json())
        for name, headers in other_viewers(table).items()
    }


@pytest.fixture
def declarer(agent, middlehand_auction):
    """The agent holds the middlehand chair and has won the auction with a bid of its own tool."""
    table = middlehand_auction
    assert not agent.take_step(AUCTION_BID_TOOL, table, command_id="agent-bid", value=VALID_BIDS[0]).is_error
    person_passes(table, FOREHAND)
    person_passes(table, REARHAND)
    return table


@pytest.fixture
def forehand_declarer(agent, forehand_auction):
    """The agent holds the forehand chair and has won the auction by playing the lowest game."""
    table = forehand_auction
    person_passes(table, MIDDLEHAND)
    person_passes(table, REARHAND)
    assert not agent.take_step(AUCTION_PLAY_TOOL, table, command_id="agent-play").is_error
    return table


@pytest.fixture
def after_take(agent, declarer):
    assert not agent.take_step(TAKE_SKAT_TOOL, declarer, command_id="agent-take").is_error
    return declarer


@pytest.fixture
def picked(agent, after_take):
    answer = agent.take_step(
        PUT_BACK_CARDS_TOOL, after_take, command_id="agent-put-back", **put_back_fields(*PUT_BACK_CARDS)
    )
    assert not answer.is_error, answer.text
    return after_take


class TestDescriptions:
    @pytest.mark.parametrize(
        ("tool", "stage", "next_tool"),
        [
            pytest.param(TAKE_SKAT_TOOL, "choosing", PUT_BACK_CARDS_TOOL, id="take"),
            pytest.param(PUT_BACK_CARDS_TOOL, "discarding", DECLARE_GAME_TOOL, id="put back"),
            pytest.param(DECLARE_GAME_TOOL, "picked", PLAY_CARD_TOOL, id="declare"),
        ],
    )
    def test_a_description_names_the_stage_it_fits_and_the_tool_that_comes_next(self, agent, tool, stage, next_tool):
        tools = {listed["name"]: listed for listed in agent.request("tools/list").json()["result"]["tools"]}

        assert f'"{stage}"' in tools[tool]["description"]
        assert next_tool in tools[tool]["description"]


class TestReadAsTheDeclarer:
    @pytest.mark.parametrize(
        ("arrangement", "position"),
        [
            pytest.param("declarer", MIDDLEHAND, id="by a bid"),
            pytest.param("forehand_declarer", FOREHAND, id="by play"),
        ],
    )
    def test_the_agent_that_won_the_auction_reads_the_choosing_stage_with_ten_cards(
        self, request, agent, arrangement, position
    ):
        table = request.getfixturevalue(arrangement)

        view = agent.read(table.table_id).json()

        assert view["hand"]["declaring"]["stage"] == "choosing"
        assert view["hand"]["declaring"]["declarer_seat"] == seat_of(position)
        assert next(chair for chair in view["chairs"] if chair["is_mine"])["seat"] == seat_of(position)
        assert len(view["hand"]["own_cards"]) == len(MIDDLEHAND_CARDS)
        assert view["hand"]["skat_count"] == len(SKAT_CARDS)
        assert view == direct_view(table, position)


class TestTakeSkat:
    def test_the_take_gives_the_agent_all_twelve_cards_as_a_person_gets_them(self, agent, declarer):
        before = declarer.record.version

        answer = agent.take_step(TAKE_SKAT_TOOL, declarer, command_id="agent-take")

        assert not answer.is_error, answer.text
        assert answer.json()["version"] == before + 1
        assert answer.json() == direct_view(declarer, MIDDLEHAND)
        assert agent.read(declarer.table_id).json() == answer.json()
        assert len(hand_of(answer.json())["own_cards"]) == len(MIDDLEHAND_CARDS) + len(SKAT_CARDS)
        assert hand_of(answer.json())["skat_count"] == 0

    def test_no_other_viewer_gets_a_skat_card_from_the_take(self, skat, agent, declarer):
        others = [(headers, None) for headers in other_viewers(declarer).values()]
        with streams_of(skat, declarer.table_id, others) as streams:
            agent.take_step(TAKE_SKAT_TOOL, declarer, command_id="agent-take")
            seen = [cards_in(next(stream)) for stream in streams]
        opponent = Agent(skat, agent.issuer, "an-opponent-agent")

        assert all(wire_cards(SKAT_CARDS).isdisjoint(each) for each in seen)
        assert wire_cards(SKAT_CARDS).isdisjoint(cards_in(opponent.read(declarer.table_id).json()))
        assert wire_cards(SKAT_CARDS) <= cards_in(agent.read(declarer.table_id).json())

    def test_a_take_retried_after_the_put_back_never_brings_the_twelve_back(self, agent, picked):
        version = picked.record.version

        again = agent.take_step(TAKE_SKAT_TOOL, picked, command_id="agent-take", version=version - 2)

        assert again.json()["version"] == version
        assert len(hand_of(again.json())["own_cards"]) == len(MIDDLEHAND_CARDS)
        assert picked.record.version == version


class TestPutBackCards:
    def test_two_cards_go_back_and_vanish_from_every_later_payload(self, skat, agent, after_take):
        before = after_take.record.version
        others = [(headers, None) for headers in other_viewers(after_take).values()]

        with streams_of(skat, after_take.table_id, others) as streams:
            answer = agent.take_step(PUT_BACK_CARDS_TOOL, after_take, **put_back_fields(*PUT_BACK_CARDS))
            seen = [cards_in(next(stream)) for stream in streams]

        view = answer.json()
        assert not answer.is_error, answer.text
        assert view["version"] == before + 1
        assert view["hand"]["declaring"]["stage"] == "picked"
        assert view["hand"]["skat_count"] == len(SKAT_CARDS)
        assert len(view["hand"]["own_cards"]) == len(MIDDLEHAND_CARDS)
        assert wire_cards(PUT_BACK_CARDS).isdisjoint(cards_in(view))
        assert all(wire_cards(PUT_BACK_CARDS).isdisjoint(each) for each in seen)
        assert wire_cards(PUT_BACK_CARDS).isdisjoint(cards_in(agent.read(after_take.table_id).json()))

    def test_the_kept_skat_card_is_the_declarers_own_card(self, agent, picked):
        kept = wire_cards(SKAT_CARDS[1:])

        assert kept <= cards_in(agent.read(picked.table_id).json())
        assert all(not seen for seen in skat_cards_seen_by_others(picked, SKAT_CARDS[1:]).values())


class TestDeclareGame:
    def test_declaring_after_the_pick_up_starts_the_play_with_the_forehand_to_lead(self, agent, picked):
        answer = agent.take_step(DECLARE_GAME_TOOL, picked, command_id="agent-declare", **declare_fields())

        view = answer.json()
        assert not answer.is_error, answer.text
        assert view["hand"]["declaring"]["stage"] == "declared"
        assert view["hand"]["playing"]["turn_seat"] == seat_of(FOREHAND)

    def test_a_hand_game_declared_at_the_choosing_stage_never_shows_the_skat(self, agent, declarer):
        answer = agent.take_step(DECLARE_GAME_TOOL, declarer, **declare_fields(hand=True))

        view = answer.json()
        assert not answer.is_error, answer.text
        assert view["hand"]["declaring"]["stage"] == "declared"
        assert len(view["hand"]["own_cards"]) == len(MIDDLEHAND_CARDS)
        assert wire_cards(SKAT_CARDS).isdisjoint(cards_in(view))
        assert wire_cards(SKAT_CARDS).isdisjoint(cards_in(agent.read(declarer.table_id).json()))
        assert not any(skat_cards_seen_by_others(declarer).values())

    @pytest.mark.parametrize(
        ("arrangement", "fields", "stored_declaration"),
        [
            pytest.param(
                "declarer",
                declare_fields(hand=True, announcement=AnnouncementToken.SCHNEIDER),
                Declaration(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.SCHNEIDER),
                id="suit hand schneider",
            ),
            pytest.param(
                "declarer",
                declare_fields(hand=True, announcement=AnnouncementToken.SCHWARZ),
                Declaration(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.SCHWARZ),
                id="suit hand schwarz",
            ),
            pytest.param(
                "declarer",
                declare_fields(GameToken.GRAND, hand=True),
                Declaration(GameKind.GRAND, hand=True, ouvert=False, announcement=Announcement.NONE),
                id="grand hand",
            ),
            pytest.param(
                "declarer",
                declare_fields(GameToken.GRAND, hand=True, ouvert=True),
                Declaration(GameKind.GRAND, hand=True, ouvert=True, announcement=Announcement.SCHWARZ),
                id="grand ouvert counts as announced schwarz",
            ),
            pytest.param(
                "declarer",
                declare_fields(GameToken.NULL, hand=True),
                Declaration(GameKind.NULL, hand=True, ouvert=False, announcement=Announcement.NONE),
                id="null hand",
            ),
            pytest.param(
                "declarer",
                declare_fields(GameToken.NULL, hand=True, ouvert=True),
                Declaration(GameKind.NULL, hand=True, ouvert=True, announcement=Announcement.NONE),
                id="null ouvert hand",
            ),
            pytest.param(
                "picked",
                declare_fields(GameToken.NULL, ouvert=True),
                Declaration(GameKind.NULL, hand=False, ouvert=True, announcement=Announcement.NONE),
                id="null ouvert after the pick up",
            ),
        ],
    )
    def test_the_ladder_of_games_is_stored_as_the_engine_builds_it(
        self, request, agent, arrangement, fields, stored_declaration
    ):
        table = request.getfixturevalue(arrangement)

        answer = agent.take_step(DECLARE_GAME_TOOL, table, command_id="agent-declare", **fields)

        assert not answer.is_error, answer.text
        assert declaring_of(table.record).declaration == stored_declaration

    def test_a_game_below_the_bid_is_accepted(self, agent, picked):
        answer = agent.take_step(DECLARE_GAME_TOOL, picked, **declare_fields(GameToken.NULL))

        assert not answer.is_error, answer.text


class TestRefusals:
    @pytest.mark.parametrize(
        ("arrangement", "tool", "fields", "reason"),
        [
            pytest.param(
                "declarer",
                PUT_BACK_CARDS_TOOL,
                put_back_fields(*MIDDLEHAND_CARDS[:2]),
                DeclarationRefusal.OUT_OF_ORDER,
                id="put back before the take",
            ),
            pytest.param(
                "declarer",
                DECLARE_GAME_TOOL,
                declare_fields(),
                DeclarationRefusal.OUT_OF_ORDER,
                id="declare without hand at choosing",
            ),
            pytest.param("after_take", TAKE_SKAT_TOOL, {}, DeclarationRefusal.OUT_OF_ORDER, id="take twice"),
            pytest.param(
                "after_take",
                DECLARE_GAME_TOOL,
                declare_fields(),
                DeclarationRefusal.OUT_OF_ORDER,
                id="declare holding twelve",
            ),
            pytest.param(
                "after_take",
                PUT_BACK_CARDS_TOOL,
                put_back_fields(*SKAT_CARDS[:1], FOREHAND_CARDS[0]),
                DeclarationRefusal.NOT_TWO_OF_THE_TWELVE,
                id="a card outside the twelve",
            ),
            pytest.param(
                "after_take",
                PUT_BACK_CARDS_TOOL,
                put_back_fields(SKAT_CARDS[0], SKAT_CARDS[0]),
                DeclarationRefusal.NOT_TWO_OF_THE_TWELVE,
                id="the same card twice",
            ),
            pytest.param(
                "picked",
                DECLARE_GAME_TOOL,
                declare_fields(hand=True),
                DeclarationRefusal.LEVEL_NOT_ALLOWED_AFTER_PICK_UP,
                id="hand after the pick up",
            ),
            pytest.param(
                "picked",
                DECLARE_GAME_TOOL,
                declare_fields(announcement=AnnouncementToken.SCHNEIDER),
                DeclarationRefusal.LEVEL_NOT_ALLOWED_AFTER_PICK_UP,
                id="announcement after the pick up",
            ),
            pytest.param(
                "picked",
                DECLARE_GAME_TOOL,
                declare_fields(ouvert=True),
                DeclarationRefusal.LEVEL_NOT_ALLOWED_AFTER_PICK_UP,
                id="ouvert suit after the pick up",
            ),
            pytest.param(
                "declarer",
                DECLARE_GAME_TOOL,
                declare_fields(GameToken.NULL, hand=True, announcement=AnnouncementToken.SCHNEIDER),
                DeclarationRefusal.ANNOUNCEMENT_IN_NULL,
                id="null hand with an announcement",
            ),
        ],
    )
    def test_the_engine_refusal_is_a_failed_result_that_spends_the_id_and_leaves_the_table(
        self, request, skat, agent, arrangement, tool, fields, reason
    ):
        table = request.getfixturevalue(arrangement)
        before = stored(skat)

        answer = agent.take_step(tool, table, command_id="agent-refused", **fields)

        assert answer.is_error
        assert answer.json() == {"reason": reason, "holder_name": None}
        assert stored(skat)[0] == before[0]
        assert any(command_id == "agent-refused" for _, command_id in skat.store.receipts)

    @pytest.mark.parametrize(
        ("tool", "fields"),
        [
            pytest.param(TAKE_SKAT_TOOL, {}, id="take"),
            pytest.param(PUT_BACK_CARDS_TOOL, put_back_fields(*MIDDLEHAND_CARDS[:2]), id="put back"),
            pytest.param(DECLARE_GAME_TOOL, declare_fields(hand=True), id="declare"),
        ],
    )
    def test_every_step_is_already_declared_once_the_game_is_declared(self, agent, declarer, tool, fields):
        agent.take_step(DECLARE_GAME_TOOL, declarer, command_id="agent-declare", **declare_fields(hand=True))

        answer = agent.take_step(tool, declarer, command_id="agent-again", **fields)

        assert answer.json()["reason"] == DeclarationRefusal.ALREADY_DECLARED

    def test_an_agent_in_a_chair_that_won_nothing_is_refused_as_not_declarer(self, skat, agent, forehand_auction):
        table = forehand_auction
        table.middlehand_wins()
        before = stored(skat)

        answer = agent.take_step(TAKE_SKAT_TOOL, table, command_id="agent-refused")

        assert answer.json()["reason"] == Refusal.NOT_DECLARER
        assert stored(skat)[0] == before[0]

    def test_an_agent_without_a_chair_is_refused_as_not_seated(self, skat, agent, declarer):
        guest = Agent(skat, agent.issuer, "a-guest-agent")
        before = stored(skat)

        answer = guest.take_step(TAKE_SKAT_TOOL, declarer, command_id="agent-refused")

        assert answer.json()["reason"] == Refusal.NOT_SEATED
        assert stored(skat)[0] == before[0]

    def test_a_declaring_step_during_the_auction_is_the_wrong_phase(self, skat, agent, middlehand_auction):
        before = stored(skat)

        answer = agent.take_step(TAKE_SKAT_TOOL, middlehand_auction, command_id="agent-refused")

        assert answer.json()["reason"] == Refusal.WRONG_PHASE
        assert stored(skat)[0] == before[0]

    def test_a_table_with_no_hand_is_refused_as_no_hand(self, skat, agent):
        table_id = skat.create(agent.admitted()).json()["id"]
        before = stored(skat)

        answer = agent.call(TAKE_SKAT_TOOL, table_id=table_id, command_id="agent-step-0001", version=1)

        assert answer.json()["reason"] == Refusal.NO_HAND
        assert stored(skat)[0] == before[0]

    def test_a_stale_version_is_refused_as_stale_version(self, skat, agent, declarer):
        before = stored(skat)

        answer = agent.take_step(
            TAKE_SKAT_TOOL, declarer, command_id="agent-stale", version=declarer.record.version - 1
        )

        assert answer.json()["reason"] == Refusal.STALE_VERSION
        assert stored(skat)[0] == before[0]

    def test_an_unknown_table_is_a_failed_result(self, agent):
        answer = agent.call(TAKE_SKAT_TOOL, table_id=UNKNOWN_ID, command_id="agent-step-0001", version=1)

        assert answer.is_error

    @pytest.mark.parametrize(
        ("tool", "fields"),
        [
            pytest.param(PUT_BACK_CARDS_TOOL, {}, id="no cards"),
            pytest.param(PUT_BACK_CARDS_TOOL, put_back_fields(SKAT_CARDS[0]), id="one card"),
            pytest.param(PUT_BACK_CARDS_TOOL, put_back_fields(*MIDDLEHAND_CARDS[:3]), id="three cards"),
            pytest.param(TAKE_SKAT_TOOL, {"action": "take"}, id="take names an action"),
            pytest.param(
                PUT_BACK_CARDS_TOOL,
                {**put_back_fields(*SKAT_CARDS), "action": "put_back"},
                id="put back names an action",
            ),
            pytest.param(DECLARE_GAME_TOOL, {**declare_fields(), "seat": 1}, id="declare names a seat"),
            pytest.param(DECLARE_GAME_TOOL, {**declare_fields(), "game": "ramsch"}, id="unknown game"),
            pytest.param(DECLARE_GAME_TOOL, {**declare_fields(), "hand": "yes"}, id="hand as a string"),
        ],
    )
    def test_an_argument_that_breaks_the_tools_shape_stores_nothing_and_spends_no_id(
        self, skat, agent, after_take, tool, fields
    ):
        before = stored(skat)

        answer = agent.take_step(tool, after_take, command_id="agent-broken", **fields)

        assert answer.is_error
        assert stored(skat) == before


class TestRetries:
    @pytest.mark.parametrize(
        ("arrangement", "tool", "fields"),
        [
            pytest.param("declarer", TAKE_SKAT_TOOL, {}, id="take"),
            pytest.param("after_take", PUT_BACK_CARDS_TOOL, put_back_fields(*PUT_BACK_CARDS), id="put back"),
            pytest.param("picked", DECLARE_GAME_TOOL, declare_fields(), id="declare"),
        ],
    )
    def test_the_same_call_again_answers_the_same_and_stores_nothing_twice(
        self, request, agent, arrangement, tool, fields
    ):
        table = request.getfixturevalue(arrangement)
        first = agent.take_step(tool, table, command_id="agent-retry", **fields)
        after_first = stored(table.skat)

        again = agent.take_step(tool, table, command_id="agent-retry", version=table.record.version - 1, **fields)

        assert (again.is_error, again.text) == (first.is_error, first.text)
        assert stored(table.skat) == after_first

    @pytest.mark.parametrize(
        ("tool", "fields"),
        [
            pytest.param(DECLARE_GAME_TOOL, declare_fields(GameToken.PIK), id="another game"),
            pytest.param(DECLARE_GAME_TOOL, declare_fields(hand=True), id="another hand flag"),
            pytest.param(TAKE_SKAT_TOOL, {}, id="take on the id of a declare"),
            pytest.param(PUT_BACK_CARDS_TOOL, put_back_fields(*PUT_BACK_CARDS), id="put back on the id of a declare"),
        ],
    )
    def test_the_same_id_with_other_fields_or_on_another_tool_is_refused_as_reused(
        self, skat, agent, picked, tool, fields
    ):
        version = picked.record.version
        agent.take_step(DECLARE_GAME_TOOL, picked, command_id="agent-reused", version=version, **declare_fields())
        after_first = stored(skat)

        answer = agent.take_step(tool, picked, command_id="agent-reused", version=version, **fields)

        assert answer.is_error
        assert "reused" in answer.text
        assert stored(skat) == after_first


class TestOwnAccountAndReceipts:
    def test_each_step_is_recorded_under_the_agents_own_account_as_a_declaring_step(self, skat, agent, declarer):
        agent_id = skat.stores.accounts.get(SUBJECT).id

        agent.take_step(TAKE_SKAT_TOOL, declarer, command_id="agent-take")

        receipt = skat.store.receipts[(agent_id, "agent-take")]
        assert receipt.command == DECLARING_STEP_COMMAND
        assert receipt.table_id.value == declarer.table_id
        assert skat.stores.accounts.get("the-agents-owner") is None


ROUTE_STEPS = [
    pytest.param("declarer", TABLE_DECLARING_TAKE_SUFFIX, {}, id="take"),
    pytest.param("after_take", TABLE_DECLARING_PUT_BACK_SUFFIX, put_back_fields(*PUT_BACK_CARDS), id="put back"),
    pytest.param("picked", TABLE_DECLARING_DECLARE_SUFFIX, declare_fields(), id="declare"),
]


class TestRoutes:
    def test_the_old_union_path_is_gone_for_a_session_and_refused_for_a_token(self, skat, issuer, declarer):
        before = stored(skat)
        path = f"{TABLES_PATH}/{declarer.table_id}{RETIRED_UNION_SUFFIX}"
        body = {"command_id": "command-old", "version": declarer.record.version, "action": "take"}

        by_session = skat.client.post(
            path, json=body, headers={"origin": TEST_PUBLIC_ORIGIN, **declarer.at[MIDDLEHAND]}
        )
        skat.client.cookies.clear()
        by_token = skat.client.post(
            path, json=body, headers={"authorization": f"Bearer {issuer.agent_token(SUBJECT)}", **FETCH}
        )

        assert by_session.status_code == 404
        assert by_token.status_code in {401, 403}
        assert stored(skat) == before

    @pytest.mark.parametrize(("arrangement", "suffix", "fields"), ROUTE_STEPS)
    @pytest.mark.parametrize("headers", [{}, {"origin": TEST_PUBLIC_ORIGIN}], ids=["no origin", "with an origin"])
    def test_the_bearer_posts_each_route_directly_as_the_agents_own_account(
        self, request, skat, issuer, arrangement, suffix, fields, headers
    ):
        table = request.getfixturevalue(arrangement)
        token = issuer.agent_token(SUBJECT)

        answer = skat.client.post(
            f"{TABLES_PATH}/{table.table_id}{suffix}",
            json={"command_id": "agent-direct", "version": table.record.version, **fields},
            headers={"authorization": f"Bearer {token}", **FETCH, **headers},
        )

        assert answer.status_code == 200, answer.text
        assert (skat.stores.accounts.get(SUBJECT).id, "agent-direct") in skat.store.receipts

    @pytest.mark.parametrize("suffix", STEP_SUFFIXES)
    @pytest.mark.parametrize(
        "token_changes",
        [
            pytest.param({"aud": "https://elsewhere.test.invalid/mcp"}, id="wrong audience"),
            pytest.param({"scope": "another-scope"}, id="missing scope"),
            pytest.param({"groups": [AGENT_GROUP]}, id="no mcp group"),
            pytest.param({"iat": 0, "exp": 1}, id="expired"),
        ],
    )
    def test_a_token_that_does_not_fit_is_refused_at_each_route_and_nothing_runs(
        self, skat, issuer, declarer, suffix, token_changes
    ):
        before = stored(skat)
        token = issuer.agent_token(SUBJECT, **token_changes)

        answer = skat.client.post(
            f"{TABLES_PATH}/{declarer.table_id}{suffix}",
            json={"command_id": "agent-direct", "version": declarer.record.version},
            headers={"authorization": f"Bearer {token}", **FETCH},
        )

        assert answer.status_code in {401, 403}
        assert stored(skat) == before

    @pytest.mark.parametrize(("arrangement", "suffix", "fields"), ROUTE_STEPS)
    def test_a_persons_session_posts_each_route_and_gets_the_table_answer(self, request, arrangement, suffix, fields):
        table = request.getfixturevalue(arrangement)
        before = table.record.version

        answer = table.skat.client.post(
            f"{TABLES_PATH}/{table.table_id}{suffix}",
            json={"command_id": "person-step", "version": before, **fields},
            headers={"origin": TEST_PUBLIC_ORIGIN, **table.at[MIDDLEHAND]},
        )

        assert answer.status_code == 200, answer.text
        assert answer.headers["cache-control"] == "no-store"
        assert answer.json()["version"] == before + 1

    def test_the_agents_bearer_with_an_origin_is_refused_at_mcp(self, agent):
        answer = agent.request("tools/list", extra_headers={"origin": TEST_PUBLIC_ORIGIN})

        assert answer.status_code == 403
