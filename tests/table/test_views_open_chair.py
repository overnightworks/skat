"""The views of a hand that waits for a sitter say so and offer no step, to every viewer alike."""

from dataclasses import replace

import pytest

from skat.engine.kontra import Word
from skat.table.records import HandProgress
from skat.table.rules import decide_sit
from skat.table.views import turn_seat_of, view_of
from tests.support.open_chairs import (
    FOREHAND_SEAT,
    KONTRA,
    MIDDLEHAND_SEAT,
    PHASES,
    REARHAND_SEAT,
    newcomer,
    sent_away,
)
from tests.support.played_game import declared_herz_hand, table_in

NOBODY = frozenset[str]()
VIEWERS = ("account-middlehand", "account-rearhand", "account-forehand", "account-watcher")


def a_seat_off_turn(table):
    turn = turn_seat_of(view_of(table, "account-watcher", NOBODY).hand)
    return next(seat for seat in (MIDDLEHAND_SEAT, REARHAND_SEAT, FOREHAND_SEAT) if seat != turn)


class TestTheWaitingSeat:
    @pytest.mark.parametrize("phase", PHASES)
    def test_names_the_open_seat_the_same_for_every_viewer(self, phase):
        table = sent_away(PHASES[phase](), REARHAND_SEAT)

        assert {view_of(table, viewer, NOBODY).hand.waiting_seat for viewer in VIEWERS} == {REARHAND_SEAT}

    @pytest.mark.parametrize("phase", ["pushing-start", "pushing-after-the-take", "pushing-after-the-push"])
    @pytest.mark.parametrize("viewer", VIEWERS)
    def test_names_the_open_seat_beside_the_stage_and_its_pushes_which_stay_facts_of_the_hand(self, phase, viewer):
        running = PHASES[phase]()
        waiting = sent_away(running, REARHAND_SEAT)

        before = view_of(running, viewer, NOBODY).hand
        after = view_of(waiting, viewer, NOBODY).hand

        assert before.pushing is not None
        assert (after.waiting_seat, after.pushing, after.pushes) == (REARHAND_SEAT, before.pushing, before.pushes)

    def test_names_the_lowest_of_two_open_seats(self):
        table = sent_away(sent_away(PHASES["auction"](), FOREHAND_SEAT), REARHAND_SEAT)

        assert view_of(table, account_of_a_seated_person(table), NOBODY).hand.waiting_seat == REARHAND_SEAT

    @pytest.mark.parametrize("phase", PHASES)
    def test_names_none_when_every_chair_is_taken(self, phase):
        assert view_of(PHASES[phase](), "account-middlehand", NOBODY).hand.waiting_seat is None

    def test_names_none_once_a_sitter_fills_the_chair(self):
        table = sent_away(PHASES["auction"](), REARHAND_SEAT)
        taken = decide_sit(table, newcomer(), REARHAND_SEAT, None).table

        assert view_of(taken, newcomer().account_id, NOBODY).hand.waiting_seat is None

    def test_has_no_hand_between_hands(self):
        between = replace(table_in(HandProgress()), hand=None, dealer=None)

        assert view_of(between, "account-middlehand", NOBODY).hand is None

    def test_shows_the_open_chair_with_no_name_and_its_part_of_the_hand(self):
        table = sent_away(PHASES["auction"](), REARHAND_SEAT)

        chair = view_of(table, "account-middlehand", NOBODY).chairs[REARHAND_SEAT - 1]

        assert (chair.occupant_name, chair.occupant_kind) == (None, None)
        assert chair.hand is not None

    def test_gives_a_watcher_no_card(self):
        table = sent_away(PHASES["after-the-take"](), MIDDLEHAND_SEAT)

        assert view_of(table, "account-watcher", NOBODY).hand.own_cards == ()


class TestTheFormerHolder:
    @pytest.mark.parametrize("phase", PHASES)
    def test_every_viewer_reads_the_leavers_name_on_the_open_chair_and_none_elsewhere(self, phase):
        running = PHASES[phase]()
        waiting = sent_away(running, REARHAND_SEAT)
        leaver = running.chairs[REARHAND_SEAT - 1].occupant.display_name

        for viewer in VIEWERS:
            names = [chair.former_holder_name for chair in view_of(waiting, viewer, NOBODY).chairs]
            assert names == [None, leaver, None]

    def test_a_sit_leaves_no_name_for_any_viewer(self):
        table = sent_away(PHASES["auction"](), REARHAND_SEAT)
        taken = decide_sit(table, newcomer(), REARHAND_SEAT, None).table

        assert {chair.former_holder_name for viewer in VIEWERS for chair in view_of(taken, viewer, NOBODY).chairs} == {
            None
        }

    def test_a_chair_stored_with_no_name_reads_none_though_it_is_open(self):
        table = sent_away(PHASES["auction"](), REARHAND_SEAT)
        stored = replace(table, progress=replace(table.progress, former_holders=frozenset()))

        assert view_of(stored, "account-watcher", NOBODY).chairs[REARHAND_SEAT - 1].former_holder_name is None


def account_of_a_seated_person(table):
    return next(chair.occupant.account_id for chair in table.chairs if chair.occupant is not None)


class TestNoStepIsOffered:
    @pytest.mark.parametrize("viewer", VIEWERS)
    def test_the_auction_lists_no_value_to_bid_for_anyone(self, viewer):
        running = table_in(HandProgress())
        waiting = sent_away(running, REARHAND_SEAT)

        assert view_of(running, "account-middlehand", NOBODY).hand.auction.values
        assert view_of(waiting, viewer, NOBODY).hand.auction.values == ()

    def test_the_player_on_turn_has_no_legal_card(self):
        running = PHASES["between-tricks"]()
        on_turn = account_of_seat(running, turn_seat_of(view_of(running, "account-watcher", NOBODY).hand))
        waiting = sent_away(running, a_seat_off_turn(running))

        assert view_of(running, on_turn, NOBODY).hand.playing.legal_cards
        assert view_of(waiting, on_turn, NOBODY).hand.playing.legal_cards == ()

    def test_an_opponent_has_no_kontra_word_to_say(self):
        running = table_in(declared_herz_hand(), KONTRA)
        opponent = account_of_seat(running, FOREHAND_SEAT)
        waiting = sent_away(running, REARHAND_SEAT)

        assert view_of(running, opponent, NOBODY).hand.playing.kontra.my_word is Word.KONTRA
        assert view_of(waiting, opponent, NOBODY).hand.playing.kontra.my_word is None

    @pytest.mark.parametrize("phase", ["between-tricks", "in-a-ramsch-trick"])
    def test_the_turn_and_the_trick_stay_facts_of_the_hand(self, phase):
        running = PHASES[phase]()
        waiting = sent_away(running, REARHAND_SEAT)

        before = view_of(running, "account-watcher", NOBODY).hand.playing
        after = view_of(waiting, "account-watcher", NOBODY).hand.playing

        assert (after.turn_seat, after.current_trick, after.last_trick) == (
            before.turn_seat,
            before.current_trick,
            before.last_trick,
        )


def account_of_seat(table, seat):
    return table.chairs[seat - 1].occupant.account_id
