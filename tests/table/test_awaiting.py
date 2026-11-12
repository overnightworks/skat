"""Whether the table waits for a seat is decided from the seat's own view, in eight cases."""

from dataclasses import replace

import pytest

from skat.engine.bidding import Bid, Pass
from skat.engine.cards import DECK
from skat.engine.deal import Position
from skat.engine.declaration import Announcement, Declare, PutBack, TakeSkat
from skat.engine.games import GameKind
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer, Word, WordSaid
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.table.awaiting import awaits_you
from skat.table.kontra import NoWordCommand, decide_no_word
from skat.table.records import (
    Actor,
    Chair,
    EndedTable,
    EndProposal,
    EndReason,
    HandProgress,
    NoWordSaid,
    RamschOccasion,
    RamschSetting,
    Series,
    TableId,
    TableOptions,
)
from skat.table.rules import decide_sit
from skat.table.views import view_of
from tests.support.open_chairs import PHASES, REARHAND_SEAT, newcomer, sent_away
from tests.support.played_game import (
    a_whole_game,
    asked_by_the_declarer,
    between_games,
    declared_herz_hand,
    table_in,
)

MIDDLEHAND, REARHAND, FOREHAND = "account-middlehand", "account-rearhand", "account-forehand"
EVERYONE = (MIDDLEHAND, REARHAND, FOREHAND)
# Seat 2 deals, so the seats 1, 2 and 3 are middlehand, rearhand and forehand.
SEAT_OF = {MIDDLEHAND: 1, REARHAND: 2, FOREHAND: 3}
RAMSCH = TableOptions(
    ramsch=RamschSetting(
        RamschOccasion.PASSED_IN,
        RamschOptions(RamschScoring.SKAT_TO_LOSER, JungfrauRule.OFF, DurchmarschRule.WINS_120_FLAT),
    )
)
KONTRA_OPTIONS = TableOptions(
    kontra=KontraOptions(KontraSayer.ANY_OPPONENT, KontraReach.KONTRA_RE, KontraDeadline.OWN_CARD)
)
BIDDERS_ONLY_OPTIONS = TableOptions(
    kontra=KontraOptions(KontraSayer.BIDDERS_ONLY, KontraReach.KONTRA_RE, KontraDeadline.OWN_CARD)
)
ALL_PASS = (Pass(Position.MIDDLEHAND), Pass(Position.REARHAND), Pass(Position.FOREHAND))
HERZ_HAND = Declare(GameKind.HERZ, hand=True, ouvert=False, announcement=Announcement.NONE)
DECLARER_BID = (Bid(Position.MIDDLEHAND, 18), Pass(Position.FOREHAND), Pass(Position.REARHAND))


def waiting_for(table):
    """The accounts of the seated whose own view says the table waits for them."""
    return {account for account in EVERYONE if awaits_you(view_of(table, account, frozenset()))}


class TestTheTurnOfTheHand:
    @pytest.mark.parametrize(
        ("progress", "options", "waiting"),
        [
            pytest.param(HandProgress(), None, {MIDDLEHAND}, id="auction-first-bid"),
            pytest.param(HandProgress((Bid(Position.MIDDLEHAND, 18),)), None, {FOREHAND}, id="auction-answer"),
            pytest.param(HandProgress(DECLARER_BID), None, {MIDDLEHAND}, id="declarer-takes-the-skat"),
            pytest.param(
                HandProgress(DECLARER_BID, declaring=(TakeSkat(),)), None, {MIDDLEHAND}, id="declarer-puts-back"
            ),
            pytest.param(declared_herz_hand(), None, {FOREHAND}, id="play-forehand-leads"),
            pytest.param(HandProgress(ALL_PASS), RAMSCH, {FOREHAND}, id="ramsch-play"),
        ],
    )
    def test_the_seat_on_turn_is_awaited_and_no_other(self, progress, options, waiting):
        table = table_in(progress, options)

        assert waiting_for(table) == waiting

    def test_the_declarer_is_still_awaited_after_the_skat_went_back_until_the_game_is_declared(self):
        table = table_in(HandProgress(DECLARER_BID, declaring=(TakeSkat(), PutBack(DECK[30:32]))))

        assert MIDDLEHAND in waiting_for(table)


def kontra_hand(words=(), no_words=(), plays=0, options=KONTRA_OPTIONS):
    """The declared Herz Hand game at a table with Kontra, the words said and the answers of no word given."""
    table = table_in(declared_herz_hand(), options)
    progress = replace(
        table.progress,
        plays=a_whole_game(table)[:plays],
        words=tuple(words),
        no_words=frozenset(NoWordSaid(position, word) for position, word in no_words),
    )
    return replace(table, progress=progress)


class TestAKontraWord:
    @pytest.mark.parametrize(
        ("table", "waiting"),
        [
            pytest.param(kontra_hand(), {FOREHAND, REARHAND}, id="both-opponents-for-kontra-and-forehand-for-the-lead"),
            pytest.param(
                kontra_hand(no_words=[(Position.REARHAND, Word.KONTRA)]),
                {FOREHAND},
                id="not-the-opponent-who-answered",
            ),
            pytest.param(
                kontra_hand(no_words=[(Position.FOREHAND, Word.KONTRA), (Position.REARHAND, Word.KONTRA)]),
                {FOREHAND},
                id="only-the-turn-once-both-answered",
            ),
            pytest.param(
                kontra_hand(words=[WordSaid(Position.FOREHAND, Word.KONTRA, 0)]),
                {MIDDLEHAND, FOREHAND},
                id="the-declarer-for-re-and-no-other-opponent-for-kontra",
            ),
            pytest.param(
                kontra_hand(
                    words=[WordSaid(Position.FOREHAND, Word.KONTRA, 0)],
                    no_words=[(Position.FOREHAND, Word.KONTRA), (Position.MIDDLEHAND, Word.RE)],
                ),
                {FOREHAND},
                id="the-answer-of-an-earlier-word-and-the-declarers-answer-end-the-wait",
            ),
            pytest.param(
                kontra_hand(plays=1),
                {MIDDLEHAND, REARHAND},
                id="an-opponent-who-played-his-card-is-no-longer-awaited-for-the-word",
            ),
            pytest.param(
                kontra_hand(options=BIDDERS_ONLY_OPTIONS),
                {FOREHAND},
                id="an-opponent-who-did-not-bid-at-a-bidders-only-table-is-not-awaited",
            ),
            pytest.param(
                kontra_hand(
                    words=[WordSaid(Position.FOREHAND, Word.KONTRA, 0), WordSaid(Position.MIDDLEHAND, Word.RE, 0)]
                ),
                {FOREHAND},
                id="no-word-is-left-within-the-reach",
            ),
        ],
    )
    def test_a_seat_with_a_word_open_that_it_has_not_answered_is_awaited(self, table, waiting):
        assert waiting_for(table) == waiting

    def test_the_seat_is_not_awaited_for_a_word_while_a_chair_of_the_hand_is_open(self):
        assert waiting_for(sent_away(kontra_hand(), REARHAND_SEAT)) == set()

    def test_the_answer_raises_the_revision_and_ends_the_wait(self):
        table = kontra_hand()
        before = view_of(table, REARHAND, frozenset())

        after = view_of(
            decide_no_word(table, Actor(REARHAND, "Rhea"), NoWordCommand("c", table.id.value, table.version)).table,
            REARHAND,
            frozenset(),
        )

        assert (awaits_you(before), awaits_you(after)) == (True, False)
        assert after.version > before.version


class TestAGiveUpQuestion:
    @pytest.mark.parametrize(
        ("declined_by", "waiting"),
        [
            pytest.param(None, {FOREHAND, REARHAND}, id="an-opponent-who-has-not-answered-though-not-on-turn"),
            pytest.param(Position.REARHAND, {FOREHAND}, id="not-the-opponent-who-declined-nor-the-asker"),
        ],
    )
    def test_the_opponents_who_have_not_answered_are_awaited(self, declined_by, waiting):
        assert waiting_for(asked_by_the_declarer(declined_by)) == waiting


class TestAResultAndTheEndOfTheSeries:
    @pytest.mark.parametrize(
        ("table", "waiting"),
        [
            pytest.param(
                between_games(SEAT_OF[REARHAND]), {MIDDLEHAND, FOREHAND}, id="a-result-awaits-who-has-not-continued"
            ),
            pytest.param(between_games(1, 2, 3), set(), id="a-result-awaits-nobody-once-all-continued"),
            pytest.param(
                between_games(SEAT_OF[MIDDLEHAND], series=Series(12, 12)),
                {REARHAND, FOREHAND},
                id="a-series-over-awaits-who-has-not-marked-new-series",
            ),
            pytest.param(
                between_games(series=Series(12, 1, ended_early=True)),
                set(EVERYONE),
                id="a-series-ended-early-awaits-the-unmarked-like-one-that-ran-out",
            ),
            pytest.param(
                between_games(1, 2, 3, series=Series(12, 12)), set(), id="a-series-over-awaits-nobody-once-all-marked"
            ),
        ],
    )
    def test_the_seats_that_have_not_answered_the_result_are_awaited(self, table, waiting):
        assert waiting_for(table) == waiting


class TestAnEarlyEndProposal:
    @pytest.mark.parametrize(
        ("proposal", "waiting"),
        [
            pytest.param(EndProposal(1), {REARHAND, FOREHAND}, id="the-seats-that-have-not-answered"),
            pytest.param(EndProposal(1, accepter=2), {FOREHAND}, id="not-the-proposer-nor-the-accepter"),
        ],
    )
    def test_the_seats_that_have_not_answered_are_awaited(self, proposal, waiting):
        assert waiting_for(between_games(1, 2, 3, proposal=proposal)) == waiting


def with_a_free_first_chair(table):
    return replace(table, chairs=(Chair(1, None), *table.chairs[1:]))


def with_a_free_third_chair(table):
    return replace(table, hand=None, chairs=(table.chairs[0], table.chairs[1], Chair(3, None)))


class TestNothingIsAwaited:
    @pytest.mark.parametrize(
        ("table", "waiting"),
        [
            pytest.param(
                with_a_free_first_chair(between_games()), {REARHAND, FOREHAND}, id="a-free-chair-is-not-awaited"
            ),
            pytest.param(
                replace(table_in(HandProgress(ALL_PASS)), hand=None), set(), id="a-passed-in-hand-while-it-pauses"
            ),
            pytest.param(
                with_a_free_third_chair(table_in(HandProgress())), set(), id="fewer-than-three-chairs-and-no-result"
            ),
        ],
    )
    def test_the_seats_that_nothing_waits_for_are_not_awaited(self, table, waiting):
        assert waiting_for(table) == waiting

    def test_an_account_without_a_chair_is_not_awaited(self):
        view = view_of(between_games(), "account-watcher", frozenset({"account-watcher"}))

        assert awaits_you(view) is False

    def test_an_ended_table_awaits_nobody(self):
        ended = EndedTable(TableId("0" * 32), 9, EndReason.EMPTY, 3600)

        assert awaits_you(view_of(ended, MIDDLEHAND, frozenset())) is False


class TestAnOpenChair:
    """The hand waits for a sitter, so no seat is awaited and the revision rises when one joins."""

    @pytest.mark.parametrize("phase", PHASES)
    def test_no_seat_is_awaited_while_a_chair_of_the_running_hand_is_open(self, phase):
        running = PHASES[phase]()
        waiting = sent_away(running, REARHAND_SEAT)

        assert waiting_for(running)
        assert waiting_for(waiting) == set()

    @pytest.mark.parametrize(
        ("phase", "on_turn"),
        [("pushing-start", FOREHAND), ("pushing-after-the-take", FOREHAND), ("pushing-after-the-push", MIDDLEHAND)],
    )
    def test_the_seat_pushing_is_awaited_but_not_while_a_chair_is_open(self, phase, on_turn):
        running = PHASES[phase]()

        assert waiting_for(running) == {on_turn}
        assert waiting_for(sent_away(running, REARHAND_SEAT)) == set()
        assert waiting_for(sent_away(running, SEAT_OF[on_turn])) == set()

    def test_no_seat_is_awaited_for_a_give_up_question_either(self):
        asked = asked_by_the_declarer()

        assert waiting_for(sent_away(asked, REARHAND_SEAT)) == set()

    def test_the_seat_on_turn_is_awaited_again_under_a_higher_revision_once_a_sitter_joins(self):
        running = PHASES["auction"]()
        waiting = sent_away(running, SEAT_OF[REARHAND])
        sitter = newcomer()

        taken = decide_sit(waiting, sitter, SEAT_OF[REARHAND], None).table

        assert waiting_for(taken) == waiting_for(running)
        assert taken.version > waiting.version
