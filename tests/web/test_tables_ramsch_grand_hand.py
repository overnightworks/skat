import pytest

from skat.web.declaring import TABLE_DECLARING_DECLARE_SUFFIX
from skat.web.kontra import TABLE_KONTRA_SUFFIX
from skat.web.tables import GameToken
from tests.support.payload_cards import cards_in_text, wire_cards
from tests.web.support.playing import (
    FOREHAND,
    JUNGFRAU_DEAL,
    JUNGFRAU_HAND,
    MIDDLEHAND,
    PLAIN_DEAL,
    PLAIN_HAND,
    REARHAND,
    SWEEP_DEAL,
    SWEEP_HAND,
    Table,
    bock_of,
    cards,
)
from tests.web.support.ramsch_stage import (
    FOREHAND_SEAT,
    MIDDLEHAND_SEAT,
    POINTS,
    REARHAND_SEAT,
    SUFFIXES,
    VIEWERS,
    accepted,
    list_rows,
    play_stage,
    read,
    refused,
    stage_table,
)
from tests.web.support.series import headers_of, tap_weiter


def grand_hand_table(skat, deal=PLAIN_DEAL, **changed):
    """A table whose stage lets a seat declare a Grand Hand instead of the Ramsch."""
    return stage_table(skat, deal=deal, grand_hand="allowed", **changed)


def declared_through_the_auction(skat, deal, game):
    """The same cards played as a Grand Hand middlehand declared after winning the auction at the lowest bid."""
    table = Table(skat, {"ramsch": POINTS})
    table.with_deal(deal)
    table.declared_hand_game(GameToken.GRAND)
    table.played_out(game)
    return table


WHO_DECLARES = [
    pytest.param(FOREHAND, (), id="forehand-first"),
    pytest.param(MIDDLEHAND, ("push",), id="middlehand-after-a-push"),
    pytest.param(REARHAND, ("push", "push"), id="rearhand-after-two-pushes"),
    pytest.param(REARHAND, ("back", "push"), id="rearhand-after-a-take-and-a-push"),
]


class TestDeclaringAGrandHandInstead:
    @pytest.mark.parametrize(("position", "earlier"), WHO_DECLARES)
    def test_the_seat_on_turn_fixes_a_grand_hand_by_itself_at_the_lowest_bid_and_the_ramsch_is_off(
        self, skat, position, earlier
    ):
        table = grand_hand_table(skat)
        play_stage(table, *earlier)

        accepted(table, position, "grand-hand")

        seat = {FOREHAND: FOREHAND_SEAT, MIDDLEHAND: MIDDLEHAND_SEAT, REARHAND: REARHAND_SEAT}[position]
        for viewer in VIEWERS:
            hand = read(table, viewer)["hand"]
            assert (hand["ramsch"], hand["pushing"], hand["pushes"], hand["skat_count"]) == (False, None, 0, 2)
            assert hand["declaring"] == {
                "declarer_seat": seat,
                "stage": "declared",
                "declaration": {"game": "grand", "hand": True, "ouvert": False, "announcement": "none"},
                "open_cards": [],
            }
            assert hand["playing"]["turn_seat"] == FOREHAND_SEAT
        assert read(table)["result"] is None

    def test_the_cards_are_the_ones_the_stage_left_and_nobody_names_the_skat(self, skat):
        table = grand_hand_table(skat)
        accepted(table, FOREHAND, "take")
        accepted(table, FOREHAND, "put-back", cards("C7 C8"))
        accepted(table, MIDDLEHAND, "grand-hand")

        named = {
            position: cards_in_text(table.read_as(table.watcher if position is None else table.at[position]).text)
            for position in VIEWERS
        }

        assert named == {
            FOREHAND: wire_cards(cards("C9 CT CJ CQ CK CA S7 S8 DK DA")),
            MIDDLEHAND: wire_cards(PLAIN_DEAL.middlehand),
            REARHAND: wire_cards(PLAIN_DEAL.rearhand),
            None: set(),
        }

    def test_the_stage_log_ends_with_the_step_and_a_retry_stores_it_once(self, skat):
        table = grand_hand_table(skat)
        accepted(table, FOREHAND, "push")
        retry = {"command_id": "retry-0001", "version": table.record.version}

        first = table.act(SUFFIXES["grand-hand"], table.at[MIDDLEHAND], body=retry)
        again = table.act(SUFFIXES["grand-hand"], table.at[MIDDLEHAND], body=retry)

        assert (again.status_code, again.json()) == (first.status_code, first.json())
        assert [type(each).__name__ for each in table.record.progress.pushing] == ["Push", "DeclareGrandHand"]

    @pytest.mark.parametrize(
        ("before", "position", "reason"),
        [
            pytest.param((), MIDDLEHAND, "not-your-turn", id="out-of-turn"),
            pytest.param(((FOREHAND, "take"),), FOREHAND, "out-of-order", id="after-a-take-before-the-put-back"),
            pytest.param(((FOREHAND, "take"),), MIDDLEHAND, "not-your-turn", id="another-seat-after-a-take"),
        ],
    )
    def test_the_engines_refusals_come_back_and_leave_the_table_as_it_was(self, skat, before, position, reason):
        table = grand_hand_table(skat)
        for earlier_position, earlier_kind in before:
            accepted(table, earlier_position, earlier_kind)

        refused(table, position, "grand-hand", reason)

    def test_the_table_refuses_a_watcher_a_stale_version_and_a_step_after_the_stage_or_the_declaration(self, skat):
        after_the_stage = grand_hand_table(skat)
        play_stage(after_the_stage, "push", "push", "push")
        declared = grand_hand_table(skat)
        accepted(declared, FOREHAND, "grand-hand")
        fresh = grand_hand_table(skat)
        before = fresh.record

        fresh.refused_act(SUFFIXES["grand-hand"], fresh.watcher, "not-seated")
        fresh.refused_act(
            SUFFIXES["grand-hand"], fresh.at[FOREHAND], "stale-version", body={"version": before.version - 1}
        )
        refused(after_the_stage, FOREHAND, "grand-hand", "wrong-phase")
        refused(declared, FOREHAND, "grand-hand", "wrong-phase")
        refused(declared, FOREHAND, "take", "wrong-phase")

    @pytest.mark.parametrize(
        "table_of",
        [
            pytest.param(lambda skat: stage_table(skat, grand_hand="off"), id="off"),
            pytest.param(lambda skat: stage_table(skat), id="left-out"),
            pytest.param(lambda skat: stage_table(skat, rule=None), id="a-table-without-pushing"),
        ],
    )
    def test_a_table_that_does_not_allow_it_refuses_the_step_as_wrong_phase(self, skat, table_of):
        table = table_of(skat)

        refused(table, FOREHAND, "grand-hand", "wrong-phase")
        refused(table, MIDDLEHAND, "grand-hand", "wrong-phase")

    @pytest.mark.parametrize("announcement", ["schneider", "schwarz", "none"])
    def test_a_declaration_or_an_announcement_after_it_is_refused_as_already_declared(self, skat, announcement):
        table = grand_hand_table(skat)
        accepted(table, FOREHAND, "grand-hand")
        body = {"game": "grand", "hand": True, "ouvert": False, "announcement": announcement}

        table.refused_act(TABLE_DECLARING_DECLARE_SUFFIX, table.at[FOREHAND], "already-declared", body=body)

    @pytest.mark.parametrize(
        ("deal", "game"),
        [
            pytest.param(PLAIN_DEAL, PLAIN_HAND, id="lost-with-schneider-reached-by-the-opponents"),
            pytest.param(JUNGFRAU_DEAL, JUNGFRAU_HAND, id="won-with-schneider-reached-by-the-declarer"),
            pytest.param(SWEEP_DEAL, SWEEP_HAND, id="lost-with-schwarz-reached-by-the-opponents"),
        ],
    )
    def test_it_is_reckoned_and_listed_as_the_grand_hand_the_auction_would_have_declared(self, skat, deal, game):
        wanted = declared_through_the_auction(skat, deal, game)
        table = grand_hand_table(skat, deal=deal)
        play_stage(table, "push")
        accepted(table, MIDDLEHAND, "grand-hand")

        table.played_out(game)

        result = table.result()
        assert result == wanted.result()
        assert (result["kind"], result["hand"], result["bid"], result["announcement"]) == ("declared", True, 18, "none")
        assert "pushes" not in result
        row, wanted_row = (list_rows(each)[0] | {"declarer_name": None} for each in (table, wanted))
        assert row == wanted_row
        assert (row["kind"], row["game"], row["hand"], row["announcement"]) == ("declared", "grand", True, "none")

    def test_a_won_grand_hand_triggers_bock_and_an_opponent_may_say_kontra_as_at_any_declared_game(self, skat):
        table = grand_hand_table(
            skat,
            deal=JUNGFRAU_DEAL,
            extra={
                "bock": {"triggers": ["won-grand-hand"], "overlap": "append"},
                "kontra": {"sayer": "any-opponent", "reach": "kontra-re", "deadline": "own-card"},
            },
        )
        play_stage(table, "push")
        accepted(table, MIDDLEHAND, "grand-hand")

        said = table.act(TABLE_KONTRA_SUFFIX, table.at[REARHAND], body={"word": "kontra"})
        table.played_out(JUNGFRAU_HAND)

        assert said.status_code == 200, said.text
        assert table.result()["kontra"]["word"] == "kontra"
        assert bock_of(table) == {"games_left": 3, "factor": 2}

    def test_nobody_bid_so_a_table_that_lets_only_bidders_say_kontra_has_no_kontra_here(self, skat):
        table = grand_hand_table(
            skat, extra={"kontra": {"sayer": "bidders-only", "reach": "kontra-re", "deadline": "own-card"}}
        )
        accepted(table, FOREHAND, "grand-hand")

        table.refused_act(TABLE_KONTRA_SUFFIX, table.at[MIDDLEHAND], "did-not-bid", body={"word": "kontra"})

    def test_weiter_after_the_grand_hand_deals_a_hand_whose_stage_starts_with_no_step(self, skat):
        table = grand_hand_table(skat)
        accepted(table, FOREHAND, "grand-hand")
        table.played_out(PLAIN_HAND)

        tapped = tap_weiter(skat, headers_of(table)[0], table.table_id, "tap-0001")

        assert tapped.status_code == 200, tapped.text
        assert table.record.progress.pushing == ()
