from dataclasses import replace

import pytest

from skat.engine.bidding import Bid
from skat.engine.bock import BockRounds
from skat.engine.cards import DECK
from skat.engine.deal import Deal, Position, positions_from
from skat.engine.declaration import TakeSkat
from skat.engine.tricks import CardPlayed, PlayRefusal
from skat.table.hand_state import playing_of
from skat.table.playing import PlayCardCommand, card_payload, decide_card
from skat.table.records import (
    Actor,
    Chair,
    HandProgress,
    Occupant,
    Refusal,
    TableId,
    TableOptions,
    TableRecord,
    parsed_refusal,
)
from tests.support.played_game import before_the_last_card, declared_herz_hand

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
TABLE_VERSION = 7
FOREHAND_ACCOUNT = "account-forehand"
CARDS_IN_A_GAME = 30


def table_id():
    return "0123456789abcdef0123456789abcdef"


def actor(account_id):
    return Actor(account_id=account_id, display_name="Anna")


def table_in(progress):
    dealer = 2
    seats = {position: seat for seat, position in positions_from(dealer).items()}
    chairs = tuple(
        Chair(seats[position], Occupant(f"account-{position.name.lower()}", position.name))
        for position in (MIDDLEHAND, REARHAND, FOREHAND)
    )
    deal = Deal(forehand=DECK[0:10], middlehand=DECK[10:20], rearhand=DECK[20:30], skat=DECK[30:32])
    return TableRecord(
        id=TableId(table_id()),
        version=TABLE_VERSION,
        chairs=chairs,
        dealer=dealer,
        hand=deal,
        progress=progress,
        game_list=(),
        series=None,
        options=TableOptions(),
        bock=BockRounds.start(),
    )


def command_with(card, version=TABLE_VERSION):
    return PlayCardCommand(command_id="command-1", table_id=table_id(), version=version, card=card)


class TestPlayingOf:
    def test_no_hand_has_no_tricks(self):
        handless = replace(table_in(HandProgress()), hand=None, dealer=None)

        assert playing_of(handless) is None

    def test_a_running_auction_has_no_tricks(self):
        assert playing_of(table_in(HandProgress(auction=(Bid(MIDDLEHAND, 18),)))) is None

    def test_the_declarer_still_choosing_has_no_tricks(self):
        progress = replace(declared_herz_hand(), declaring=(TakeSkat(),))

        assert playing_of(table_in(progress)) is None

    def test_after_the_declaration_forehand_leads_and_no_card_is_played(self):
        state = playing_of(table_in(declared_herz_hand()))

        assert state.turn is FOREHAND
        assert state.tricks == ()
        assert state.current == ()

    def test_the_stored_cards_are_replayed_through_the_engine(self):
        progress = replace(declared_herz_hand(), plays=(CardPlayed(FOREHAND, DECK[8]),))

        state = playing_of(table_in(progress))

        assert state.current == (DECK[8],)
        assert state.turn is MIDDLEHAND
        assert DECK[8] not in state.hands[FOREHAND]

    def test_a_stored_log_the_rules_refuse_raises(self):
        corrupt = table_in(replace(declared_herz_hand(), plays=(CardPlayed(REARHAND, DECK[20]),)))

        with pytest.raises(ValueError, match="impossible card log"):
            playing_of(corrupt)


class TestCardPayload:
    @pytest.mark.parametrize(
        "other",
        [
            pytest.param(command_with(DECK[0], version=TABLE_VERSION + 1), id="another-version"),
            pytest.param(command_with(DECK[1]), id="another-card"),
            pytest.param(replace(command_with(DECK[0]), table_id="f" * 32), id="another-table"),
        ],
    )
    def test_each_request_has_its_own_payload(self, other):
        assert card_payload(other) != card_payload(command_with(DECK[0]))


class TestDecide:
    def test_no_hand_is_named_before_not_seated_and_a_stale_version(self):
        handless = replace(table_in(HandProgress()), hand=None, dealer=None)

        decision = decide_card(handless, actor("account-outsider"), command_with(DECK[0], version=1))

        assert decision.refusal is Refusal.NO_HAND

    def test_not_seated_is_named_before_a_stale_version(self):
        decision = decide_card(
            table_in(declared_herz_hand()), actor("account-outsider"), command_with(DECK[0], version=1)
        )

        assert decision.refusal is Refusal.NOT_SEATED

    def test_a_stale_version_is_named_before_the_wrong_phase(self):
        running = table_in(HandProgress(auction=(Bid(MIDDLEHAND, 18),)))

        decision = decide_card(running, actor(FOREHAND_ACCOUNT), command_with(DECK[0], version=1))

        assert decision.refusal is Refusal.STALE_VERSION

    def test_the_wrong_phase_is_named_before_the_engine_is_asked(self):
        running = table_in(HandProgress(auction=(Bid(MIDDLEHAND, 18),)))

        decision = decide_card(running, actor(FOREHAND_ACCOUNT), command_with(DECK[31]))

        assert decision.refusal is Refusal.WRONG_PHASE

    def test_the_position_comes_from_the_chair_and_the_dealer(self):
        table = table_in(declared_herz_hand())

        decision = decide_card(table, actor(FOREHAND_ACCOUNT), command_with(DECK[8]))

        assert decision.table.progress.plays == (CardPlayed(FOREHAND, DECK[8]),)

    def test_an_accepted_card_is_appended_and_raises_the_version_and_keeps_the_deal(self):
        table = table_in(declared_herz_hand())

        decision = decide_card(table, actor(FOREHAND_ACCOUNT), command_with(DECK[8]))

        assert decision.refusal is None
        assert decision.table.version == table.version + 1
        assert decision.table.hand == table.hand

    def test_a_refused_card_leaves_the_table_as_it_was(self):
        table = table_in(declared_herz_hand())

        decision = decide_card(table, actor("account-middlehand"), command_with(DECK[10]))

        assert decision.refusal is PlayRefusal.NOT_YOUR_TURN
        assert decision.table == table


def the_last_card_to_play():
    """A declared table holding every card but the last, and that last card's command and actor."""
    table, last = before_the_last_card(table_in(declared_herz_hand()))
    return table, actor(f"account-{last.position.name.lower()}"), command_with(last.card)


class TestTheLastCard:
    def test_a_card_before_the_thirtieth_writes_no_entry_and_the_hand_runs(self):
        table = table_in(declared_herz_hand())

        decision = decide_card(table, actor(FOREHAND_ACCOUNT), command_with(DECK[8]))

        assert decision.table.game_list == ()
        assert decision.table.hand == table.hand

    def test_the_thirtieth_card_ends_the_hand_with_one_entry_in_one_version_bump(self):
        table, last_actor, last_card = the_last_card_to_play()
        assert len(table.progress.plays) == CARDS_IN_A_GAME - 1

        decision = decide_card(table, last_actor, last_card)

        assert decision.refusal is None
        assert decision.table.hand is None
        assert decision.table.progress == HandProgress()
        assert len(decision.table.game_list) == 1
        assert decision.table.version == table.version + 1
        assert (decision.table.dealer, decision.table.chairs) == (table.dealer, table.chairs)

    def test_the_entry_names_the_seated_accounts_and_the_declarer_s_seat(self):
        table, last_actor, last_card = the_last_card_to_play()

        entry = decide_card(table, last_actor, last_card).table.game_list[0]

        assert entry.seat_accounts == tuple(chair.occupant.account_id for chair in table.chairs)
        assert positions_from(table.dealer)[entry.declarer_seat] is MIDDLEHAND

    def test_a_second_game_appends_its_entry_after_the_first_unchanged(self):
        table, last_actor, last_card = the_last_card_to_play()
        first = decide_card(table, last_actor, last_card).table.game_list[0]

        decision = decide_card(replace(table, game_list=(first,)), last_actor, last_card)

        assert decision.table.game_list[0] == first
        assert len(decision.table.game_list) == 2


class TestParsedRefusal:
    @pytest.mark.parametrize("refusal", [PlayRefusal.NOT_IN_HAND, PlayRefusal.MUST_FOLLOW], ids=str)
    def test_reads_the_play_tokens_back_to_their_own_enum(self, refusal):
        assert parsed_refusal(refusal.value) is refusal

    @pytest.mark.parametrize("refusal", list(PlayRefusal), ids=str)
    def test_every_play_token_keeps_its_wire_string(self, refusal):
        assert parsed_refusal(refusal.value).value == refusal.value
