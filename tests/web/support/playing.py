import itertools
from dataclasses import replace

from skat.engine.bock import BockRounds
from skat.engine.cards import Card, Rank, Suit
from skat.engine.deal import Deal, Position, positions_from
from skat.web.auction import TABLE_AUCTION_BID_SUFFIX, TABLE_AUCTION_PASS_SUFFIX
from skat.web.declaring import (
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
    AnnouncementToken,
    GameToken,
)
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS, TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, seated_three
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
# Middlehand declares in every played-out game; seats 1, 2, 3 are middlehand, rearhand, forehand.
DECLARER_SEAT = 1


def card(text):
    """A card from a suit letter (C, S, H, D) and a rank letter (7, 8, 9, T, J, Q, K, A)."""
    suits = {"C": Suit.KREUZ, "S": Suit.PIK, "H": Suit.HERZ, "D": Suit.KARO}
    ranks = (Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE)
    return Card(suits[text[0]], dict(zip("789TJQKA", ranks, strict=True))[text[1]])


def cards(text):
    return tuple(card(each) for each in text.split())


def card_body(played):
    return {"suit": SUIT_TOKENS[played.suit], "rank": RANK_TOKENS[played.rank]}


def game_of(*halves):
    """Every card of a game in the order it is played, read from strings of tricks parted by slashes."""
    return tuple(each for half in halves for trick in half.split("/") for each in cards(trick))


# Middlehand's Herz Hand game against the known deal, played to its tenth trick: the declarer takes 55 trick points.
HERZ_GAME = game_of(
    "S7 S9 D7 / H7 DJ CJ / S8 ST D8 / SQ D9 C7 / SK DT C8",
    "SA DQ C9 / SJ HJ CT / H8 HQ CQ / HK CK H9 / HA CA HT",
)


def deal_of(forehand, middlehand, rearhand, skat):
    return Deal(forehand=cards(forehand), middlehand=cards(middlehand), rearhand=cards(rearhand), skat=cards(skat))


# Ramsch hands, each played by taking the first legal card in the deck's order; a trick lists its cards from the
# seat that led it.
# Rearhand takes tricks 1 to 4 (2, 3, 4, 21), 9 and 10 (17, 24): 71 points, the skat's DK and DA (15) go to him as
# the last trick's taker, forehand takes 12 and middlehand 5 + 3 + 14 = 22.
PLAIN_DEAL = deal_of(
    "C7 C8 C9 CT CJ CQ CK CA S7 S8", "S9 ST SJ SQ SK SA H7 H8 H9 HT", "HJ HQ HK HA D7 D8 D9 DT DJ DQ", "DK DA"
)
PLAIN_HAND = game_of(
    "C7 S9 HJ / HQ C8 H7 / HK C9 H8 / HA CT H9 / D7 CJ ST", "CQ SJ D8 / SQ D9 S7 / SK DT S8 / SA DJ CK / DQ CA HT"
)
# Forehand takes no trick: middlehand takes 86 and the skat's CA and SK (15) as the last trick's taker.
JUNGFRAU_DEAL = deal_of(
    "H7 D8 H9 H8 HK DJ SA S8 HQ HA", "DA DQ HJ SJ SQ DT C8 CQ D9 ST", "C7 CJ S9 D7 CK HT S7 DK C9 CT", "CA SK"
)
JUNGFRAU_HAND = game_of(
    "S8 ST S7 / C8 C7 SA / CQ C9 H7 / SJ CJ DJ / CT H8 SQ", "CK H9 HJ / D9 D7 D8 / DT DK HQ / DQ S9 HK / DA HT HA"
)
# Rearhand and middlehand take 41 each, forehand 34 and the skat's SK (4) as the last trick's taker.
TIE_DEAL = deal_of(
    "DJ D8 CQ ST SJ CJ HK DT C7 S9", "HQ CA DA HA C8 HT HJ S8 C9 S7", "DK H7 CK D9 CT D7 DQ SA SQ H8", "H9 SK"
)
TIE_HAND = game_of(
    "C7 C8 CT / CK CQ C9 / SQ S9 S7 / SA ST S8 / H7 HK HT", "CA H8 CJ / SJ HJ D7 / D8 DA D9 / HQ DQ DT / HA DK DJ"
)
# Forehand holds the four jacks and the aces and tens that win every trick: all 120 points but the skat's HT and HK.
SWEEP_DEAL = deal_of(
    "CJ SJ HJ DJ CA CT SA ST HA DA", "C7 C8 C9 S7 S8 H7 H8 D7 D8 D9", "CK CQ S9 SK SQ H9 HQ DT DK DQ", "HT HK"
)
SWEEP_HAND = game_of(
    "CT C7 CQ / CJ C8 CK / CA C9 S9 / ST S7 SQ / SJ S8 SK", "SA H7 H9 / HJ H8 HQ / HA D7 DT / DJ D8 DQ / DA D9 DK"
)


def takers(letters):
    """The position that takes each trick, from F, M and R in trick order."""
    return tuple({"F": FOREHAND, "M": MIDDLEHAND, "R": REARHAND}[letter] for letter in letters.split())


def points_of_cards(played):
    return sum(each.points for each in played)


def reason_of(answer):
    return answer.json()["reason"]


def result_fields(**changed):
    """A result answer for a plain first game of the declarer in seat 1; a test names what differs."""
    plain = {
        "kind": "declared",
        "ordinal": 1,
        "declarer_seat": DECLARER_SEAT,
        "hand": False,
        "ouvert": False,
        "announcement": "none",
        "schneider": False,
        "schwarz": False,
        "doubled": False,
        "overbid": False,
        "announcement_missed": False,
        "bid": 18,
        "kontra": None,
        "bock_factor": 1,
        "ending": "played-out",
        "ended_by_seat": None,
    }
    return plain | changed


def ending_of(result):
    return result["ending"], result["ended_by_seat"]


def gains(declarer, each_opponent):
    """The opponents gain only from a lost game, which is the declarer's loss."""
    declarer_won = each_opponent == 0
    return [
        {"seat": 1, "gain": declarer, "won": declarer_won},
        {"seat": 2, "gain": each_opponent, "won": not declarer_won},
        {"seat": 3, "gain": each_opponent, "won": not declarer_won},
    ]


class Table:
    """A dealt table with its people told apart by position, and the watcher left over."""

    def __init__(self, skat, options=None):
        self.skat = skat
        self.table_id, people = seated_three(skat, options)
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

    def read_as(self, headers):
        self.skat.client.cookies.clear()
        return self.skat.client.get(f"{TABLES_PATH}/{self.table_id}", headers=headers)

    def result(self):
        answer = self.read_as(self.watcher)
        assert answer.status_code == 200, answer.text
        return answer.json()["result"]

    def endings_in_every_view(self):
        """The ending and the seat that ended the game, as each of the three chairs and the watcher read them."""
        results = [self.read_as(headers).json()["result"] for headers in (self.watcher, *self.at.values())]
        return {(result["ending"], result["ended_by_seat"]) for result in results}

    def with_deal(self, deal):
        self.skat.store.tables[self.table_id] = replace(self.record, hand=deal)

    def _post(self, suffix, position, **body):
        answer = self.skat.client.post(
            f"{TABLES_PATH}/{self.table_id}{suffix}",
            json={"command_id": self.fresh_id(), "version": self.record.version, **body},
            headers={"origin": TEST_PUBLIC_ORIGIN, **self.at[position]},
        )
        assert answer.status_code == 200, answer.text

    def passes(self, position):
        self._post(TABLE_AUCTION_PASS_SUFFIX, position)

    def middlehand_bids(self, value=18):
        self._post(TABLE_AUCTION_BID_SUFFIX, MIDDLEHAND, value=value)

    def middlehand_wins(self, bid=18):
        self.middlehand_bids(bid)
        self.passes(FOREHAND)
        self.passes(REARHAND)

    def _declare(self, game, *, hand, ouvert=False, announcement=AnnouncementToken.NONE):
        self._post(
            TABLE_DECLARING_DECLARE_SUFFIX,
            MIDDLEHAND,
            game=game,
            hand=hand,
            ouvert=ouvert,
            announcement=announcement,
        )

    def declared_hand_game(self, game=GameToken.HERZ, *, bid=18, announcement=AnnouncementToken.NONE, ouvert=False):
        self.middlehand_wins(bid)
        self._declare(game, hand=True, ouvert=ouvert, announcement=announcement)

    def declared_grand_ouvert(self):
        self.middlehand_wins()
        self._declare(GameToken.GRAND, hand=True, ouvert=True, announcement=AnnouncementToken.SCHWARZ)

    def declared_after_putting_back(self, put_back, game=GameToken.HERZ, *, ouvert=False):
        self.middlehand_wins()
        self._post(TABLE_DECLARING_TAKE_SUFFIX, MIDDLEHAND)
        self._post(
            TABLE_DECLARING_PUT_BACK_SUFFIX,
            MIDDLEHAND,
            cards=[card_body(each) for each in put_back],
        )
        self._declare(game, hand=False, ouvert=ouvert)

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

    def act(self, suffix, headers=None, *, body=None):
        """An act without a payload of its own (a give-up, a throw-down), the declarer's unless told otherwise."""
        self.skat.client.cookies.clear()
        return self.skat.client.post(
            f"{TABLES_PATH}/{self.table_id}{suffix}",
            json={"command_id": self.fresh_id(), "version": self.record.version} | (body or {}),
            headers={"origin": TEST_PUBLIC_ORIGIN, **(headers or self.at[MIDDLEHAND])},
        )

    def refused_act(self, suffix, headers, reason, *, body=None):
        before = self.record
        answer = self.act(suffix, headers, body=body)
        assert answer.status_code == 409, answer.text
        assert reason_of(answer) == reason
        assert self.record == before

    def holder_of(self, played):
        """Whoever plays the card; a skat card the declarer kept is his."""
        if played in self.record.hand.skat:
            return MIDDLEHAND
        return next(position for position, held in self.record.hand.hands.items() if played in held)

    def accepted(self, played, *, command_id=None, version=None):
        before = self.record
        answer = self.send(self.at[self.holder_of(played)], played, command_id=command_id, version=version)
        assert answer.status_code == 200, answer.text
        assert self.record.version == before.version + 1
        stored = (len(self.plays), len(self.record.game_list))
        # The card is stored, or it ended the game: the hand's cards and steps go and the game joins the list.
        assert stored in {
            (len(before.progress.plays) + 1, len(before.game_list)),
            (0, len(before.game_list) + 1),
        }
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


def three_pass(table):
    for position in (MIDDLEHAND, REARHAND, FOREHAND):
        table.passes(position)


def with_pending(table, *rounds):
    table.skat.store.tables[table.table_id] = replace(table.record, bock=BockRounds(rounds))


def bock_of(table):
    return table.read_as(table.watcher).json()["bock"]
