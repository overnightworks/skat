from dataclasses import replace

import pytest

from skat.engine.bidding import Bid
from skat.engine.bock import BockRounds
from skat.engine.cards import DECK
from skat.engine.deal import Deal, Position, positions_from
from skat.engine.declaration import TakeSkat
from skat.engine.tricks import CARDS_IN_A_GAME, CardPlayed, PlayRefusal
from skat.table.awaiting import awaits_you
from skat.table.game_list import GameEnding
from skat.table.hand_state import playing_of
from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    GiveUpCommand,
    PlayCardCommand,
    card_payload,
    decide_agree_to_give_up,
    decide_card,
    decide_decline_give_up,
    decide_give_up,
)
from skat.table.records import (
    Actor,
    Chair,
    GiveUpAsked,
    HandProgress,
    Occupant,
    OccupantKind,
    Refusal,
    TableId,
    TableOptions,
    TableRecord,
    Visibility,
    parsed_refusal,
)
from skat.table.rules import decide_sit, decide_stand, waiting_seat_of
from skat.table.views import view_of
from tests.support.open_chairs import (
    HAND_COMMANDS,
    MIDDLEHAND_SEAT,
    REARHAND_SEAT,
    actor_at,
    hand_command,
    newcomer,
    sent_away,
)
from tests.support.played_game import (
    a_whole_game,
    asked_by_an_opponent,
    before_the_last_card,
    declared_herz_hand,
    with_agents,
)

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
TABLE_VERSION = 7
FOREHAND_ACCOUNT = "account-forehand"
# The dealer sits in seat 2, so forehand sits in seat 3.
FOREHAND_SEAT = 3


def table_id():
    return "0123456789abcdef0123456789abcdef"


def actor(account_id):
    return Actor(account_id=account_id, display_name="Anna")


def table_in(progress):
    dealer = 2
    seats = {position: seat for seat, position in positions_from(dealer).items()}
    chairs = tuple(
        Chair(seats[position], Occupant(f"account-{position.name.lower()}", position.name, OccupantKind.PERSON))
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
        visibility=Visibility.OPEN,
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


def after_two_tricks(request):
    """A declared table in which the declarer holds eight cards, with the request standing, if one is given."""
    table = table_in(declared_herz_hand())
    plays = a_whole_game(table)[:6]
    return replace(table, progress=replace(table.progress, plays=plays, give_up=request))


class TestTheEndingTheEntryRecords:
    def test_a_request_an_opponent_asked_names_the_asking_opponent(self):
        table = after_two_tricks(GiveUpAsked(FOREHAND))
        command = AgreeToGiveUpCommand("command-1", table_id(), TABLE_VERSION)

        entry = decide_agree_to_give_up(table, actor("account-middlehand"), command).table.game_list[0]

        assert (entry.ending, entry.ended_by_seat) == (GameEnding.GIVEN_UP, FOREHAND_SEAT)


class TestParsedRefusal:
    @pytest.mark.parametrize("refusal", [PlayRefusal.NOT_IN_HAND, PlayRefusal.MUST_FOLLOW], ids=str)
    def test_reads_the_play_tokens_back_to_their_own_enum(self, refusal):
        assert parsed_refusal(refusal.value) is refusal

    @pytest.mark.parametrize("refusal", list(PlayRefusal), ids=str)
    def test_every_play_token_keeps_its_wire_string(self, refusal):
        assert parsed_refusal(refusal.value).value == refusal.value


OPENINGS = pytest.mark.parametrize("opening", ["stand-up", "send-away"])
NOBODY = frozenset[str]()


def opened(table, seat, opening):
    """The table once the occupant of `seat` stood up, or the agent in it was sent away."""
    if opening == "send-away":
        return sent_away(table, seat)
    decision = decide_stand(table, actor_at(table, seat))
    assert decision.refusal is None
    return decision.table


def sat(table, sitter, seat):
    decision = decide_sit(table, sitter, seat, None)
    assert decision.refusal is None
    return decision.table


def decline_as(table, who):
    return decide_decline_give_up(table, who, DeclineGiveUpCommand("c", table.id.value, table.version)).table


class TestAnOpponentsGiveUpAndAChairThatOpens:
    @OPENINGS
    def test_the_askers_chair_takes_the_request_with_it_in_one_version_and_the_hand_waits_for_a_sitter(self, opening):
        table = asked_by_an_opponent(FOREHAND)

        freed = opened(table, FOREHAND_SEAT, opening)

        assert freed.progress.give_up is None
        assert (freed.version, waiting_seat_of(freed)) == (table.version + 1, FOREHAND_SEAT)

    @OPENINGS
    def test_a_sitter_in_the_askers_chair_plays_on_and_may_give_up_afresh(self, opening):
        sitter = newcomer()
        taken = sat(opened(asked_by_an_opponent(FOREHAND), FOREHAND_SEAT, opening), sitter, FOREHAND_SEAT)

        afresh = decide_give_up(taken, sitter, GiveUpCommand("c", taken.id.value, taken.version))

        assert hand_command("card", taken, sitter).refusal is None
        assert afresh.table.progress.give_up == GiveUpAsked(FOREHAND)

    @OPENINGS
    def test_the_declarers_chair_leaves_the_request_standing_and_every_command_seat_open(self, opening):
        freed = opened(asked_by_an_opponent(FOREHAND), MIDDLEHAND_SEAT, opening)

        assert freed.progress.give_up == GiveUpAsked(FOREHAND)
        for command in HAND_COMMANDS:
            decision = hand_command(command, freed, actor_at(freed, REARHAND_SEAT))
            assert (decision.refusal, decision.table) == (Refusal.SEAT_OPEN, freed)

    @OPENINGS
    def test_the_sitter_in_the_declarers_chair_is_asked_and_answers_while_the_one_who_left_is_not_asked(self, opening):
        table = asked_by_an_opponent(FOREHAND)
        leaver, sitter = actor_at(table, MIDDLEHAND_SEAT), newcomer()
        taken = sat(opened(table, MIDDLEHAND_SEAT, opening), sitter, MIDDLEHAND_SEAT)

        assert awaits_you(view_of(taken, sitter.account_id, NOBODY))
        assert not awaits_you(view_of(taken, leaver.account_id, NOBODY))
        assert decline_as(taken, sitter).progress.give_up is None

    @OPENINGS
    def test_the_other_opponents_chair_leaves_the_request_standing_for_the_declarer(self, opening):
        table = asked_by_an_opponent(FOREHAND)

        taken = sat(opened(table, REARHAND_SEAT, opening), newcomer(), REARHAND_SEAT)

        assert taken.progress.give_up == GiveUpAsked(FOREHAND)
        assert awaits_you(view_of(taken, actor_at(taken, MIDDLEHAND_SEAT).account_id, NOBODY))
        assert not awaits_you(view_of(taken, actor_at(taken, FOREHAND_SEAT).account_id, NOBODY))

    def test_a_person_declarer_who_stood_up_answers_the_request_after_sitting_in_his_held_chair(self):
        table = with_agents(asked_by_an_opponent(FOREHAND), FOREHAND_SEAT)
        declarer = actor_at(table, MIDDLEHAND_SEAT)

        back = sat(opened(table, MIDDLEHAND_SEAT, "stand-up"), declarer, MIDDLEHAND_SEAT)

        assert back.progress.give_up == GiveUpAsked(FOREHAND)
        assert decline_as(back, declarer).progress.give_up is None
