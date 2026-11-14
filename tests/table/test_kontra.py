from dataclasses import replace

import pytest

from skat.engine.bidding import Bid, BidRefusal, Hold, Pass
from skat.engine.deal import Position, seats_from
from skat.engine.kontra import (
    Doubling,
    KontraDeadline,
    KontraOptions,
    KontraReach,
    KontraRefusal,
    KontraSayer,
    Word,
    WordSaid,
)
from skat.table.awaiting import awaits_you
from skat.table.hand_state import doubling_of, playing_of
from skat.table.kontra import (
    KontraCommand,
    decide_kontra,
    kontra_payload,
    kontra_view_of,
)
from skat.table.playing import (
    GiveUpCommand,
    PlayCardCommand,
    ThrowDownCommand,
    decide_card,
    decide_give_up,
    decide_throw_down,
)
from skat.table.records import (
    Actor,
    CreateTable,
    HandProgress,
    NoWordSaid,
    Refusal,
    TableOptions,
    parsed_refusal,
)
from skat.table.rules import create_payload
from skat.table.views import view_of
from tests.support.played_game import (
    HERZ_HAND,
    a_whole_game,
    asked_by_an_opponent,
    before_the_last_card,
    declared_herz_hand,
    table_in,
)

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
KONTRA, RE, SUPRA, HIRSCH = Word.KONTRA, Word.RE, Word.SUPRA, Word.HIRSCH
OWN_CARD, FIRST_CARD = KontraDeadline.OWN_CARD, KontraDeadline.FIRST_CARD
VERSION = 7


def options_of(sayer=KontraSayer.ANY_OPPONENT, reach=KontraReach.KONTRA_RE, deadline=OWN_CARD):
    return TableOptions(kontra=KontraOptions(sayer, reach, deadline))


def actor(position):
    return Actor(account_id=f"account-{position.name.lower()}", display_name=position.name)


def kontra_table(options=None, progress=None):
    return table_in(declared_herz_hand() if progress is None else progress, options or options_of())


def with_words(table, *words, plays=0):
    cards = a_whole_game(table)[:plays]
    return replace(table, progress=replace(table.progress, plays=cards, words=words))


def say_as(table, position, word, version=VERSION):
    return decide_kontra(table, actor(position), KontraCommand("command-1", table.id.value, version, word))


class TestSaying:
    def test_an_opponent_says_kontra_and_the_word_is_stored_with_the_cards_played_before_it(self):
        decision = say_as(kontra_table(), FOREHAND, KONTRA)

        assert decision.refusal is None
        assert decision.table.version == VERSION + 1
        assert decision.table.progress.words == (WordSaid(FOREHAND, KONTRA, 0),)

    def test_the_declarer_answers_with_re_after_the_opponents_first_card(self):
        table = with_words(kontra_table(), WordSaid(FOREHAND, KONTRA, 0), plays=1)

        decision = say_as(table, MIDDLEHAND, RE)

        assert decision.table.progress.words[-1] == WordSaid(MIDDLEHAND, RE, 1)

    @pytest.mark.parametrize(
        ("table", "position", "word", "version", "expected"),
        [
            pytest.param(replace(kontra_table(), hand=None, dealer=None), FOREHAND, KONTRA, VERSION, Refusal.NO_HAND),
            pytest.param(
                replace(kontra_table(), hand=None, dealer=None, options=TableOptions()),
                FOREHAND,
                KONTRA,
                VERSION,
                Refusal.NO_HAND,
                id="no-hand-before-rule-off",
            ),
            pytest.param(kontra_table(), FOREHAND, KONTRA, VERSION - 1, Refusal.STALE_VERSION),
            pytest.param(
                kontra_table(options=TableOptions()),
                FOREHAND,
                KONTRA,
                VERSION - 1,
                Refusal.STALE_VERSION,
                id="stale-before-rule-off",
            ),
            pytest.param(kontra_table(options=TableOptions()), FOREHAND, KONTRA, VERSION, Refusal.RULE_OFF),
            pytest.param(
                kontra_table(options=TableOptions(), progress=HandProgress()),
                FOREHAND,
                KONTRA,
                VERSION,
                Refusal.RULE_OFF,
                id="rule-off-before-wrong-phase",
            ),
            pytest.param(kontra_table(progress=HandProgress()), FOREHAND, KONTRA, VERSION, Refusal.WRONG_PHASE),
            pytest.param(
                kontra_table(progress=HandProgress(auction=(Bid(MIDDLEHAND, 18), Pass(FOREHAND), Pass(REARHAND)))),
                FOREHAND,
                KONTRA,
                VERSION,
                Refusal.WRONG_PHASE,
                id="declaring",
            ),
            pytest.param(kontra_table(), MIDDLEHAND, KONTRA, VERSION, KontraRefusal.NOT_YOUR_WORD, id="declarer"),
            pytest.param(kontra_table(), FOREHAND, RE, VERSION, KontraRefusal.NOT_YOUR_WORD, id="re-first"),
            pytest.param(
                with_words(kontra_table(), WordSaid(FOREHAND, KONTRA, 0)),
                REARHAND,
                KONTRA,
                VERSION,
                KontraRefusal.NOT_YOUR_WORD,
                id="second-kontra",
            ),
            pytest.param(
                with_words(kontra_table(), WordSaid(FOREHAND, KONTRA, 0), WordSaid(MIDDLEHAND, RE, 0)),
                FOREHAND,
                SUPRA,
                VERSION,
                KontraRefusal.BEYOND_REACH,
                id="supra-at-kontra-re",
            ),
            pytest.param(
                with_words(kontra_table(), plays=1),
                FOREHAND,
                KONTRA,
                VERSION,
                KontraRefusal.TOO_LATE,
                id="after-a-card",
            ),
            pytest.param(
                with_words(kontra_table(), WordSaid(FOREHAND, KONTRA, 0), plays=3),
                MIDDLEHAND,
                RE,
                VERSION,
                KontraRefusal.TOO_LATE,
                id="re-after-his-next-card",
            ),
            pytest.param(
                kontra_table(options=options_of(KontraSayer.BIDDERS_ONLY)),
                REARHAND,
                KONTRA,
                VERSION,
                KontraRefusal.DID_NOT_BID,
                id="rearhand-passed-without-bidding",
            ),
        ],
    )
    def test_a_word_is_refused_in_the_order_hand_chair_version_rule_phase_then_the_engine(
        self, table, position, word, version, expected
    ):
        decision = say_as(table, position, word, version)

        assert decision.refusal is expected
        assert decision.table == table

    def test_a_watcher_is_not_seated(self):
        command = KontraCommand("command-1", kontra_table().id.value, VERSION, KONTRA)

        decision = decide_kontra(kontra_table(), Actor("account-dora", "Dora"), command)

        assert decision.refusal is Refusal.NOT_SEATED

    def test_a_bidder_may_say_kontra_where_the_table_asks_it(self):
        progress = HandProgress(
            auction=(Bid(MIDDLEHAND, 18), Hold(FOREHAND), Bid(MIDDLEHAND, 20), Pass(FOREHAND), Pass(REARHAND)),
            declaring=(HERZ_HAND,),
        )
        table = kontra_table(options_of(KontraSayer.BIDDERS_ONLY), progress)

        assert say_as(table, FOREHAND, KONTRA).refusal is None
        assert say_as(table, REARHAND, KONTRA).refusal is KontraRefusal.DID_NOT_BID


def answer_as(table, position, version=VERSION):
    return decide_kontra(table, actor(position), KontraCommand("command-1", table.id.value, version, None))


def waking_view(table, position):
    """The word the seat's own view names, whether it has answered it and whether the table waits for it; the seats
    that speak are off turn while nobody has played a card, forehand leading.
    """
    view = view_of(table, actor(position).account_id, frozenset())
    kontra = view.hand.playing.kontra
    return kontra.my_word, kontra.my_word_answered, awaits_you(view)


class TestAnsweringNoWord:
    def test_an_opponent_answers_no_word_and_the_answer_is_kept_with_a_risen_version(self):
        decision = answer_as(kontra_table(), FOREHAND)

        assert decision.refusal is None
        assert decision.table.version == VERSION + 1
        assert decision.table.progress.no_words == frozenset({NoWordSaid(FOREHAND, KONTRA)})
        assert decision.table.progress.words == ()

    def test_a_second_answer_of_the_same_seat_for_the_same_word_changes_nothing(self):
        answered = answer_as(kontra_table(), FOREHAND).table

        again = answer_as(answered, FOREHAND, answered.version)

        assert again.refusal is None
        assert again.table == answered

    def test_the_other_opponent_answers_for_its_own_seat(self):
        answered = answer_as(kontra_table(), FOREHAND).table

        decision = answer_as(answered, REARHAND, answered.version)

        assert decision.table.progress.no_words == frozenset(
            {NoWordSaid(FOREHAND, KONTRA), NoWordSaid(REARHAND, KONTRA)}
        )

    def test_the_word_stays_open_and_the_answer_is_no_word_of_the_log(self):
        answered = answer_as(kontra_table(), FOREHAND).table

        said = say_as(answered, FOREHAND, KONTRA, answered.version)

        assert said.refusal is None
        assert doubling_of(said.table).factor == 2
        assert doubling_of(answered) == Doubling.start()

    def test_each_stage_is_answered_on_its_own_and_the_wake_ends_with_the_answer_through_hirsch(self):
        table = kontra_table(options_of(reach=KontraReach.UP_TO_HIRSCH))
        stages = ((REARHAND, KONTRA), (MIDDLEHAND, RE), (REARHAND, SUPRA), (MIDDLEHAND, HIRSCH))
        said = []

        for position, word in stages:
            before = waking_view(table, position)
            table = answer_as(table, position, table.version).table
            after = waking_view(table, position)
            said.append(WordSaid(position, word, 0))
            table = with_words(table, *said)

            assert (before, after) == ((word, False, True), (word, True, False))
        assert table.progress.no_words == {NoWordSaid(position, word) for position, word in stages}

    @pytest.mark.parametrize(
        ("table", "position", "version", "expected"),
        [
            pytest.param(
                replace(kontra_table(), hand=None, dealer=None), FOREHAND, VERSION, Refusal.NO_HAND, id="no-hand"
            ),
            pytest.param(kontra_table(), FOREHAND, VERSION - 1, Refusal.STALE_VERSION, id="stale"),
            pytest.param(kontra_table(options=TableOptions()), FOREHAND, VERSION, Refusal.RULE_OFF, id="rule-off"),
            pytest.param(
                kontra_table(progress=HandProgress()), FOREHAND, VERSION, Refusal.WRONG_PHASE, id="no-game-yet"
            ),
            pytest.param(
                kontra_table(), MIDDLEHAND, VERSION, KontraRefusal.NOT_YOUR_WORD, id="declarer-before-a-kontra"
            ),
            pytest.param(
                with_words(kontra_table(), WordSaid(FOREHAND, KONTRA, 0)),
                REARHAND,
                VERSION,
                KontraRefusal.NOT_YOUR_WORD,
                id="the-other-opponent-after-a-kontra",
            ),
            pytest.param(
                with_words(kontra_table(), plays=1), FOREHAND, VERSION, KontraRefusal.TOO_LATE, id="after-his-card"
            ),
            pytest.param(
                kontra_table(options=options_of(KontraSayer.BIDDERS_ONLY)),
                REARHAND,
                VERSION,
                KontraRefusal.DID_NOT_BID,
                id="did-not-bid",
            ),
            pytest.param(
                with_words(kontra_table(), WordSaid(FOREHAND, KONTRA, 0), WordSaid(MIDDLEHAND, RE, 0)),
                FOREHAND,
                VERSION,
                KontraRefusal.BEYOND_REACH,
                id="no-word-left-within-the-reach",
            ),
        ],
    )
    def test_a_no_word_is_refused_as_a_word_the_seat_cannot_say_now_is(self, table, position, version, expected):
        decision = answer_as(table, position, version)

        assert decision.refusal is expected
        assert decision.table == table

    def test_the_answer_makes_a_payload_of_its_own_beside_the_word(self):
        command = KontraCommand("command-1", "table", 5, None)

        assert kontra_payload(command) == "table:5:no-word"
        assert kontra_payload(replace(command, word=KONTRA)) != kontra_payload(command)


BIDDING_FOREHAND = HandProgress(
    auction=(Bid(MIDDLEHAND, 18), Hold(FOREHAND), Bid(MIDDLEHAND, 20), Pass(FOREHAND), Pass(REARHAND)),
    declaring=(HERZ_HAND,),
)


def first_card_table(sayer=KontraSayer.ANY_OPPONENT, reach=KontraReach.KONTRA_RE, progress=None):
    return kontra_table(options_of(sayer, reach, FIRST_CARD), progress)


def lead(table):
    """The first card of the hand, played by forehand."""
    first = a_whole_game(table)[0]
    command = PlayCardCommand("command-1", table.id.value, table.version, first.card)
    return decide_card(table, actor(first.position), command)


def after_answers(table, *positions):
    for position in positions:
        table = answer_as(table, position, table.version).table
    return table


class TestTheFirstCardDeadline:
    def test_the_first_card_is_refused_while_an_opponent_has_neither_said_kontra_nor_declined(self):
        table = first_card_table()

        decision = lead(table)

        assert (decision.refusal, decision.table) == (KontraRefusal.WORDS_DUE, table)

    def test_the_first_card_is_played_where_the_table_gives_the_opponents_the_time_of_their_own_card(self):
        assert lead(kontra_table()).refusal is None

    def test_a_table_without_kontra_plays_the_first_card(self):
        assert lead(kontra_table(options=TableOptions())).refusal is None

    def test_each_opponents_answer_of_no_word_is_a_decline_that_clears_his_block_on_the_first_card(self):
        one_answered = after_answers(first_card_table(), FOREHAND)
        both_answered = after_answers(one_answered, REARHAND)

        assert lead(one_answered).refusal is KontraRefusal.WORDS_DUE
        assert lead(both_answered).refusal is None
        assert doubling_of(both_answered).declined == {FOREHAND, REARHAND}

    def test_a_second_answer_of_the_same_seat_changes_nothing(self):
        answered = after_answers(first_card_table(), FOREHAND)

        again = answer_as(answered, FOREHAND, answered.version)

        assert (again.refusal, again.table) == (None, answered)

    def test_an_opponent_who_declined_says_no_kontra_after_it(self):
        answered = after_answers(first_card_table(), FOREHAND)

        assert say_as(answered, FOREHAND, KONTRA, answered.version).refusal is KontraRefusal.NOT_YOUR_WORD

    def test_a_non_bidders_answer_of_no_word_is_refused_as_did_not_bid_where_only_bidders_say_kontra(self):
        table = first_card_table(KontraSayer.BIDDERS_ONLY, progress=BIDDING_FOREHAND)

        decision = answer_as(table, REARHAND)

        assert (decision.refusal, decision.table) == (KontraRefusal.DID_NOT_BID, table)

    def test_the_first_card_waits_for_the_bidder_alone_where_only_bidders_say_kontra(self):
        table = first_card_table(KontraSayer.BIDDERS_ONLY, progress=BIDDING_FOREHAND)

        assert lead(table).refusal is KontraRefusal.WORDS_DUE
        assert lead(after_answers(table, FOREHAND)).refusal is None

    def test_the_first_card_waits_for_no_one_where_no_opponent_bid_and_only_bidders_say_kontra(self):
        assert lead(first_card_table(KontraSayer.BIDDERS_ONLY)).refusal is None

    def test_the_declarer_owes_his_answer_to_a_kontra_before_the_first_card(self):
        said = say_as(first_card_table(), FOREHAND, KONTRA).table

        assert lead(said).refusal is KontraRefusal.WORDS_DUE
        assert lead(say_as(said, MIDDLEHAND, RE, said.version).table).refusal is None
        assert lead(after_answers(said, MIDDLEHAND)).refusal is None

    def test_the_table_declines_for_the_opponent_left_with_no_word_once_a_kontra_stands(self):
        declined = after_answers(say_as(first_card_table(), FOREHAND, KONTRA).table, MIDDLEHAND)

        assert REARHAND not in doubling_of(declined).declined
        assert lead(declined).refusal is None

    def test_the_declarer_who_answered_a_kontra_with_no_word_says_no_re_after_it(self):
        declined = after_answers(say_as(first_card_table(), FOREHAND, KONTRA).table, MIDDLEHAND)

        assert say_as(declined, MIDDLEHAND, RE, declined.version).refusal is KontraRefusal.NOT_YOUR_WORD

    @pytest.mark.parametrize(
        ("words", "owing"),
        [
            pytest.param((WordSaid(REARHAND, KONTRA, 0), WordSaid(MIDDLEHAND, RE, 0)), REARHAND, id="supra"),
            pytest.param(
                (WordSaid(REARHAND, KONTRA, 0), WordSaid(MIDDLEHAND, RE, 0), WordSaid(REARHAND, SUPRA, 0)),
                MIDDLEHAND,
                id="hirsch",
            ),
        ],
    )
    def test_each_stage_up_to_hirsch_waits_for_its_speaker_to_say_the_word_or_decline(self, words, owing):
        table = with_words(first_card_table(reach=KontraReach.UP_TO_HIRSCH), *words)

        assert lead(table).refusal is KontraRefusal.WORDS_DUE
        assert lead(after_answers(table, owing)).refusal is None

    def test_a_card_once_played_ends_the_words_and_the_answers(self):
        played = with_words(first_card_table(), plays=1)

        assert answer_as(played, FOREHAND).refusal is KontraRefusal.TOO_LATE
        assert say_as(played, FOREHAND, KONTRA).refusal is KontraRefusal.TOO_LATE

    def test_the_cards_after_the_first_wait_for_no_word(self):
        table = first_card_table()
        played = with_words(table, plays=1)
        next_card = a_whole_game(table)[1]
        command = PlayCardCommand("command-1", played.id.value, played.version, next_card.card)

        assert decide_card(played, actor(next_card.position), command).refusal is None


class TestTheFirstCardWaitingInTheViewer:
    @pytest.mark.parametrize(
        "viewer",
        [
            pytest.param(frozenset({FOREHAND}), id="the-leader"),
            pytest.param(frozenset({MIDDLEHAND}), id="the-declarer"),
            pytest.param(frozenset(), id="a-watcher"),
        ],
    )
    def test_every_viewer_is_told_that_the_first_card_waits_on_a_word_until_the_words_are_in(self, viewer):
        table = first_card_table()
        decided = after_answers(table, FOREHAND, REARHAND)

        before = kontra_view_of(table, playing_of(table), table.dealer, viewer)
        after = kontra_view_of(decided, playing_of(decided), decided.dealer, viewer)

        assert (before.first_card_waits, after.first_card_waits) == (True, False)

    def test_a_table_with_the_time_of_the_own_card_does_not_tell_that_the_first_card_waits(self):
        table = kontra_table()

        view = kontra_view_of(table, playing_of(table), table.dealer, frozenset({FOREHAND}))

        assert view.first_card_waits is False

    def test_the_first_card_no_longer_waits_after_it_is_played(self):
        table = with_words(first_card_table(), plays=1)

        view = kontra_view_of(table, playing_of(table), table.dealer, frozenset({FOREHAND}))

        assert view.first_card_waits is False

    def test_a_seat_that_declined_is_offered_no_word_and_a_seat_still_undecided_keeps_its_kontra(self):
        table = after_answers(first_card_table(), FOREHAND)

        mine = {
            position: kontra_view_of(table, playing_of(table), table.dealer, frozenset({position}))
            for position in (FOREHAND, REARHAND)
        }

        assert mine[REARHAND].my_word is KONTRA
        assert mine[FOREHAND].my_word is None


class TestAnAnswerInTheViewer:
    @pytest.mark.parametrize(
        ("viewer", "expected"),
        [
            pytest.param(frozenset({FOREHAND}), True, id="the-seat-that-answered"),
            pytest.param(frozenset({REARHAND}), False, id="the-other-opponent"),
            pytest.param(frozenset({MIDDLEHAND}), False, id="the-declarer-with-no-word-to-say"),
            pytest.param(frozenset(), False, id="a-watcher"),
        ],
    )
    def test_only_the_seat_that_answered_sees_its_answer(self, viewer, expected):
        table = answer_as(kontra_table(), FOREHAND).table

        view = kontra_view_of(table, playing_of(table), table.dealer, viewer)

        assert view.my_word_answered is expected

    def test_an_answer_to_an_earlier_word_does_not_answer_the_word_now_open(self):
        answered = answer_as(kontra_table(), FOREHAND).table
        table = with_words(answered, WordSaid(REARHAND, KONTRA, 0))

        view = kontra_view_of(table, playing_of(table), table.dealer, frozenset({FOREHAND}))

        assert (view.my_word, view.my_word_answered) == (None, False)


class TestTheDoublingOfAHand:
    def test_the_stored_words_rebuild_the_doubling_of_the_running_hand(self):
        words = (
            WordSaid(FOREHAND, KONTRA, 0),
            WordSaid(MIDDLEHAND, RE, 1),
            WordSaid(FOREHAND, SUPRA, 3),
            WordSaid(MIDDLEHAND, HIRSCH, 3),
        )
        table = with_words(kontra_table(options_of(reach=KontraReach.UP_TO_HIRSCH)), *words, plays=4)

        doubling = doubling_of(table)

        assert doubling.words == (KONTRA, RE, SUPRA, HIRSCH)
        assert doubling.factor == 16

    def test_a_declared_hand_without_stored_words_has_the_starting_doubling(self):
        next_hand = kontra_table(progress=declared_herz_hand())

        assert doubling_of(next_hand) == Doubling.start()

    @pytest.mark.parametrize(
        "table",
        [
            pytest.param(kontra_table(options=TableOptions()), id="a-table-without-kontra"),
            pytest.param(kontra_table(progress=HandProgress()), id="no-game-yet"),
            pytest.param(replace(kontra_table(), hand=None, dealer=None), id="no-hand"),
        ],
    )
    def test_there_is_no_doubling_where_nothing_can_be_said(self, table):
        assert doubling_of(table) is None


class TestWhatEachViewerSees:
    def test_everyone_sees_the_words_with_their_seats_and_the_factor(self):
        table = with_words(kontra_table(), WordSaid(FOREHAND, KONTRA, 0), WordSaid(MIDDLEHAND, RE, 1), plays=1)
        seats = seats_from(table.dealer)

        for viewer in (frozenset({FOREHAND}), frozenset({MIDDLEHAND}), frozenset({REARHAND}), frozenset()):
            view = kontra_view_of(table, playing_of(table), table.dealer, viewer)

            assert [(each.seat, each.word) for each in view.said] == [
                (seats[FOREHAND], KONTRA),
                (seats[MIDDLEHAND], RE),
            ]
            assert view.factor == 4

    @pytest.mark.parametrize(
        ("words", "expected"),
        [
            pytest.param((), {FOREHAND: KONTRA, MIDDLEHAND: None, REARHAND: KONTRA}, id="before-any-word"),
            pytest.param(
                (WordSaid(FOREHAND, KONTRA, 0),),
                {FOREHAND: None, MIDDLEHAND: RE, REARHAND: None},
                id="after-kontra",
            ),
            pytest.param(
                (WordSaid(FOREHAND, KONTRA, 0), WordSaid(MIDDLEHAND, RE, 0)),
                {FOREHAND: None, MIDDLEHAND: None, REARHAND: None},
                id="after-re-at-kontra-re",
            ),
        ],
    )
    def test_only_the_viewers_own_chair_gets_the_word_it_may_say_now(self, words, expected):
        table = with_words(kontra_table(), *words)

        mine = {
            position: kontra_view_of(table, playing_of(table), table.dealer, frozenset({position})).my_word
            for position in expected
        }

        assert mine == expected
        assert kontra_view_of(table, playing_of(table), table.dealer, frozenset()).my_word is None

    def test_a_table_without_kontra_has_no_view(self):
        table = kontra_table(options=TableOptions())

        assert kontra_view_of(table, playing_of(table), table.dealer, frozenset({FOREHAND})) is None


class TestTheEntryOfADoubledGame:
    def last_card_entry(self, *words):
        table, last = before_the_last_card(table_in(declared_herz_hand(), options_of()))
        table = replace(table, progress=replace(table.progress, words=words))
        command = PlayCardCommand("command-1", table.id.value, table.version, last.card)
        return decide_card(table, actor(last.position), command).table.game_list[-1]

    def test_the_last_card_writes_the_last_word_and_the_doubled_list_score(self):
        plain = self.last_card_entry()
        doubled = self.last_card_entry(WordSaid(FOREHAND, KONTRA, 0))

        assert plain.kontra_word is None
        assert doubled.kontra_word is KONTRA
        assert doubled.score == plain.score * 2
        assert (doubled.won, doubled.settled_value, doubled.game_value) == (
            plain.won,
            plain.settled_value,
            plain.game_value,
        )

    @pytest.mark.parametrize(
        ("decide", "command"),
        [
            pytest.param(decide_give_up, GiveUpCommand, id="give-up"),
            pytest.param(decide_throw_down, ThrowDownCommand, id="throw-down"),
        ],
    )
    def test_a_give_up_and_a_throw_down_write_the_doubled_entry_too(self, decide, command):
        def entry(*words):
            table = replace(kontra_table(), progress=replace(declared_herz_hand(), words=words))
            return decide(table, actor(MIDDLEHAND), command("command-1", table.id.value, VERSION)).table.game_list[-1]

        assert entry(WordSaid(FOREHAND, KONTRA, 0), WordSaid(MIDDLEHAND, RE, 0)).score == entry().score * 4
        assert entry(WordSaid(FOREHAND, KONTRA, 0)).kontra_word is KONTRA


class TestWhileAnOpponentsGiveUpWaits:
    @pytest.mark.parametrize(
        ("position", "word"),
        [
            pytest.param(FOREHAND, KONTRA, id="the-asker"),
            pytest.param(REARHAND, KONTRA, id="the-other-opponent"),
            pytest.param(MIDDLEHAND, RE, id="the-declarer"),
        ],
    )
    @pytest.mark.parametrize("said", [pytest.param(True, id="a-word"), pytest.param(False, id="no-word")])
    def test_a_word_and_the_answer_of_no_word_are_pending_and_change_nothing(self, position, word, said):
        table = asked_by_an_opponent(FOREHAND, options_of())

        decision = say_as(table, position, word if said else None)

        assert (decision.refusal, decision.table) == (Refusal.REQUEST_PENDING, table)

    def test_the_word_is_open_again_for_the_opponent_and_the_table_waits_for_it_after_the_declarers_no(self):
        table = asked_by_an_opponent(FOREHAND, options_of())
        assert waking_view(table, REARHAND) == (None, False, False)
        playing_on = replace(table, progress=replace(table.progress, give_up=None))

        assert waking_view(playing_on, REARHAND) == (KONTRA, False, True)
        assert say_as(playing_on, REARHAND, KONTRA).refusal is None
        assert answer_as(playing_on, REARHAND).refusal is None


class TestTheRequestsAndTheirReceipts:
    def test_a_table_without_kontra_keeps_the_payload_it_always_had(self):
        assert create_payload(CreateTable("command-1", 3)) == '{"series_length":3}'

    def test_the_options_of_kontra_join_the_payload_after_the_running_points(self):
        options = TableOptions(
            show_running_points=True,
            kontra=KontraOptions(KontraSayer.BIDDERS_ONLY, KontraReach.UP_TO_HIRSCH, OWN_CARD),
        )

        payload = create_payload(CreateTable("command-1", 3, options))

        assert payload == (
            '{"series_length":3,"show_running_points":true,'
            '"kontra":{"sayer":"bidders-only","reach":"up-to-hirsch","deadline":"own-card"}}'
        )

    def test_the_word_and_the_version_make_the_payload(self):
        command = KontraCommand("command-1", "table", 5, KONTRA)

        assert kontra_payload(command) == "table:5:kontra"
        assert kontra_payload(replace(command, word=RE)) != kontra_payload(command)

    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ("rule-off", Refusal.RULE_OFF),
            ("beyond-reach", KontraRefusal.BEYOND_REACH),
            ("did-not-bid", KontraRefusal.DID_NOT_BID),
            ("not-your-word", KontraRefusal.NOT_YOUR_WORD),
            ("too-late", KontraRefusal.TOO_LATE),
            ("over", BidRefusal.OVER),
            ("not-your-turn", BidRefusal.NOT_YOUR_TURN),
        ],
    )
    def test_a_stored_refusal_token_parses_to_its_owner_and_a_shared_one_keeps_the_auctions(self, token, expected):
        assert parsed_refusal(token) is expected
