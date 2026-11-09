import itertools
import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest

from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position, positions_from
from skat.engine.tricks import CardPlayed, PlayRefusal
from skat.table.auction import AuctionAction
from skat.table.hand_state import playing_of
from skat.table.records import Refusal
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.declaring import TABLE_DECLARATION_SUFFIX, AnnouncementToken, DeclaringAction, GameToken
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS, TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, KNOWN_DEAL, SKAT_CARDS, cards_in_text, seated_three, wire_cards
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import UNKNOWN_ID

if TYPE_CHECKING:
    from collections.abc import Callable

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

    def middlehand_bids(self):
        self._post(TABLE_AUCTION_SUFFIX, MIDDLEHAND, action=AuctionAction.BID, value=18)

    def middlehand_wins(self):
        self.middlehand_bids()
        self._post(TABLE_AUCTION_SUFFIX, FOREHAND, action=AuctionAction.PASS)
        self._post(TABLE_AUCTION_SUFFIX, REARHAND, action=AuctionAction.PASS)

    def _declare(self, game, *, hand, ouvert=False, announcement=AnnouncementToken.NONE):
        self._post(
            TABLE_DECLARATION_SUFFIX,
            MIDDLEHAND,
            action=DeclaringAction.DECLARE,
            game=game,
            hand=hand,
            ouvert=ouvert,
            announcement=announcement,
        )

    def declared_hand_game(self, game=GameToken.HERZ):
        self.middlehand_wins()
        self._declare(game, hand=True)

    def declared_grand_ouvert(self):
        self.middlehand_wins()
        self._declare(GameToken.GRAND, hand=True, ouvert=True, announcement=AnnouncementToken.SCHWARZ)

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


SEATS = {MIDDLEHAND: 1, REARHAND: 2, FOREHAND: 3}
CHAIRS_IN_SEAT_ORDER = (MIDDLEHAND, REARHAND, FOREHAND)
ALL_POINTS = 120


def message_body(raw):
    return json.loads(raw.removeprefix("data: "))


def message_at_version(lines, version):
    """The stream's message at a version; someone joining wakes the stream with the old one first."""
    for line in lines:
        if line.startswith("data: ") and message_body(line)["version"] == version:
            return line
    return pytest.fail(f"the stream ended before version {version}")


def in_deck_order(held):
    return tuple(each for each in DECK if each in held)


def remaining(deal, played, position):
    """What a position still holds; a watcher holds nothing."""
    if position is None:
        return ()
    return in_deck_order(set(deal.hands[position]) - set(played))


def table_cards(played):
    """The played cards anyone may see: the last completed trick and the trick in progress."""
    completed = len(played) // 3 * 3
    return played[max(completed - 3, 0) :]


def visible_cards(deal, played, position, *, ouvert):
    open_cards = remaining(deal, played, MIDDLEHAND) if ouvert else ()
    return {*remaining(deal, played, position), *table_cards(played), *open_cards}


def played_body(position, text):
    return {"seat": SEATS[position], "card": card_body(card(text))}


def last_cards(trick):
    """A completed trick names its cards in playing order without their seats."""
    return [played["card"] for played in trick]


def sides(declarer, opponents):
    return {"declarer": declarer, "opponents": opponents}


@dataclass(frozen=True)
class Viewer:
    name: str
    position: Position | None

    def headers_at(self, table):
        return table.watcher if self.position is None else table.at[self.position]


DECLARER = Viewer("declarer", MIDDLEHAND)
FOREHAND_OPPONENT = Viewer("forehand", FOREHAND)
REARHAND_OPPONENT = Viewer("rearhand", REARHAND)
WATCHER = Viewer("watcher", None)
EVERY_VIEWER = (DECLARER, FOREHAND_OPPONENT, REARHAND_OPPONENT, WATCHER)


def herz_hand_game(table):
    table.declared_hand_game()


def swapped_herz_hand_game(table):
    table.with_deal(SWAPPED_DEAL)
    table.declared_hand_game()


def grand_ouvert(table):
    table.declared_grand_ouvert()


@dataclass(frozen=True)
class Moment:
    """A point in a declared game and the `playing` its answer holds; middlehand is the declarer."""

    declare: Callable[[Table], None]
    played: tuple[Card, ...]
    turn: Position | None
    current: tuple[dict[str, object], ...] = ()
    last: tuple[tuple[dict[str, object], ...], Position] | None = None
    tricks_won: tuple[int, int] = (0, 0)
    trick_points: tuple[int, int] = (0, 0)
    legal: tuple[Card, ...] = ()
    deal: Deal = KNOWN_DEAL
    ouvert: bool = False

    def reach(self, table):
        self.declare(table)
        table.played_out(self.played)

    def playing_for(self, viewer):
        last = None if self.last is None else {"cards": last_cards(self.last[0]), "taker_seat": SEATS[self.last[1]]}
        legal = self.legal if viewer.position is not None and viewer.position is self.turn else ()
        return {
            "turn_seat": None if self.turn is None else SEATS[self.turn],
            "current_trick": list(self.current),
            "last_trick": last,
            "tricks_won": sides(*self.tricks_won),
            "trick_points": sides(*self.trick_points),
            "legal_cards": [card_body(each) for each in legal],
        }

    def own_cards_of(self, viewer):
        return remaining(self.deal, self.played, viewer.position)

    def open_cards(self):
        return remaining(self.deal, self.played, MIDDLEHAND) if self.ouvert else ()

    def chair_counts(self):
        return [len(remaining(self.deal, self.played, position)) for position in CHAIRS_IN_SEAT_ORDER]

    def visible_to(self, viewer):
        return visible_cards(self.deal, self.played, viewer.position, ouvert=self.ouvert)


FIRST_TRICK = (played_body(FOREHAND, "S7"), played_body(MIDDLEHAND, "S9"), played_body(REARHAND, "D7"))
SECOND_TRICK = (played_body(MIDDLEHAND, "H7"), played_body(REARHAND, "DJ"), played_body(FOREHAND, "CJ"))
EIGHTH_TRICK = (played_body(MIDDLEHAND, "H8"), played_body(REARHAND, "HQ"), played_body(FOREHAND, "CQ"))
TENTH_TRICK = (played_body(REARHAND, "HA"), played_body(FOREHAND, "CA"), played_body(MIDDLEHAND, "HT"))
MOMENTS = {
    "declared": Moment(herz_hand_game, (), FOREHAND, legal=KNOWN_DEAL.forehand),
    "one-card": Moment(
        herz_hand_game, HERZ_GAME[:1], MIDDLEHAND, current=FIRST_TRICK[:1], legal=cards("S9 ST SQ SK SA")
    ),
    "a-jack-led-in-pik": Moment(
        swapped_herz_hand_game,
        cards("SK"),
        MIDDLEHAND,
        current=(played_body(FOREHAND, "SK"),),
        legal=cards("S7 S9 ST SQ SA"),
        deal=SWAPPED_DEAL,
    ),
    "first-trick": Moment(
        herz_hand_game,
        HERZ_GAME[:3],
        MIDDLEHAND,
        last=(FIRST_TRICK, MIDDLEHAND),
        tricks_won=(1, 0),
        legal=cards("ST SJ SQ SK SA H7 H8 H9 HT"),
    ),
    "second-trick": Moment(
        herz_hand_game,
        HERZ_GAME[:6],
        FOREHAND,
        last=(SECOND_TRICK, FOREHAND),
        tricks_won=(1, 1),
        trick_points=(0, 4),
        legal=cards("C7 C8 C9 CT CQ CK CA S8"),
    ),
    "seventh-card": Moment(
        herz_hand_game,
        HERZ_GAME[:7],
        MIDDLEHAND,
        current=(played_body(FOREHAND, "S8"),),
        last=(SECOND_TRICK, FOREHAND),
        tricks_won=(1, 1),
        trick_points=(0, 4),
        legal=cards("ST SQ SK SA"),
    ),
    "rearhand-leads": Moment(
        herz_hand_game,
        HERZ_GAME[:26],
        MIDDLEHAND,
        current=(played_body(REARHAND, "HK"), played_body(FOREHAND, "CK")),
        last=(EIGHTH_TRICK, REARHAND),
        tricks_won=(6, 2),
        trick_points=(55, 10),
        legal=cards("H9 HT"),
    ),
    "played-out": Moment(
        herz_hand_game,
        HERZ_GAME,
        None,
        last=(TENTH_TRICK, REARHAND),
        tricks_won=(6, 4),
        trick_points=(55, 50),
    ),
    "ouvert-two-cards": Moment(
        grand_ouvert,
        GRAND_GAME[:2],
        REARHAND,
        current=FIRST_TRICK[:2],
        legal=KNOWN_DEAL.rearhand,
        ouvert=True,
    ),
}
MID_TRICK = ("one-card", "seventh-card", "rearhand-leads", "ouvert-two-cards")


def every_viewer_at(names):
    return [
        pytest.param(MOMENTS[name], viewer, id=f"{name}-{viewer.name}") for name in names for viewer in EVERY_VIEWER
    ]


def assert_holds_the_moment(raw, moment, viewer):
    body = message_body(raw)
    hand = body["hand"]
    assert hand["playing"] == moment.playing_for(viewer)
    assert hand["own_cards"] == [card_body(each) for each in moment.own_cards_of(viewer)]
    assert hand["declaring"]["open_cards"] == [card_body(each) for each in moment.open_cards()]
    assert [chair["hand"]["card_count"] for chair in body["chairs"]] == moment.chair_counts()
    assert cards_in_text(raw) == wire_cards(moment.visible_to(viewer))


def middlehand_won(table):
    table.middlehand_wins()


def auction_running(table):
    table.middlehand_bids()


def read(table, headers):
    table.skat.client.cookies.clear()
    answer = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}", headers=headers)
    assert answer.status_code == 200, answer.text
    return answer.text


def stream(table, headers):
    table.skat.client.cookies.clear()
    return table.skat.client.stream("GET", f"{TABLES_PATH}/{table.table_id}{TABLE_EVENTS_SUFFIX}", headers=headers)


def first_stream_message(table, headers):
    with stream(table, headers) as opened:
        first = next(opened.iter_lines())
        opened.close()
    return first


class TestEveryViewersPlaying:
    @pytest.mark.parametrize("before", [auction_running, middlehand_won], ids=["auction", "declaring"])
    @pytest.mark.parametrize("viewer", EVERY_VIEWER, ids=lambda viewer: viewer.name)
    def test_before_the_declaration_there_is_no_playing(self, table, before, viewer):
        before(table)
        headers = viewer.headers_at(table)

        bodies = [message_body(read(table, headers)), message_body(first_stream_message(table, headers))]

        assert [body["hand"]["playing"] for body in bodies] == [None, None]

    @pytest.mark.parametrize(("moment", "viewer"), every_viewer_at(MOMENTS))
    def test_the_read_and_a_new_streams_first_message_hold_exactly_what_the_moment_allows(self, table, moment, viewer):
        moment.reach(table)

        headers = viewer.headers_at(table)

        assert_holds_the_moment(read(table, headers), moment, viewer)
        assert_holds_the_moment(first_stream_message(table, headers), moment, viewer)

    @pytest.mark.parametrize(("moment", "viewer"), every_viewer_at(MID_TRICK))
    def test_a_reload_and_a_new_stream_give_the_same_view_mid_trick(self, table, moment, viewer):
        moment.reach(table)
        headers = viewer.headers_at(table)

        reloads = [message_body(read(table, headers)), message_body(read(table, headers))]
        streamed = message_body(first_stream_message(table, headers))

        assert [body["hand"] for body in reloads] == [streamed["hand"], streamed["hand"]]
        assert [body["chairs"] for body in reloads] == [streamed["chairs"], streamed["chairs"]]

    def test_after_thirty_cards_both_sides_trick_points_and_the_skats_make_all_points(self, table):
        MOMENTS["played-out"].reach(table)

        points = message_body(read(table, table.watcher))["hand"]["playing"]["trick_points"]

        assert points["declarer"] + points["opponents"] + sum(each.points for each in SKAT_CARDS) == ALL_POINTS

    @pytest.mark.parametrize(
        ("declare", "script", "ouvert"),
        [
            pytest.param(herz_hand_game, HERZ_GAME, False, id="hand-game"),
            pytest.param(grand_ouvert, GRAND_GAME, True, id="grand-ouvert"),
        ],
    )
    def test_every_accepted_card_sends_every_open_stream_a_snapshot_naming_only_what_its_viewer_may_see(
        self, table, declare, script, ouvert
    ):
        declare(table)
        with (
            stream(table, DECLARER.headers_at(table)) as declarer_stream,
            stream(table, FOREHAND_OPPONENT.headers_at(table)) as forehand_stream,
            stream(table, REARHAND_OPPONENT.headers_at(table)) as rearhand_stream,
            stream(table, WATCHER.headers_at(table)) as watcher_stream,
        ):
            lines = [
                opened.iter_lines() for opened in (declarer_stream, forehand_stream, rearhand_stream, watcher_stream)
            ]
            for stream_lines in lines:
                next(stream_lines)

            for count, played in enumerate(script, start=1):
                actor = table.holder_of(played)
                answer = table.accepted(played)
                version = table.record.version

                assert cards_in_text(answer.text) == wire_cards(
                    visible_cards(KNOWN_DEAL, script[:count], actor, ouvert=ouvert)
                )
                for stream_lines, viewer in zip(lines, EVERY_VIEWER, strict=True):
                    allowed = wire_cards(visible_cards(KNOWN_DEAL, script[:count], viewer.position, ouvert=ouvert))
                    assert cards_in_text(message_at_version(stream_lines, version)) == allowed
                    assert cards_in_text(read(table, viewer.headers_at(table))) == allowed
