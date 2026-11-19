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
from skat.table.series_end import (
    END_ANSWER_SECONDS,
    SeriesEndCommand,
    decide_agree_to_end,
    decide_end_answer_lapse,
    decide_refuse_to_end,
    series_end_payload,
)
from tests.support.played_game import END_ASKED_AT, an_end_proposal, an_entry

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")
TABLE_VERSION = 9
LATER = END_ASKED_AT + timedelta(seconds=10)


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
        with pytest.raises(ValueError, match="proposer of an end agrees"):
            EndProposal(2, frozenset({1}), END_ASKED_AT)

    def test_a_proposal_every_seat_agreed_to_is_no_proposal(self):
        with pytest.raises(ValueError, match="every seat agreed"):
            EndProposal(1, frozenset({1, 2, 3}), END_ASKED_AT)

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
