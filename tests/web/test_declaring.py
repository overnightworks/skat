import itertools

import pytest

from skat.engine.cards import DECK
from skat.engine.deal import Position, positions_from
from skat.engine.declaration import Announcement, Declaration, DeclarationRefusal, Declare, PutBack, TakeSkat
from skat.engine.games import GameKind
from skat.table.auction import AuctionAction
from skat.table.hand_state import declaring_of
from skat.table.records import Refusal
from skat.web.auction import TABLE_AUCTION_SUFFIX
from skat.web.declaring import TABLE_DECLARATION_SUFFIX, AnnouncementToken, DeclaringAction, GameToken
from skat.web.tables import RANK_TOKENS, SUIT_TOKENS, TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT, KNOWN_DEAL, MIDDLEHAND_CARDS, SKAT_CARDS, seated_three
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import FETCH, UNKNOWN_ID

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND


def card_body(card):
    return {"suit": SUIT_TOKENS[card.suit], "rank": RANK_TOKENS[card.rank]}


def cards_body(*cards):
    return {"cards": [card_body(card) for card in cards]}


def declared_body(game=GameToken.HERZ, *, hand=False, ouvert=False, announcement=AnnouncementToken.NONE):
    return {"game": game, "hand": hand, "ouvert": ouvert, "announcement": announcement}


def two_of_the_twelve():
    return cards_body(MIDDLEHAND_CARDS[0], MIDDLEHAND_CARDS[1])


def any_declaration():
    return declared_body()


def hand_declaration():
    return declared_body(hand=True)


def post_declaring(skat, headers, table_id, *, command_id, version, action, **fields):
    return skat.client.post(
        f"{TABLES_PATH}/{table_id}{TABLE_DECLARATION_SUFFIX}",
        json={"command_id": command_id, "version": version, "action": action, **fields},
        headers={"origin": TEST_PUBLIC_ORIGIN, **headers},
    )


def reason_of(answer):
    return answer.json()["reason"]


class Table:
    """A dealt table with its people told apart by position, and the watcher left over."""

    def __init__(self, skat):
        self.skat = skat
        self.table_id, people = seated_three(skat)
        by_seat = {seat: people[seat - 1][0] for seat in (1, 2, 3)}
        self.at = {position: by_seat[seat] for seat, position in positions_from(DEALER_SEAT).items()}
        self.watcher = people[3][0]
        self._commands = itertools.count(1)
        self.same_command = "command-same"

    @property
    def record(self):
        return self.skat.store.tables[self.table_id]

    @property
    def steps(self):
        return self.record.progress.declaring

    @property
    def declaration(self):
        return declaring_of(self.record).declaration

    def fresh_id(self):
        return f"step-{next(self._commands):04d}"

    def auction_step(self, position, action, value=None):
        fields = {} if value is None else {"value": value}
        answer = self.skat.client.post(
            f"{TABLES_PATH}/{self.table_id}{TABLE_AUCTION_SUFFIX}",
            json={"command_id": self.fresh_id(), "version": self.record.version, "action": action, **fields},
            headers={"origin": TEST_PUBLIC_ORIGIN, **self.at[position]},
        )
        assert answer.status_code == 200, answer.text

    def middlehand_wins_at(self, value):
        self.auction_step(MIDDLEHAND, AuctionAction.BID, value)
        self.auction_step(FOREHAND, AuctionAction.PASS)
        self.auction_step(REARHAND, AuctionAction.PASS)

    def send(self, headers, action, *, command_id=None, version=None, **fields):
        return post_declaring(
            self.skat,
            headers,
            self.table_id,
            command_id=command_id or self.fresh_id(),
            version=self.record.version if version is None else version,
            action=action,
            **fields,
        )

    def accepted(self, action, **fields):
        before = self.record
        answer = self.send(self.at[MIDDLEHAND], action, **fields)
        assert answer.status_code == 200, answer.text
        assert self.record.version == before.version + 1
        assert len(self.steps) == len(before.progress.declaring) + 1
        return answer

    def refused(self, headers, action, reason, **fields):
        before = self.record
        answer = self.send(headers, action, **fields)
        assert answer.status_code == 409, answer.text
        assert reason_of(answer) == reason
        assert self.record == before
        return answer

    def picked(self):
        self.accepted(DeclaringAction.TAKE)
        self.accepted(DeclaringAction.PUT_BACK, **two_of_the_twelve())


@pytest.fixture
def table(skat):
    return Table(skat)


@pytest.fixture
def won(table):
    table.middlehand_wins_at(20)
    return table


@pytest.fixture
def after_take(won):
    won.accepted(DeclaringAction.TAKE)
    return won


@pytest.fixture
def picked(won):
    won.picked()
    return won


class TestAccepted:
    def test_taking_the_skat_stores_a_step_and_raises_the_version(self, won):
        answer = won.accepted(DeclaringAction.TAKE)

        assert won.steps == (TakeSkat(),)
        assert answer.json()["version"] == won.record.version
        assert answer.headers["cache-control"] == "no-store"

    def test_putting_back_two_of_the_twelve_leaves_the_dealt_hand_as_dealt(self, after_take):
        after_take.accepted(DeclaringAction.PUT_BACK, **cards_body(SKAT_CARDS[0], MIDDLEHAND_CARDS[0]))

        assert after_take.steps == (TakeSkat(), PutBack((SKAT_CARDS[0], MIDDLEHAND_CARDS[0])))
        assert after_take.record.hand == KNOWN_DEAL

    def test_the_declarer_names_the_game_after_putting_back(self, picked):
        picked.accepted(DeclaringAction.DECLARE, **any_declaration())

        assert picked.declaration == Declaration(
            GameKind.HERZ, hand=False, ouvert=False, announcement=Announcement.NONE
        )

    def test_a_hand_game_is_declared_without_taking_the_skat(self, won):
        won.accepted(DeclaringAction.DECLARE, **hand_declaration())

        assert won.steps == (Declare(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE),)
        assert won.declaration == Declaration(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE)

    def test_null_ouvert_may_be_declared_after_taking_the_skat(self, picked):
        picked.accepted(DeclaringAction.DECLARE, **declared_body(GameToken.NULL, ouvert=True))

        assert picked.declaration == Declaration(GameKind.NULL, hand=False, ouvert=True, announcement=Announcement.NONE)

    def test_a_null_below_the_bid_is_accepted_after_a_bid_of_twenty_four(self, table):
        table.middlehand_wins_at(24)
        table.picked()

        table.accepted(DeclaringAction.DECLARE, **declared_body(GameToken.NULL))

        assert table.declaration == Declaration(GameKind.NULL, hand=False, ouvert=False, announcement=Announcement.NONE)


class TestRefusedByTheEngine:
    @pytest.mark.parametrize(
        ("arrangement", "action", "fields", "reason"),
        [
            pytest.param(
                "won",
                DeclaringAction.PUT_BACK,
                two_of_the_twelve(),
                DeclarationRefusal.OUT_OF_ORDER,
                id="put-back-before-take",
            ),
            pytest.param(
                "won",
                DeclaringAction.DECLARE,
                any_declaration(),
                DeclarationRefusal.OUT_OF_ORDER,
                id="declare-without-hand",
            ),
            pytest.param("after_take", DeclaringAction.TAKE, {}, DeclarationRefusal.OUT_OF_ORDER, id="take-twice"),
            pytest.param(
                "after_take",
                DeclaringAction.DECLARE,
                hand_declaration(),
                DeclarationRefusal.OUT_OF_ORDER,
                id="declare-holding-twelve",
            ),
            pytest.param(
                "after_take",
                DeclaringAction.PUT_BACK,
                cards_body(DECK[0], MIDDLEHAND_CARDS[0]),
                DeclarationRefusal.NOT_TWO_OF_THE_TWELVE,
                id="card-outside-the-twelve",
            ),
            pytest.param(
                "after_take",
                DeclaringAction.PUT_BACK,
                cards_body(MIDDLEHAND_CARDS[0], MIDDLEHAND_CARDS[0]),
                DeclarationRefusal.NOT_TWO_OF_THE_TWELVE,
                id="same-card-twice",
            ),
            pytest.param(
                "picked",
                DeclaringAction.DECLARE,
                hand_declaration(),
                DeclarationRefusal.LEVEL_NOT_ALLOWED_AFTER_PICK_UP,
                id="hand-after-pick-up",
            ),
            pytest.param(
                "picked",
                DeclaringAction.DECLARE,
                declared_body(announcement=AnnouncementToken.SCHNEIDER),
                DeclarationRefusal.LEVEL_NOT_ALLOWED_AFTER_PICK_UP,
                id="announcement-after-pick-up",
            ),
            pytest.param(
                "picked",
                DeclaringAction.DECLARE,
                declared_body(ouvert=True),
                DeclarationRefusal.LEVEL_NOT_ALLOWED_AFTER_PICK_UP,
                id="ouvert-suit-after-pick-up",
            ),
            pytest.param(
                "won",
                DeclaringAction.DECLARE,
                declared_body(GameToken.NULL, hand=True, announcement=AnnouncementToken.SCHNEIDER),
                DeclarationRefusal.ANNOUNCEMENT_IN_NULL,
                id="null-hand-with-an-announcement",
            ),
        ],
    )
    def test_the_rules_refuse_the_step_by_name(self, request, arrangement, action, fields, reason):
        table = request.getfixturevalue(arrangement)

        table.refused(table.at[MIDDLEHAND], action, reason, **fields)

    @pytest.mark.parametrize(
        ("action", "fields"),
        [
            pytest.param(DeclaringAction.TAKE, {}, id="take"),
            pytest.param(DeclaringAction.PUT_BACK, two_of_the_twelve(), id="put-back"),
            pytest.param(DeclaringAction.DECLARE, hand_declaration(), id="declare"),
        ],
    )
    def test_once_declared_every_step_is_already_declared(self, won, action, fields):
        won.accepted(DeclaringAction.DECLARE, **hand_declaration())

        won.refused(won.at[MIDDLEHAND], action, DeclarationRefusal.ALREADY_DECLARED, **fields)


class TestRefusedByTheTable:
    def test_an_opponent_is_not_the_declarer(self, won):
        won.refused(won.at[FOREHAND], DeclaringAction.TAKE, Refusal.NOT_DECLARER)

    def test_a_watcher_is_not_seated(self, won):
        won.refused(won.watcher, DeclaringAction.TAKE, Refusal.NOT_SEATED)

    def test_during_the_auction_the_step_is_the_wrong_phase(self, table):
        table.refused(table.at[MIDDLEHAND], DeclaringAction.TAKE, Refusal.WRONG_PHASE)

    def test_a_passed_in_hand_has_no_declarer(self, table):
        table.auction_step(MIDDLEHAND, AuctionAction.PASS)
        table.auction_step(REARHAND, AuctionAction.PASS)
        table.auction_step(FOREHAND, AuctionAction.PASS)

        table.refused(table.at[FOREHAND], DeclaringAction.TAKE, Refusal.WRONG_PHASE)

    def test_a_table_without_a_hand_has_none_to_declare(self, skat):
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]

        answer = post_declaring(skat, headers, table_id, command_id="step-0001", version=1, action=DeclaringAction.TAKE)

        assert reason_of(answer) == Refusal.NO_HAND

    def test_no_hand_is_named_before_not_seated_and_a_stale_version(self, skat):
        opener, _ = skat.member()
        outsider, _ = skat.member()
        table_id = skat.create(opener).json()["id"]

        answer = post_declaring(
            skat, outsider, table_id, command_id="step-0001", version=0, action=DeclaringAction.TAKE
        )

        assert reason_of(answer) == Refusal.NO_HAND

    def test_not_seated_is_named_before_a_stale_version(self, won):
        won.refused(won.watcher, DeclaringAction.TAKE, Refusal.NOT_SEATED, version=won.record.version - 1)

    def test_a_stale_version_is_named_before_the_wrong_phase(self, table):
        table.auction_step(MIDDLEHAND, AuctionAction.BID, 18)

        table.refused(
            table.at[MIDDLEHAND], DeclaringAction.TAKE, Refusal.STALE_VERSION, version=table.record.version - 1
        )

    def test_the_wrong_phase_is_named_before_not_the_declarer(self, table):
        table.refused(table.at[REARHAND], DeclaringAction.TAKE, Refusal.WRONG_PHASE)

    def test_not_the_declarer_is_named_before_the_engines_reason(self, won):
        won.refused(won.at[FOREHAND], DeclaringAction.PUT_BACK, Refusal.NOT_DECLARER, **two_of_the_twelve())


class TestContract:
    @pytest.mark.parametrize(
        ("action", "fields"),
        [
            pytest.param(DeclaringAction.PUT_BACK, cards_body(MIDDLEHAND_CARDS[0]), id="one-card"),
            pytest.param(DeclaringAction.PUT_BACK, cards_body(*MIDDLEHAND_CARDS[:3]), id="three-cards"),
            pytest.param(DeclaringAction.PUT_BACK, {}, id="no-cards"),
            pytest.param(
                DeclaringAction.PUT_BACK,
                {"cards": [{"suit": "lila", "rank": "ace"}, card_body(MIDDLEHAND_CARDS[0])]},
                id="unknown-suit",
            ),
            pytest.param(
                DeclaringAction.PUT_BACK,
                {"cards": [{**card_body(MIDDLEHAND_CARDS[0]), "seat": 1}, card_body(MIDDLEHAND_CARDS[1])]},
                id="a-card-with-a-foreign-field",
            ),
            pytest.param(DeclaringAction.TAKE, {"seat": 1}, id="names-a-seat"),
            pytest.param(DeclaringAction.TAKE, {"position": "forehand"}, id="names-a-position"),
            pytest.param(DeclaringAction.PUT_BACK, {**two_of_the_twelve(), "game": "herz"}, id="foreign-field"),
            pytest.param(DeclaringAction.DECLARE, {**any_declaration(), "cards": []}, id="cards-on-declare"),
            pytest.param(DeclaringAction.DECLARE, {"game": "herz"}, id="missing-declaration-fields"),
            pytest.param(DeclaringAction.DECLARE, {**any_declaration(), "game": "ramsch"}, id="unknown-game"),
            pytest.param(
                DeclaringAction.DECLARE, {**any_declaration(), "announcement": "kontra"}, id="unknown-announcement"
            ),
            pytest.param(DeclaringAction.DECLARE, {**any_declaration(), "hand": "yes"}, id="hand-not-a-boolean"),
            pytest.param("reject", {}, id="unknown-action"),
        ],
    )
    def test_a_body_that_breaks_the_contract_is_refused_and_stores_nothing(self, won, action, fields):
        before = won.record

        answer = won.send(won.at[MIDDLEHAND], action, **fields)

        assert answer.status_code == 422
        assert won.record == before

    def test_an_unknown_table_answers_404(self, skat):
        headers, _ = skat.member()

        answer = post_declaring(
            skat, headers, UNKNOWN_ID, command_id="step-0001", version=1, action=DeclaringAction.TAKE
        )

        assert answer.status_code == 404

    def test_signed_out_is_refused_and_changes_nothing(self, won):
        before = won.record

        answer = won.send(FETCH, DeclaringAction.TAKE)

        assert answer.status_code == 401
        assert won.record == before


class TestRetry:
    def test_a_repeated_acceptance_answers_the_same_and_changes_nothing(self, won):
        version = won.record.version
        first = won.send(won.at[MIDDLEHAND], DeclaringAction.TAKE, command_id=won.same_command, version=version)
        after_first = won.record

        again = won.send(won.at[MIDDLEHAND], DeclaringAction.TAKE, command_id=won.same_command, version=version)

        assert again.status_code == 200
        assert again.json() == first.json()
        assert won.record == after_first

    def test_a_repeated_refusal_answers_the_same_refusal(self, won):
        first = won.refused(
            won.at[MIDDLEHAND],
            DeclaringAction.PUT_BACK,
            DeclarationRefusal.OUT_OF_ORDER,
            command_id=won.same_command,
            **two_of_the_twelve(),
        )

        again = won.refused(
            won.at[MIDDLEHAND],
            DeclaringAction.PUT_BACK,
            DeclarationRefusal.OUT_OF_ORDER,
            command_id=won.same_command,
            **two_of_the_twelve(),
        )

        assert again.json() == first.json()

    @pytest.mark.parametrize(
        ("action", "fields"),
        [
            pytest.param(DeclaringAction.DECLARE, declared_body(GameToken.PIK), id="another-game"),
            pytest.param(DeclaringAction.DECLARE, declared_body(hand=True), id="another-hand-flag"),
            pytest.param(DeclaringAction.DECLARE, declared_body(ouvert=True), id="another-ouvert-flag"),
            pytest.param(
                DeclaringAction.DECLARE,
                declared_body(announcement=AnnouncementToken.SCHWARZ),
                id="another-announcement",
            ),
            pytest.param(DeclaringAction.TAKE, {}, id="another-action"),
        ],
    )
    def test_the_same_id_with_another_body_is_refused_as_reused(self, picked, action, fields):
        version = picked.record.version
        picked.accepted(DeclaringAction.DECLARE, command_id=picked.same_command, version=version, **any_declaration())
        after_first = picked.record

        answer = picked.send(picked.at[MIDDLEHAND], action, command_id=picked.same_command, version=version, **fields)

        assert answer.status_code == 409
        assert "reused" in answer.json()["detail"]
        assert picked.record == after_first

    def test_the_same_id_with_other_cards_is_refused_as_reused(self, after_take):
        version = after_take.record.version
        after_take.accepted(
            DeclaringAction.PUT_BACK, command_id=after_take.same_command, version=version, **two_of_the_twelve()
        )

        answer = after_take.send(
            after_take.at[MIDDLEHAND],
            DeclaringAction.PUT_BACK,
            command_id=after_take.same_command,
            version=version,
            **cards_body(SKAT_CARDS[0], SKAT_CARDS[1]),
        )

        assert answer.status_code == 409

    def test_a_fresh_id_with_the_old_version_is_stale(self, won):
        old_version = won.record.version
        won.accepted(DeclaringAction.TAKE)

        won.refused(
            won.at[MIDDLEHAND],
            DeclaringAction.PUT_BACK,
            Refusal.STALE_VERSION,
            version=old_version,
            **two_of_the_twelve(),
        )

    def test_a_retry_with_its_old_version_is_the_replay_not_stale(self, won):
        old_version = won.record.version
        won.accepted(DeclaringAction.TAKE, command_id=won.same_command, version=old_version)
        won.accepted(DeclaringAction.PUT_BACK, **two_of_the_twelve())
        after_steps = won.record

        again = won.send(won.at[MIDDLEHAND], DeclaringAction.TAKE, command_id=won.same_command, version=old_version)

        assert again.status_code == 200
        assert won.record == after_steps
