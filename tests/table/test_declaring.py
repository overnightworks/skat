from dataclasses import replace

import pytest

from skat.engine.bidding import Bid, Pass
from skat.engine.cards import DECK
from skat.engine.deal import Deal, Position, positions_from
from skat.engine.declaration import Announcement, Declare, DeclarationRefusal, PutBack, TakeSkat
from skat.engine.games import GameKind
from skat.table.declaring import DeclaringCommand, declaring_payload, decide_declaring_step
from skat.table.hand_state import declaring_of
from skat.table.records import Actor, Chair, HandProgress, Occupant, Refusal, TableId, TableRecord, parsed_refusal

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
DEALER_SEAT = 2
TABLE_ID = "0123456789abcdef0123456789abcdef"
FIRST, SECOND, THIRD = DECK[10], DECK[11], DECK[12]
FOREHAND_ACCOUNT = "account-forehand"
HERZ_DECLARATION = Declare(GameKind.HERZ, hand=False, ouvert=False, announcement=Announcement.NONE)


def actor(account_id):
    return Actor(account_id=account_id, display_name="Anna")


def table_in(progress):
    seats = {position: seat for seat, position in positions_from(DEALER_SEAT).items()}
    chairs = tuple(
        Chair(seats[position], Occupant(f"account-{position.name.lower()}", position.name))
        for position in (MIDDLEHAND, REARHAND, FOREHAND)
    )
    deal = Deal(forehand=DECK[0:10], middlehand=DECK[10:20], rearhand=DECK[20:30], skat=DECK[30:32])
    return TableRecord(id=TableId(TABLE_ID), version=7, chairs=chairs, dealer=DEALER_SEAT, hand=deal, progress=progress)


WON = (Bid(MIDDLEHAND, 20), Pass(FOREHAND), Pass(REARHAND))


class TestDeclaringOf:
    def test_a_running_auction_has_no_declaring_state(self):
        assert declaring_of(table_in(HandProgress(auction=(Bid(MIDDLEHAND, 18),)))) is None

    def test_a_passed_in_hand_has_no_declaring_state(self):
        passed_in = (Pass(MIDDLEHAND), Pass(REARHAND), Pass(FOREHAND))

        assert declaring_of(table_in(HandProgress(auction=passed_in))) is None

    def test_the_stored_steps_are_replayed_from_the_winner_and_the_deal(self):
        progress = HandProgress(auction=WON, declaring=(TakeSkat(), PutBack((FIRST, SECOND))))

        state = declaring_of(table_in(progress))

        assert state.declarer is MIDDLEHAND
        assert state.bid == 20
        assert set(state.hand) == set(DECK[12:20]) | set(DECK[30:32])
        assert state.skat == (FIRST, SECOND)

    def test_a_stored_log_the_rules_refuse_raises(self):
        corrupt = table_in(HandProgress(auction=WON, declaring=(PutBack((FIRST, SECOND)),)))

        with pytest.raises(ValueError, match="impossible declaring log"):
            declaring_of(corrupt)


def command_with(step, version=7):
    return DeclaringCommand(command_id="command-1", table_id=TABLE_ID, version=version, step=step)


class TestDeclaringPayload:
    @pytest.mark.parametrize(
        "other",
        [
            pytest.param(command_with(TakeSkat(), version=8), id="another-version"),
            pytest.param(command_with(PutBack((FIRST, SECOND))), id="put-back"),
            pytest.param(command_with(HERZ_DECLARATION), id="declare"),
        ],
    )
    def test_each_request_has_its_own_payload(self, other):
        assert declaring_payload(other) != declaring_payload(command_with(TakeSkat()))

    @pytest.mark.parametrize(
        "other",
        [
            pytest.param(PutBack((FIRST, THIRD)), id="another-second-card"),
            pytest.param(PutBack((THIRD, SECOND)), id="another-first-card"),
        ],
    )
    def test_other_cards_are_another_request(self, other):
        assert declaring_payload(command_with(other)) != declaring_payload(command_with(PutBack((FIRST, SECOND))))

    @pytest.mark.parametrize(
        "changed",
        [
            pytest.param({"kind": GameKind.PIK}, id="game"),
            pytest.param({"hand": True}, id="hand"),
            pytest.param({"ouvert": True}, id="ouvert"),
            pytest.param({"announcement": Announcement.SCHNEIDER}, id="announcement"),
        ],
    )
    def test_each_field_of_a_declaration_is_part_of_the_request(self, changed):
        other = replace(HERZ_DECLARATION, **changed)

        assert declaring_payload(command_with(other)) != declaring_payload(command_with(HERZ_DECLARATION))

    def test_a_repeated_request_has_the_same_payload(self):
        assert declaring_payload(command_with(HERZ_DECLARATION)) == declaring_payload(command_with(HERZ_DECLARATION))


class TestDecide:
    def test_an_accepted_step_is_appended_and_raises_the_version(self):
        table = table_in(HandProgress(auction=WON))
        decision = decide_declaring_step(table, actor("account-middlehand"), command_with(TakeSkat()))

        assert decision.refusal is None
        assert decision.table.progress.declaring == (TakeSkat(),)
        assert decision.table.version == table.version + 1
        assert decision.table.hand == table.hand

    def test_a_refused_step_leaves_the_table_as_it_was(self):
        table = table_in(HandProgress(auction=WON))

        decision = decide_declaring_step(table, actor(FOREHAND_ACCOUNT), command_with(TakeSkat()))

        assert decision.refusal is Refusal.NOT_DECLARER
        assert decision.table == table


class TestParsedRefusal:
    @pytest.mark.parametrize("refusal", [*DeclarationRefusal, Refusal.WRONG_PHASE, Refusal.NOT_DECLARER], ids=str)
    def test_reads_the_declaring_tokens_back_to_their_own_enum(self, refusal):
        assert parsed_refusal(refusal.value) is refusal
