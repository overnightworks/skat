import itertools
import json
from dataclasses import replace

import pytest

from skat.engine.cards import Card, Rank, Suit
from skat.engine.deal import Deal, Position, positions_from
from skat.engine.tricks import CardPlayed, PlayRefusal
from skat.table.auction import AuctionAction
from skat.table.hand_state import playing_of
from skat.table.records import Refusal
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.declaring import TABLE_DECLARATION_SUFFIX, AnnouncementToken, DeclaringAction, GameToken
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS, TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, KNOWN_DEAL, cards_in_text, seated_three, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import UNKNOWN_ID

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND


def card(text):
    """A card from a suit letter (C, S, H, D) and a rank letter (7, 8, 9, T, J, Q, K, A)."""
    suits = {"C": Suit.KREUZ, "S": Suit.PIK, "H": Suit.HERZ, "D": Suit.KARO}
    ranks = {
        "7": Rank.SEVEN,
        "8": Rank.EIGHT,
        "9": Rank.NINE,
        "T": Rank.TEN,
        "J": Rank.JACK,
        "Q": Rank.QUEEN,
        "K": Rank.KING,
        "A": Rank.ACE,
    }
    return Card(suits[text[0]], ranks[text[1]])


def cards(text):
    return tuple(card(each) for each in text.split())


def card_body(played):
    return {"suit": SUIT_TOKENS[played.suit], "rank": RANK_TOKENS[played.rank]}


def reason_of(answer):
    return answer.json()["reason"]


def post_card(skat, table_id, headers, **changed):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_CARD_SUFFIX}",
        json={"command_id": "command-card", "version": 1, **card_body(card("S7")), **changed},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


# The known deal, as the tricks below read it: forehand holds all of Kreuz and S7 S8; middlehand S9 ST SJ SQ SK SA and
# H7 H8 H9 HT; rearhand HJ HQ HK HA and D7 D8 D9 DT DJ DQ; the skat is DK DA.
SWAPPED_DEAL = Deal(
    forehand=cards("C7 C8 C9 CT CJ CQ CK CA SK S8"),
    middlehand=cards("S9 ST SJ SQ S7 SA H7 H8 H9 HT"),
    rearhand=KNOWN_DEAL.rearhand,
    skat=KNOWN_DEAL.skat,
)


def game_of(*tricks):
    """Every card of a game in the order it is played, read from one string per trick."""
    return tuple(each for trick in tricks for each in cards(trick))


HERZ_GAME = game_of(
    "S7 S9 D7",
    "H7 DJ CJ",
    "S8 ST D8",
    "SQ D9 C7",
    "SK DT C8",
    "SA DQ C9",
    "SJ HJ CT",
    "H8 HQ CQ",
    "HK CK H9",
    "HA CA HT",
)
HERZ_TAKERS = (
    MIDDLEHAND,
    FOREHAND,
    MIDDLEHAND,
    MIDDLEHAND,
    MIDDLEHAND,
    MIDDLEHAND,
    MIDDLEHAND,
    REARHAND,
    REARHAND,
    REARHAND,
)
GRAND_GAME = game_of(
    "S7 S9 D7",
    "H7 HQ C7",
    "D8 C8 ST",
    "D9 C9 SQ",
    "DJ CJ SJ",
    "CT SK DT",
    "CQ SA DQ",
    "S8 H8 HK",
    "CK H9 HA",
    "CA HT HJ",
)
GRAND_TAKERS = (
    MIDDLEHAND,
    REARHAND,
    REARHAND,
    REARHAND,
    FOREHAND,
    FOREHAND,
    FOREHAND,
    FOREHAND,
    FOREHAND,
    REARHAND,
)
NULL_GAME = game_of(
    "S7 SJ D7",
    "S9 D8 S8",
    "ST D9 C7",
    "SQ DT C8",
    "SK DJ C9",
    "SA DQ CT",
    "H7 HJ CJ",
    "HQ CQ H8",
    "HK CK H9",
    "HA CA HT",
)
NULL_TAKERS = (
    MIDDLEHAND,
    MIDDLEHAND,
    MIDDLEHAND,
    MIDDLEHAND,
    MIDDLEHAND,
    MIDDLEHAND,
    REARHAND,
    REARHAND,
    REARHAND,
    REARHAND,
)


class Table:
    """A dealt table with its people told apart by position, and the watcher left over."""

    def __init__(self, skat):
        self.skat = skat
        self.table_id, people = seated_three(skat)
        by_seat = {seat: people[seat - 1][0] for seat in (1, 2, 3)}
        self.at = {position: by_seat[seat] for seat, position in positions_from(DEALER_SEAT).items()}
        self.watcher = people[3][0]
        self._commands = itertools.count(1)

    @property
    def record(self):
        return self.skat.store.tables[self.table_id]

    @property
    def plays(self):
        return self.record.progress.plays

    def fresh_id(self):
        return f"step-{next(self._commands):04d}"

    def with_deal(self, deal):
        self.skat.store.tables[self.table_id] = replace(self.record, hand=deal)

    def _post(self, suffix, position, **body):
        answer = self.skat.client.post(
            f"{TABLES_PATH}/{self.table_id}{suffix}",
            json={"command_id": self.fresh_id(), "version": self.record.version, **body},
            headers={"origin": TEST_PUBLIC_ORIGIN, **self.at[position]},
        )
        assert answer.status_code == 200, answer.text

    def middlehand_wins(self):
        self._post(TABLE_AUCTION_SUFFIX, MIDDLEHAND, action=AuctionAction.BID, value=18)
        self._post(TABLE_AUCTION_SUFFIX, FOREHAND, action=AuctionAction.PASS)
        self._post(TABLE_AUCTION_SUFFIX, REARHAND, action=AuctionAction.PASS)

    def _declare(self, game, *, hand):
        self._post(
            TABLE_DECLARATION_SUFFIX,
            MIDDLEHAND,
            action=DeclaringAction.DECLARE,
            game=game,
            hand=hand,
            ouvert=False,
            announcement=AnnouncementToken.NONE,
        )

    def declared_hand_game(self, game=GameToken.HERZ):
        self.middlehand_wins()
        self._declare(game, hand=True)

    def declared_after_putting_back(self, put_back):
        self.middlehand_wins()
        self._post(TABLE_DECLARATION_SUFFIX, MIDDLEHAND, action=DeclaringAction.TAKE)
        self._post(
            TABLE_DECLARATION_SUFFIX,
            MIDDLEHAND,
            action=DeclaringAction.PUT_BACK,
            cards=[card_body(each) for each in put_back],
        )
        self._declare(GameToken.HERZ, hand=False)

    def send(self, headers, played, *, command_id=None, version=None):
        return self.skat.client.post(
            f"{TABLES_PATH}/{self.table_id}{TABLE_CARD_SUFFIX}",
            json={
                "command_id": command_id or self.fresh_id(),
                "version": self.record.version if version is None else version,
                **card_body(played),
            },
            headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
        )

    def holder_of(self, played):
        return next(position for position, held in self.record.hand.hands.items() if played in held)

    def accepted(self, played, *, command_id=None, version=None):
        before = self.record
        answer = self.send(self.at[self.holder_of(played)], played, command_id=command_id, version=version)
        assert answer.status_code == 200, answer.text
        assert self.record.version == before.version + 1
        assert len(self.plays) == len(before.progress.plays) + 1
        return answer

    def refused(self, headers, played, reason, *, command_id=None, version=None):
        before = self.record
        answer = self.send(headers, played, command_id=command_id, version=version)
        assert answer.status_code == 409, answer.text
        assert reason_of(answer) == reason
        assert self.record == before
        return answer

    def played_out(self, game):
        for played in game:
            self.accepted(played)


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def herz_hand(table):
    table.declared_hand_game()
    return table


class TestAFirstCard:
    def test_forehand_plays_and_the_card_is_the_first_stored(self, herz_hand):
        answer = herz_hand.accepted(card("S7"))

        assert answer.headers["cache-control"] == "no-store"
        assert answer.json()["version"] == herz_hand.record.version
        assert herz_hand.plays == (CardPlayed(FOREHAND, card("S7")),)

    @pytest.mark.parametrize("seat_position", [MIDDLEHAND, REARHAND], ids=lambda position: position.name)
    def test_another_seat_cannot_lead(self, herz_hand, seat_position):
        herz_hand.refused(herz_hand.at[seat_position], card("S9"), PlayRefusal.NOT_YOUR_TURN)


class TestCardsTheRulesForbid:
    def test_a_card_not_held_is_refused(self, herz_hand):
        herz_hand.refused(herz_hand.at[FOREHAND], card("HA"), PlayRefusal.NOT_IN_HAND)

    def test_a_card_put_back_is_no_longer_held(self, table):
        table.declared_after_putting_back(cards("S9 ST"))
        table.accepted(card("S7"))

        table.refused(table.at[MIDDLEHAND], card("S9"), PlayRefusal.NOT_IN_HAND)

    def test_a_hand_game_s_skat_card_is_not_held(self, herz_hand):
        herz_hand.accepted(card("S7"))

        herz_hand.refused(herz_hand.at[MIDDLEHAND], card("DK"), PlayRefusal.NOT_IN_HAND)

    def test_the_led_suit_must_be_followed(self, herz_hand):
        herz_hand.accepted(card("S7"))

        herz_hand.refused(herz_hand.at[MIDDLEHAND], card("H7"), PlayRefusal.MUST_FOLLOW)

    def test_a_jack_does_not_follow_its_printed_suit_in_a_suit_game(self, table):
        table.with_deal(SWAPPED_DEAL)
        table.declared_hand_game()
        table.accepted(card("SK"))

        table.refused(table.at[MIDDLEHAND], card("SJ"), PlayRefusal.MUST_FOLLOW)
        table.accepted(card("S7"))

    def test_without_the_led_suit_any_card_is_accepted(self, herz_hand):
        herz_hand.accepted(card("C7"))

        herz_hand.accepted(card("HT"))


class TestATrick:
    def test_the_third_card_completes_the_trick_and_its_taker_leads_the_next(self, herz_hand):
        for played in cards("S7 S9 D7"):
            herz_hand.accepted(played)

        state = playing_of(herz_hand.record)
        assert [trick.taker for trick in state.tricks] == [MIDDLEHAND]
        herz_hand.refused(herz_hand.at[FOREHAND], card("S8"), PlayRefusal.NOT_YOUR_TURN)
        herz_hand.accepted(card("H7"))


class TestAPlayedOutHand:
    @pytest.mark.parametrize(
        ("game", "script", "takers"),
        [
            pytest.param(GameToken.HERZ, HERZ_GAME, HERZ_TAKERS, id="suit"),
            pytest.param(GameToken.GRAND, GRAND_GAME, GRAND_TAKERS, id="grand"),
            pytest.param(GameToken.NULL, NULL_GAME, NULL_TAKERS, id="null"),
        ],
    )
    def test_ten_tricks_end_the_game_with_each_taker(self, table, game, script, takers):
        table.declared_hand_game(game)

        table.played_out(script)

        state = playing_of(table.record)
        assert tuple(trick.taker for trick in state.tricks) == takers
        assert state.result is not None
        assert len(table.plays) == len(script)

    @pytest.fixture
    def played_out(self, herz_hand):
        herz_hand.played_out(HERZ_GAME)
        return herz_hand

    def test_a_thirty_first_card_is_refused_as_over_and_stores_nothing(self, played_out):
        played_out.refused(played_out.at[FOREHAND], card("S7"), PlayRefusal.OVER)

        assert len(played_out.plays) == len(HERZ_GAME)

    def test_nobody_stands_up_while_the_played_out_hand_is_not_ended(self, played_out, skat):
        answer = skat.stand(played_out.at[FOREHAND], played_out.table_id)

        assert answer.status_code == 409
        assert reason_of(answer) == Refusal.HAND_RUNNING


class TestTheWrongMoment:
    def test_no_hand_is_refused(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = post_card(skat, table_id, headers)

        assert answer.status_code == 409
        assert reason_of(answer) == Refusal.NO_HAND

    def test_a_watcher_is_refused(self, herz_hand):
        herz_hand.refused(herz_hand.watcher, card("S7"), Refusal.NOT_SEATED)

    def test_the_auction_is_the_wrong_phase(self, table):
        table.refused(table.at[FOREHAND], card("S7"), Refusal.WRONG_PHASE)

    def test_the_declaring_is_the_wrong_phase(self, table):
        table.middlehand_wins()

        table.refused(table.at[MIDDLEHAND], card("S9"), Refusal.WRONG_PHASE)

    def test_an_unknown_table_is_not_found(self, herz_hand, skat):
        answer = post_card(skat, UNKNOWN_ID, herz_hand.at[FOREHAND])

        assert answer.status_code == 404


class TestTheBody:
    @pytest.mark.parametrize(
        "changed",
        [
            pytest.param({"seat": 1}, id="a-seat-named"),
            pytest.param({"position": "forehand"}, id="a-position-named"),
            pytest.param({"suit": "lila"}, id="an-unknown-suit"),
            pytest.param({"rank": "one"}, id="an-unknown-rank"),
            pytest.param({"version": "3"}, id="a-version-as-text"),
            pytest.param({"command_id": "short"}, id="a-malformed-retry-key"),
        ],
    )
    def test_a_body_outside_the_contract_is_refused_and_changes_nothing(self, herz_hand, skat, changed):
        before = herz_hand.record

        answer = post_card(skat, herz_hand.table_id, herz_hand.at[FOREHAND], **{"version": before.version, **changed})

        assert answer.status_code == 422
        assert herz_hand.record == before


class TestRetries:
    def test_a_retry_returns_the_same_outcome_and_stores_nothing_new(self, herz_hand):
        version = herz_hand.record.version
        first = herz_hand.accepted(card("S7"), command_id="command-retried", version=version)

        again = herz_hand.send(herz_hand.at[FOREHAND], card("S7"), command_id="command-retried", version=version)

        assert again.status_code == 200
        assert again.json() == first.json()
        assert len(herz_hand.plays) == 1

    def test_a_refused_retry_returns_the_same_refusal(self, herz_hand):
        version = herz_hand.record.version
        herz_hand.refused(
            herz_hand.at[MIDDLEHAND],
            card("S9"),
            PlayRefusal.NOT_YOUR_TURN,
            command_id="command-refused",
            version=version,
        )

        again = herz_hand.send(herz_hand.at[MIDDLEHAND], card("S9"), command_id="command-refused", version=version)

        assert again.status_code == 409
        assert reason_of(again) == PlayRefusal.NOT_YOUR_TURN

    def test_the_same_id_with_another_card_is_refused_as_reused(self, herz_hand):
        version = herz_hand.record.version
        herz_hand.accepted(card("S7"), command_id="command-reused", version=version)
        before = herz_hand.record

        again = herz_hand.send(herz_hand.at[FOREHAND], card("S8"), command_id="command-reused", version=version)

        assert again.status_code == 409
        assert "reused" in again.json()["detail"]
        assert herz_hand.record == before

    def test_a_fresh_command_with_an_old_version_is_refused_as_stale(self, herz_hand):
        version = herz_hand.record.version
        herz_hand.accepted(card("S7"))

        herz_hand.refused(herz_hand.at[MIDDLEHAND], card("S9"), Refusal.STALE_VERSION, version=version)

    def test_an_old_retry_after_the_table_moved_on_is_replayed_before_stale(self, herz_hand):
        version = herz_hand.record.version
        first = herz_hand.accepted(card("S7"), command_id="command-old", version=version)
        herz_hand.accepted(card("S9"))
        later = herz_hand.record

        again = herz_hand.send(herz_hand.at[FOREHAND], card("S7"), command_id="command-old", version=version)

        assert again.status_code == 200
        assert again.json()["version"] == later.version
        assert first.json()["id"] == again.json()["id"]
        assert herz_hand.record == later


class TestTheStream:
    def test_an_accepted_card_sends_a_fresh_snapshot_with_no_foreign_card(self, herz_hand, skat):
        skat.client.cookies.clear()
        events = f"{TABLES_PATH}/{herz_hand.table_id}{TABLE_EVENTS_SUFFIX}"

        with skat.client.stream("GET", events, headers=herz_hand.at[REARHAND]) as stream:
            lines = stream.iter_lines()
            opened = json.loads(next(lines).removeprefix("data: "))
            next(lines)
            skat.client.cookies.clear()
            answer = herz_hand.send(herz_hand.at[FOREHAND], card("S7"), version=opened["version"])
            assert answer.status_code == 200, answer.text
            fresh_line = next(lines)

        fresh = json.loads(fresh_line.removeprefix("data: "))
        assert fresh["version"] == opened["version"] + 1
        assert cards_in_text(fresh_line) <= wire_cards(KNOWN_DEAL.rearhand)
