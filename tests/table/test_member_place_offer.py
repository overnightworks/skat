"""Who may call whom is one decision: the row a person sees and the outcome of the call are the same function."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skat.table.member_place import (
    BookEntry,
    CallOffer,
    InvitationId,
    InviteRefusal,
    OfferState,
    OpenInvitation,
    call_offer_of,
    control_shown,
    decide_invite,
    offer_of,
)
from skat.table.records import HandProgress, SeatHeld
from tests.support.calls import call_facts
from tests.support.open_chairs import PHASES, REARHAND_SEAT, sent_away
from tests.support.played_game import after_the_first_game, table_in, with_agents

NOW = datetime(2026, 11, 12, 9, tzinfo=UTC)
LASTING = timedelta(seconds=120)
VIEWER = "account-viewer"
OWNER = "account-owner"
AGENT = "account-agent"
OTHER_PERSON = "account-someone-else"


def entry_inviting(inviter, *, expires_at=NOW + LASTING, epoch=0):
    table = table_in(HandProgress())
    return BookEntry(table.id, AGENT, epoch, OpenInvitation("invitation-1", expires_at, OWNER, inviter))


def a_table_with_a_free_chair():
    return sent_away(table_in(HandProgress()), REARHAND_SEAT)


def facts(**changes):
    return call_facts(AGENT, OWNER, VIEWER, **changes)


def seated_agent(table):
    return table.chairs[0].occupant.account_id


def seated_facts(table):
    return call_facts(seated_agent(table), OWNER, VIEWER)


class TestWhatACallComesTo:
    def test_a_member_present_calls_a_listening_agent_whose_owner_is_present_to_a_table_with_a_free_chair(self):
        assert offer_of(facts(), a_table_with_a_free_chair(), None, NOW) is OfferState.AVAILABLE

    @pytest.mark.parametrize(
        ("changes", "refusal"),
        [
            pytest.param({"viewer_present": False}, InviteRefusal.NOT_PRESENT, id="the-viewer-is-not-at-the-table"),
            pytest.param({"viewer_is_member": False}, InviteRefusal.NOT_A_MEMBER, id="the-viewer-is-no-member"),
            pytest.param({"agent_listens": False}, InviteRefusal.NOT_OFFERED, id="the-agent-does-not-listen"),
            pytest.param({"owner_present": False}, InviteRefusal.OWNER_ABSENT, id="the-owner-is-away"),
        ],
    )
    def test_a_fact_against_the_call_refuses_it_with_its_reason(self, changes, refusal):
        assert offer_of(facts(**changes), a_table_with_a_free_chair(), None, NOW) is refusal

    def test_a_table_that_is_not_live_offers_nothing(self):
        assert offer_of(facts(), None, None, NOW) is InviteRefusal.NO_TABLE

    def test_a_table_without_a_free_chair_has_no_room(self):
        assert offer_of(facts(), table_in(HandProgress()), None, NOW) is InviteRefusal.NO_FREE_CHAIR

    @pytest.mark.parametrize("phase", PHASES)
    def test_the_chair_a_running_hand_waits_for_counts_as_free_in_every_phase(self, phase):
        table = sent_away(PHASES[phase](), REARHAND_SEAT)

        assert offer_of(facts(), table, None, NOW) is OfferState.AVAILABLE

    @pytest.mark.parametrize(
        ("held_seat", "offer"),
        [
            pytest.param(1, InviteRefusal.NO_FREE_CHAIR, id="taken"),
            pytest.param(REARHAND_SEAT, OfferState.AVAILABLE, id="free"),
        ],
    )
    def test_an_agent_that_left_a_chair_of_the_running_hand_is_offered_only_that_chair(self, held_seat, offer):
        table = sent_away(PHASES["auction"](), REARHAND_SEAT)
        held = replace(table, progress=replace(table.progress, seats_held=frozenset({SeatHeld(AGENT, held_seat)})))

        assert offer_of(facts(), held, None, NOW) is offer

    def test_a_chair_between_hands_counts_as_free(self):
        between = after_the_first_game(table_in(HandProgress()))
        table = replace(between, chairs=(*between.chairs[:2], replace(between.chairs[2], occupant=None)))

        assert offer_of(facts(), table, None, NOW) is OfferState.AVAILABLE

    @pytest.mark.parametrize(
        "changes",
        [
            pytest.param({}, id="listening-with-its-owner-present"),
            pytest.param({"agent_listens": False}, id="not-listening"),
            pytest.param({"owner_present": False}, id="owner-away"),
            pytest.param({"agent_listens": False, "owner_account": None, "owner_present": False}, id="no-owner-known"),
        ],
    )
    def test_an_agent_that_holds_a_chair_at_the_table_is_here_whether_it_listens_or_its_owner_is_present(self, changes):
        seated = with_agents(a_table_with_a_free_chair(), 1)

        assert offer_of(replace(seated_facts(seated), **changes), seated, None, NOW) is OfferState.HERE

    @pytest.mark.parametrize(
        ("changes", "refusal"),
        [
            pytest.param({"viewer_present": False}, InviteRefusal.NOT_PRESENT, id="the-viewer-is-not-at-the-table"),
            pytest.param({"viewer_is_member": False}, InviteRefusal.NOT_A_MEMBER, id="the-viewer-is-no-member"),
        ],
    )
    def test_a_seated_agent_is_not_here_for_a_person_who_is_absent_or_no_member(self, changes, refusal):
        seated = with_agents(a_table_with_a_free_chair(), 1)

        assert offer_of(replace(seated_facts(seated), **changes), seated, None, NOW) is refusal

    @pytest.mark.parametrize(
        ("changes", "answer"),
        [
            pytest.param({}, OfferState.HERE, id="the-owner-at-the-table"),
            pytest.param({"viewer_present": False}, InviteRefusal.NOT_PRESENT, id="the-owner-is-not-at-the-table"),
            pytest.param({"viewer_account": OTHER_PERSON}, InviteRefusal.NOT_A_MEMBER, id="another-person"),
        ],
    )
    def test_the_owner_of_a_seated_agent_has_it_here_without_being_a_member(self, changes, answer):
        seated = with_agents(a_table_with_a_free_chair(), 1, owner_account=OWNER)
        outside_the_group = replace(call_facts(seated_agent(seated), OWNER, OWNER), viewer_is_member=False)

        assert offer_of(replace(outside_the_group, **changes), seated, None, NOW) is answer

    @pytest.mark.parametrize("stored_owner", [None, OTHER_PERSON], ids=["no-owner-stored", "another-owner"])
    def test_a_person_outside_the_group_has_no_right_to_an_agent_whose_chair_stores_another_owner(self, stored_owner):
        seated = with_agents(a_table_with_a_free_chair(), 1, owner_account=stored_owner)
        outside_the_group = replace(call_facts(seated_agent(seated), OWNER, OWNER), viewer_is_member=False)

        assert offer_of(outside_the_group, seated, None, NOW) is InviteRefusal.NOT_A_MEMBER

    def test_a_seated_agent_is_here_even_when_an_invitation_to_it_stands(self):
        seated = with_agents(a_table_with_a_free_chair(), 1)
        entry = BookEntry(
            seated.id, seated_agent(seated), 0, OpenInvitation("invitation-1", NOW + LASTING, OWNER, VIEWER)
        )

        assert offer_of(seated_facts(seated), seated, entry, NOW) is OfferState.HERE

    def test_an_invitation_of_someone_else_makes_the_agent_not_offered(self):
        entry = entry_inviting(OTHER_PERSON)

        assert offer_of(facts(), a_table_with_a_free_chair(), entry, NOW) is InviteRefusal.NOT_OFFERED

    def test_the_agent_the_viewer_invited_is_inviting_whatever_the_room_or_the_owner(self):
        entry = entry_inviting(VIEWER)
        full = table_in(HandProgress())

        assert offer_of(facts(owner_present=False), full, entry, NOW) is OfferState.INVITING

    def test_an_invitation_that_ran_out_offers_the_agent_again_to_everyone(self):
        entry = entry_inviting(OTHER_PERSON, expires_at=NOW)

        assert offer_of(facts(), a_table_with_a_free_chair(), entry, NOW) is OfferState.AVAILABLE

    def test_the_reasons_are_decided_in_their_order(self):
        full = table_in(HandProgress())
        facts_against = facts(viewer_present=False, viewer_is_member=False, agent_listens=False, owner_present=False)
        mending = [
            {"viewer_present": True},
            {"viewer_is_member": True},
            {"agent_listens": True},
            {"owner_present": True},
        ]
        reasons = [
            InviteRefusal.NOT_PRESENT,
            InviteRefusal.NOT_A_MEMBER,
            InviteRefusal.NOT_OFFERED,
            InviteRefusal.OWNER_ABSENT,
            InviteRefusal.NO_FREE_CHAIR,
        ]

        answered = []
        for mended in [{}, *mending]:
            facts_against = replace(facts_against, **mended)
            answered.append(offer_of(facts_against, full, None, NOW))

        assert answered == reasons


class TestTheControlIsShown:
    @pytest.mark.parametrize(
        ("present", "member", "sends_away", "shown"),
        [
            (True, True, False, True),
            (True, False, False, False),
            (False, True, False, False),
            (False, False, False, False),
            (True, False, True, True),
            (False, False, True, False),
        ],
    )
    def test_to_a_member_or_one_who_may_send_an_agent_away_and_is_at_the_table_and_to_nobody_else(
        self, present, member, sends_away, shown
    ):
        assert control_shown(viewer_present=present, viewer_is_member=member, sends_agent_away=sends_away) is shown


class TestAnInvitingRowTellsWhenItsInvitationEnds:
    @pytest.mark.parametrize(
        ("left", "seconds"),
        [(timedelta(seconds=90), 90), (timedelta(milliseconds=1500), 2), (timedelta(milliseconds=1), 1)],
    )
    def test_in_whole_seconds_rounded_up(self, left, seconds):
        entry = entry_inviting(VIEWER, expires_at=NOW + left)

        assert call_offer_of(facts(), a_table_with_a_free_chair(), entry, NOW) == CallOffer(
            OfferState.INVITING, seconds
        )

    def test_a_here_row_tells_no_end(self):
        seated = with_agents(a_table_with_a_free_chair(), 1)

        assert call_offer_of(seated_facts(seated), seated, None, NOW) == CallOffer(OfferState.HERE)

    def test_a_row_that_is_not_inviting_tells_no_end(self):
        assert call_offer_of(facts(), a_table_with_a_free_chair(), None, NOW) == CallOffer(OfferState.AVAILABLE)


class TestDecidingAnInvite:
    def test_writes_an_invitation_that_expires_after_the_duration_on_the_given_clock(self):
        table = a_table_with_a_free_chair()

        written = decide_invite(table, None, facts(), InvitationId("invitation-1"), NOW, LASTING)

        entry, offer = written
        assert entry.invitation == OpenInvitation("invitation-1", NOW + LASTING, OWNER, VIEWER)
        assert (offer.id, offer.epoch, offer.expires_at) == ("invitation-1", 0, NOW + LASTING)

    def test_keeps_the_epoch_of_the_agents_row(self):
        table = a_table_with_a_free_chair()
        row = BookEntry(table.id, AGENT, 3)

        entry, offer = decide_invite(table, row, facts(), InvitationId("invitation-2"), NOW, LASTING)

        assert (entry.epoch, offer.epoch) == (3, 3)

    def test_the_viewer_who_invited_already_gets_that_invitation_and_nothing_new(self):
        table = a_table_with_a_free_chair()
        row = entry_inviting(VIEWER, epoch=2)

        entry, offer = decide_invite(table, row, facts(), InvitationId("invitation-2"), NOW, LASTING)

        assert entry is row
        assert (offer.id, offer.epoch) == ("invitation-1", 2)

    @pytest.mark.parametrize(
        "changes",
        [{"viewer_present": False}, {"viewer_is_member": False}, {"agent_listens": False}, {"owner_present": False}],
    )
    def test_writes_nothing_for_a_call_that_is_not_offered(self, changes):
        table = a_table_with_a_free_chair()

        assert isinstance(decide_invite(table, None, facts(**changes), InvitationId("i"), NOW, LASTING), InviteRefusal)

    def test_a_seated_agent_is_not_invited(self):
        seated = with_agents(a_table_with_a_free_chair(), 1)

        written = decide_invite(seated, None, seated_facts(seated), InvitationId("i"), NOW, LASTING)

        assert written is InviteRefusal.NOT_OFFERED

    def test_a_table_that_is_not_live_gets_no_invitation(self):
        assert decide_invite(None, None, facts(), InvitationId("i"), NOW, LASTING) is InviteRefusal.NO_TABLE
