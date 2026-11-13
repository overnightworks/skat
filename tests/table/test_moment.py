"""What a seat can do at its table follows from the moment its own view shows, and an agent is told when it changes."""

from dataclasses import replace

import pytest

from skat.engine.bidding import Bid, Pass
from skat.engine.deal import Position
from skat.table.member_view import moment_at, moment_recipients
from skat.table.moment import TableMoment, moment_of
from skat.table.records import EndProposal, HandProgress, Series
from skat.table.views import view_of
from tests.support.open_chairs import (
    REARHAND_SEAT,
    after_the_pushing_take,
    after_the_take,
    at_the_ramsch_start,
    before_the_first_card,
    in_a_ramsch_trick,
    in_the_auction,
    sent_away,
)
from tests.support.played_game import between_games, table_in, with_agents

DECLARER, OPPONENT = "account-middlehand", "account-rearhand"


class TestTheMomentOfASeat:
    @pytest.mark.parametrize(
        ("table", "account", "moment"),
        [
            pytest.param(in_the_auction(), DECLARER, TableMoment.AUCTION, id="auction-of-the-bidder"),
            pytest.param(in_the_auction(), OPPONENT, TableMoment.AUCTION, id="auction-of-a-seat-not-on-turn"),
            pytest.param(after_the_take(), DECLARER, TableMoment.DECLARING, id="the-declarer-after-the-take"),
            pytest.param(after_the_take(), OPPONENT, TableMoment.WAITING, id="an-opponent-while-the-declarer-declares"),
            pytest.param(
                table_in(
                    HandProgress((Bid(Position.MIDDLEHAND, 18), Pass(Position.FOREHAND), Pass(Position.REARHAND)))
                ),
                DECLARER,
                TableMoment.DECLARING,
                id="the-declarer-before-the-take",
            ),
            pytest.param(before_the_first_card(), DECLARER, TableMoment.PLAYING, id="the-declarer-plays"),
            pytest.param(before_the_first_card(), OPPONENT, TableMoment.PLAYING, id="an-opponent-plays"),
            pytest.param(at_the_ramsch_start(), OPPONENT, TableMoment.PLAYING, id="a-ramsch-without-pushing-plays"),
            pytest.param(in_a_ramsch_trick(), DECLARER, TableMoment.PLAYING, id="nobody-declares-a-ramsch"),
            pytest.param(after_the_pushing_take(), OPPONENT, TableMoment.PUSHING, id="the-ramsch-stage-of-any-seat"),
            pytest.param(
                sent_away(before_the_first_card(), REARHAND_SEAT), DECLARER, TableMoment.OPEN_CHAIR, id="open"
            ),
            pytest.param(between_games(), DECLARER, TableMoment.RESULT, id="a-result"),
            pytest.param(between_games(1, 2, 3), DECLARER, TableMoment.RESULT, id="a-result-after-all-continued"),
            pytest.param(
                between_games(series=Series(12, 12)), DECLARER, TableMoment.SERIES_END, id="the-end-of-the-series"
            ),
            pytest.param(
                between_games(series=Series(12, 1, ended_early=True)),
                DECLARER,
                TableMoment.SERIES_END,
                id="a-series-ended-early",
            ),
            pytest.param(replace(in_the_auction(), hand=None), DECLARER, TableMoment.WAITING, id="no-hand"),
        ],
    )
    def test_the_moment_follows_the_seats_own_view(self, table, account, moment):
        assert moment_of(view_of(table, account, frozenset())) is moment

    def test_a_pending_early_end_proposal_is_a_moment_of_the_result(self):
        table = between_games(1, 2, 3, proposal=EndProposal(1))

        assert moment_of(view_of(table, OPPONENT, frozenset())) is TableMoment.RESULT


class TestWhoseMomentChanged:
    def test_a_move_that_ends_the_auction_changes_the_moment_of_every_seated_agent(self):
        before = with_agents(in_the_auction(), 1, 2, 3)
        after = with_agents(before_the_first_card(), 1, 2, 3)

        assert moment_recipients(before, after) == {"account-middlehand", "account-rearhand", "account-forehand"}

    def test_a_move_that_keeps_the_moment_tells_nobody(self):
        before = with_agents(in_the_auction(), 1, 2, 3)
        after = replace(before, version=before.version + 1)

        assert moment_recipients(before, after) == frozenset()

    def test_a_person_is_never_told(self):
        assert moment_recipients(in_the_auction(), before_the_first_card()) == frozenset()

    def test_only_the_agents_at_the_table_are_told(self):
        before, after = with_agents(in_the_auction(), 1), with_agents(before_the_first_card(), 1)

        assert moment_recipients(before, after) == {DECLARER}

    def test_an_agent_that_left_or_sat_down_is_told_by_its_standing_and_not_here(self):
        before, after = with_agents(in_the_auction(), 1, 2), with_agents(before_the_first_card(), 2)
        after = replace(
            after, chairs=tuple(replace(chair, occupant=None) if chair.seat == 1 else chair for chair in after.chairs)
        )

        assert moment_recipients(before, after) == {OPPONENT}

    def test_the_moment_of_an_account_at_a_table_is_the_one_of_its_view(self):
        table = before_the_first_card()

        assert moment_at(table, DECLARER) is moment_of(view_of(table, DECLARER, frozenset()))
