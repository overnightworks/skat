import random
from dataclasses import replace
from datetime import timedelta

import pytest

from skat.engine.bock import BockOptions, BockOverlap, BockRounds, BockTrigger
from skat.engine.deal import deal
from skat.table.bock import bock_view_of
from skat.table.records import (
    Actor,
    Chair,
    EndProposal,
    HandProgress,
    Occupant,
    Refusal,
    Series,
    TableId,
    TableOptions,
    TableRecord,
    TableStyle,
    Visibility,
    parsed_refusal,
)
from skat.table.rules import dealt_next, drawn_hand, new_series_ask_stands, with_occupant
from skat.table.series_end import (
    END_ANSWER_SECONDS,
    SeriesEndCommand,
    decide_agree_to_end,
    decide_end_answer_lapse,
    decide_refuse_to_end,
    decide_stop_playing,
    new_series_lapsed,
    series_end_payload,
)
from tests.support.played_game import END_ASKED_AT, an_end_proposal, an_entry

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")
TABLE_VERSION = 9
LATER = END_ASKED_AT + timedelta(seconds=10)
MINUTE = timedelta(seconds=END_ANSWER_SECONDS)


def between_games(
    proposal: EndProposal | None = None, *, ready_seats: tuple[int, ...] = (), series: Series | None = None
) -> TableRecord:
    """Three seated after the second game of a series of twelve; `ready_seats` tapped „Weiter“."""
    people = ((1, ANNA), (2, BEN), (3, CLEO))
    chairs = tuple(
        Chair(seat, Occupant(actor.account_id, actor.display_name, actor.kind), ready=seat in ready_seats)
        for seat, actor in people
    )
    return TableRecord(
        TableId("0" * 32),
        TABLE_VERSION,
        chairs,
        dealer=2,
        hand=None,
        progress=HandProgress(),
        game_list=(an_entry(), an_entry()),
        series=series or Series(12, 2, end_proposal=proposal),
        options=TableOptions(),
        bock=BockRounds.start(),
        visibility=Visibility.OPEN,
        style=TableStyle.KLASSIK,
    )


def proposal_of(table: TableRecord) -> EndProposal | None:
    return table.series.end_proposal


class TestDecideAgreeToEnd:
    def test_the_first_yes_proposes_the_end_under_the_askers_seat_and_the_instant(self):
        decision = decide_agree_to_end(between_games(), BEN, END_ASKED_AT)

        assert decision.refusal is None
        assert proposal_of(decision.table) == an_end_proposal(2)
        assert decision.table.version == TABLE_VERSION + 1

    def test_the_second_yes_adds_to_the_proposal_and_the_series_goes_on(self):
        decision = decide_agree_to_end(between_games(an_end_proposal(1)), CLEO, LATER)

        assert proposal_of(decision.table) == an_end_proposal(1, 3)
        assert not decision.table.series.ended_early
        assert decision.table.version == TABLE_VERSION + 1

    def test_the_third_yes_ends_the_series_early_and_clears_every_mark(self):
        table = between_games(an_end_proposal(1, 2), ready_seats=(1, 2))

        decision = decide_agree_to_end(table, CLEO, LATER)

        assert decision.refusal is None
        assert decision.table.series == Series(12, 2, ended_early=True)
        assert [chair.ready for chair in decision.table.chairs] == [False, False, False]
        assert decision.table.version == TABLE_VERSION + 1

    def test_the_third_yes_lets_every_pending_bock_round_lapse(self):
        options = TableOptions(bock=BockOptions(frozenset({BockTrigger.RE}), BockOverlap.APPEND))
        table = replace(between_games(an_end_proposal(1, 2)), options=options, bock=BockRounds((3, 3)))

        decision = decide_agree_to_end(table, CLEO, LATER)

        assert decision.table.bock == BockRounds.start()
        assert bock_view_of(decision.table).games_left == 0

    @pytest.mark.parametrize(
        ("proposal", "actor", "refused_by"),
        [
            pytest.param(an_end_proposal(1, 2), CLEO, {3}, id="the-last-seat-to-answer"),
            pytest.param(an_end_proposal(1), BEN, {2, 3}, id="the-second-seat-to-answer"),
        ],
    )
    def test_a_yes_after_the_minute_ends_the_proposal_by_the_silent_seats_instead_of_the_series(
        self, proposal, actor, refused_by
    ):
        decision = decide_agree_to_end(
            between_games(proposal), actor, proposal.asked_at + MINUTE + timedelta(seconds=1)
        )

        assert decision.refusal is None
        assert proposal_of(decision.table) is None
        assert decision.table.series == Series(12, 2, end_refused_by=frozenset(refused_by))

    @pytest.mark.parametrize(
        ("proposal", "actor"),
        [
            pytest.param(an_end_proposal(1), ANNA, id="the-proposer-again"),
            pytest.param(an_end_proposal(1, 2), ANNA, id="the-proposer-after-an-acceptance"),
            pytest.param(an_end_proposal(1, 2), BEN, id="the-seat-that-agreed-again"),
        ],
    )
    def test_a_yes_from_a_seat_that_already_said_yes_changes_nothing(self, proposal, actor):
        table = between_games(proposal)

        decision = decide_agree_to_end(table, actor, LATER)

        assert decision.refusal is None
        assert decision.table == table

    @pytest.mark.parametrize(
        ("table", "actor", "refusal"),
        [
            pytest.param(between_games(), DORA, Refusal.NOT_SEATED, id="a-viewer-without-a-chair"),
            pytest.param(
                replace(between_games(), series=None, hand=deal(random.Random(3))),  # noqa: S311 - a seeded source makes the deal reproducible
                DORA,
                Refusal.NOT_SEATED,
                id="a-viewer-at-a-table-without-a-series-during-a-hand",
            ),
            pytest.param(
                replace(between_games(), dealer=None, game_list=(), series=Series(12, 0)),
                DORA,
                Refusal.NOT_SEATED,
                id="a-viewer-before-the-first-deal",
            ),
            pytest.param(replace(between_games(), series=None), ANNA, Refusal.NO_SERIES, id="a-table-without-a-series"),
            pytest.param(between_games(series=Series(12, 12)), ANNA, Refusal.SERIES_OVER, id="a-regular-end"),
            pytest.param(
                between_games(series=Series(12, 4, ended_early=True)), ANNA, Refusal.SERIES_OVER, id="an-early-end"
            ),
            pytest.param(
                replace(between_games(), hand=deal(random.Random(3))),  # noqa: S311 - a seeded source makes the deal reproducible
                ANNA,
                Refusal.HAND_RUNNING,
                id="a-running-hand",
            ),
            pytest.param(
                replace(between_games(), dealer=None, game_list=(), series=Series(12, 0)),
                ANNA,
                Refusal.NO_GAME_YET,
                id="before-the-first-deal",
            ),
            pytest.param(
                replace(between_games(), hand=deal(random.Random(3)), series=Series(12, 12)),  # noqa: S311 - a seeded source makes the deal reproducible
                ANNA,
                Refusal.HAND_RUNNING,
                id="a-running-last-hand-is-no-end-yet",
            ),
            pytest.param(
                between_games(series=Series(12, 2, end_refused_by=frozenset({2}))),
                CLEO,
                Refusal.END_REFUSED,
                id="a-proposal-refused-since-the-last-deal",
            ),
        ],
    )
    def test_a_yes_names_the_first_refusal_that_applies_and_changes_nothing(self, table, actor, refusal):
        decision = decide_agree_to_end(table, actor, LATER)

        assert decision.refusal is refusal
        assert decision.table == table


class TestDecideRefuseToEnd:
    @pytest.mark.parametrize(
        ("proposal", "actor", "refuser"),
        [
            pytest.param(an_end_proposal(1), BEN, 2, id="another-seat-refuses-a-proposal"),
            pytest.param(an_end_proposal(1), ANNA, 1, id="the-proposer-withdraws"),
            pytest.param(an_end_proposal(1, 2), CLEO, 3, id="the-third-refuses-after-a-yes"),
            pytest.param(an_end_proposal(1, 2), BEN, 2, id="a-seat-takes-its-yes-back"),
        ],
    )
    def test_a_no_ends_the_proposal_names_its_refuser_and_the_series_plays_on(self, proposal, actor, refuser):
        decision = decide_refuse_to_end(between_games(proposal), actor)

        assert decision.refusal is None
        assert proposal_of(decision.table) is None
        assert decision.table.series.end_refused_by == frozenset({refuser})
        assert decision.table.version == TABLE_VERSION + 1

    @pytest.mark.parametrize(
        ("table", "actor", "refusal"),
        [
            pytest.param(between_games(an_end_proposal(1)), DORA, Refusal.NOT_SEATED, id="a-viewer-without-a-chair"),
            pytest.param(between_games(), DORA, Refusal.NOT_SEATED, id="a-viewer-with-no-proposal-standing"),
            pytest.param(between_games(), ANNA, Refusal.NO_PROPOSAL, id="no-proposal-stands"),
            pytest.param(replace(between_games(), series=None), ANNA, Refusal.NO_PROPOSAL, id="no-series"),
        ],
    )
    def test_a_no_names_the_first_refusal_that_applies_and_changes_nothing(self, table, actor, refusal):
        decision = decide_refuse_to_end(table, actor)

        assert decision.refusal is refusal
        assert decision.table == table


class TestDecideEndAnswerLapse:
    MINUTE_OVER = END_ASKED_AT + timedelta(seconds=END_ANSWER_SECONDS)

    def test_a_seat_silent_for_the_minute_counts_as_no_and_is_named_with_the_other_silent_seats(self):
        table = between_games(an_end_proposal(1, 2))

        decision = decide_end_answer_lapse(table, self.MINUTE_OVER)

        assert proposal_of(decision.table) is None
        assert decision.table.series.end_refused_by == frozenset({3})
        assert not decision.table.series.ended_early
        assert decision.table.version == TABLE_VERSION + 1

    def test_every_seat_but_the_proposer_is_named_when_nobody_answered(self):
        decision = decide_end_answer_lapse(between_games(an_end_proposal(1)), self.MINUTE_OVER)

        assert decision.table.series.end_refused_by == frozenset({2, 3})

    @pytest.mark.parametrize(
        ("emptied_seats", "refused_by"),
        [
            pytest.param((3,), {2}, id="an-empty-chair-is-no-refuser"),
            pytest.param((2, 3), set(), id="no-seated-refuser-lapses-the-proposal-with-none-named"),
        ],
    )
    def test_an_empty_chair_never_counts_as_a_refuser(self, emptied_seats, refused_by):
        table = between_games(an_end_proposal(1))
        chairs = tuple(
            replace(chair, occupant=None) if chair.seat in emptied_seats else chair for chair in table.chairs
        )

        decision = decide_end_answer_lapse(replace(table, chairs=chairs), self.MINUTE_OVER)

        assert proposal_of(decision.table) is None
        assert decision.table.series.end_refused_by == frozenset(refused_by)

    @pytest.mark.parametrize(
        "table",
        [
            pytest.param(between_games(an_end_proposal(1)), id="a-proposal-before-its-minute-is-over"),
            pytest.param(between_games(), id="no-proposal"),
            pytest.param(replace(between_games(), series=None), id="no-series"),
        ],
    )
    def test_nothing_changes_where_no_proposal_has_run_out_of_time(self, table):
        assert decide_end_answer_lapse(table, self.MINUTE_OVER - timedelta(seconds=1)).table == table


class TestRecords:
    def test_the_proposer_agrees_to_its_own_proposal(self):
        agreed = frozenset({1})

        with pytest.raises(ValueError, match="proposer of an end agrees"):
            EndProposal(2, agreed, END_ASKED_AT)

    def test_a_proposal_every_seat_agreed_to_is_no_proposal(self):
        agreed = frozenset({1, 2, 3})

        with pytest.raises(ValueError, match="every seat agreed"):
            EndProposal(1, agreed, END_ASKED_AT)

    def test_a_series_that_ended_early_cannot_hold_a_proposal(self):
        proposal = an_end_proposal(1)

        with pytest.raises(ValueError, match="holds no proposal"):
            Series(12, 4, ended_early=True, end_proposal=proposal)

    def test_a_series_that_played_its_last_game_did_not_end_early(self):
        with pytest.raises(ValueError, match="did not end early"):
            Series(12, 12, ended_early=True)

    @pytest.mark.parametrize("refusal", [Refusal.NO_GAME_YET, Refusal.NO_PROPOSAL, Refusal.END_REFUSED])
    def test_a_stored_token_reads_back_to_its_refusal(self, refusal):
        assert parsed_refusal(refusal.value) is refusal


class TestPayload:
    def test_a_proposal_has_no_number_so_the_table_alone_is_the_payload(self):
        assert series_end_payload(SeriesEndCommand(command_id="command-end", table_id="0" * 32)) == "0" * 32


def at_the_series_end(*ready_seats: int, asked_at=None, early: bool = False, silent_seats: tuple[int, ...] = ()):
    """Three seated after the last game of a series of twelve, or after its early end; `ready_seats` chose „Neue
    Serie“, the first at `asked_at`, and the chairs of `silent_seats` are empty.
    """
    base = between_games(ready_seats=ready_seats, series=Series(12, 4, ended_early=True) if early else Series(12, 12))
    chairs = tuple(replace(chair, occupant=None) if chair.seat in silent_seats else chair for chair in base.chairs)
    return replace(base, chairs=chairs, series=replace(base.series, new_series_asked_at=asked_at))


class TestDecideStopPlaying:
    @pytest.mark.parametrize("early", [False, True], ids=["after-the-last-game", "after-an-early-end"])
    def test_every_seated_person_may_stop_at_the_series_end(self, early):
        for actor in (ANNA, BEN, CLEO):
            assert decide_stop_playing(at_the_series_end(early=early), actor) is None

    @pytest.mark.parametrize(
        ("table", "actor", "refusal"),
        [
            pytest.param(at_the_series_end(), DORA, Refusal.NOT_SEATED, id="a-viewer-without-a-chair"),
            pytest.param(replace(at_the_series_end(), series=None), ANNA, Refusal.NO_SERIES, id="no-series"),
            pytest.param(between_games(), ANNA, Refusal.SERIES_NOT_OVER, id="between-two-games"),
            pytest.param(
                replace(at_the_series_end(), hand=deal(random.Random(3))),  # noqa: S311 - a seeded source makes the deal reproducible
                ANNA,
                Refusal.SERIES_NOT_OVER,
                id="a-hand-runs-at-the-last-game",
            ),
        ],
    )
    def test_the_first_refusal_that_applies_is_named(self, table, actor, refusal):
        assert decide_stop_playing(table, actor) is refusal


class TestDecideNewSeriesLapse:
    MINUTE_OVER = END_ASKED_AT + MINUTE

    def test_a_seated_seat_silent_for_the_minute_stops_the_table(self):
        assert new_series_lapsed(at_the_series_end(1, 2, asked_at=END_ASKED_AT), self.MINUTE_OVER)

    def test_a_seated_seat_silent_beside_an_empty_chair_that_chose_stops_the_table(self):
        table = at_the_series_end(1, 3, asked_at=END_ASKED_AT, silent_seats=(3,))

        assert new_series_lapsed(table, self.MINUTE_OVER)

    @pytest.mark.parametrize(
        "table",
        [
            pytest.param(at_the_series_end(1, 2, 3, asked_at=END_ASKED_AT), id="every-seated-seat-chose"),
            pytest.param(
                at_the_series_end(1, 2, 3, asked_at=END_ASKED_AT, silent_seats=(3,)), id="the-silent-seat-stood-up"
            ),
        ],
    )
    def test_a_minute_no_silent_seated_seat_is_left_in_never_lapses(self, table):
        assert not new_series_lapsed(table, self.MINUTE_OVER)

    @pytest.mark.parametrize(
        "table",
        [
            pytest.param(at_the_series_end(1, asked_at=END_ASKED_AT), id="a-minute-with-time-left"),
            pytest.param(at_the_series_end(), id="nobody-chose-yet"),
            pytest.param(between_games(), id="between-two-games"),
            pytest.param(replace(between_games(), series=None), id="no-series"),
        ],
    )
    def test_nothing_changes_where_no_answer_has_run_out_of_time(self, table):
        assert not new_series_lapsed(table, self.MINUTE_OVER - timedelta(seconds=1))


class TestTheMinuteWhenASeatStandsUp:
    def test_the_given_marks_stay_and_the_minute_runs_while_a_seated_seat_is_silent(self):
        table = at_the_series_end(1, asked_at=END_ASKED_AT)

        after = with_occupant(table, 2, None)

        assert [chair.ready for chair in after.chairs] == [True, False, False]
        assert after.series.new_series_asked_at == END_ASKED_AT

    def test_the_last_silent_seat_standing_up_ends_the_minute_and_keeps_the_given_marks(self):
        table = at_the_series_end(1, 2, asked_at=END_ASKED_AT)

        after = with_occupant(table, 3, None)

        assert [chair.ready for chair in after.chairs] == [True, True, False]
        assert after.series.new_series_asked_at is None

    def test_the_only_seat_that_chose_standing_up_ends_the_minute(self):
        after = with_occupant(at_the_series_end(1, asked_at=END_ASKED_AT), 1, None)

        assert after.series.new_series_asked_at is None

    def test_a_minute_that_ended_that_way_stops_nothing_when_its_time_is_over(self):
        after = with_occupant(at_the_series_end(1, 2, asked_at=END_ASKED_AT), 3, None)

        assert not new_series_lapsed(after, END_ASKED_AT + MINUTE)

    @pytest.mark.parametrize(
        ("table", "stands"),
        [
            pytest.param(at_the_series_end(1, asked_at=END_ASKED_AT), True, id="a-seated-seat-is-silent"),
            pytest.param(
                at_the_series_end(1, 2, asked_at=END_ASKED_AT, silent_seats=(3,)), False, id="every-seated-seat-chose"
            ),
            pytest.param(at_the_series_end(asked_at=END_ASKED_AT), False, id="no-mark-stands"),
            pytest.param(at_the_series_end(1), False, id="no-ask-was-started"),
        ],
    )
    def test_an_ask_stands_while_a_mark_stands_and_a_seated_seat_is_silent(self, table, stands):
        assert new_series_ask_stands(table) is stands


class TestAnswersRunOutOfTime:
    def test_a_series_asks_for_its_answers_only_once_over_and_never_beside_a_proposal(self):
        with pytest.raises(ValueError, match="series that is over"):
            Series(12, 4, new_series_asked_at=END_ASKED_AT)
        with pytest.raises(ValueError, match="no proposal"):
            Series(12, 12, end_proposal=an_end_proposal(1), new_series_asked_at=END_ASKED_AT)

    def test_a_deal_clears_the_ask_of_the_series_before(self):
        table = at_the_series_end(1, 2, 3, asked_at=END_ASKED_AT)

        dealt_table = dealt_next(table, drawn_hand(table, random.Random(3)))  # noqa: S311 - a seeded source makes the deal reproducible

        assert dealt_table.series.new_series_asked_at is None
