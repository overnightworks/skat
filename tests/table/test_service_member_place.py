"""A table is a member place: an agent is a member exactly while it holds a chair or an invitation to it is open."""

import copy
import itertools
import random
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skat.table.member_place import (
    ENDED_CALL_KEPT,
    Acceptance,
    CallOffer,
    CallOutcome,
    InvitationOffer,
    InviteRefusal,
    MemberRefusal,
    MembershipState,
    OfferState,
    SeatedOffer,
    TableStanding,
)
from skat.table.records import Actor, CreateTable, HandProgress, OccupantKind, Series, SitDown, StandUp, TableId
from skat.table.rules import decide_free_chair
from skat.table.service import TableService
from tests.support.calls import call_facts
from tests.support.fake_tables import FakeTableStore
from tests.support.faulty_tables import FaultyTableTransactions
from tests.support.played_game import after_the_first_game

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
MOZART = Actor(account_id="account-mozart", display_name="Mozart", kind=OccupantKind.AGENT)
BACH = Actor(account_id="account-bach", display_name="Bach", kind=OccupantKind.AGENT)
OWNER = OPENER.account_id
START = datetime(2026, 11, 1, 12, tzinfo=UTC)
INVITATION_SECONDS = 600
NOBODY = frozenset()
UNKNOWN_TABLE = "0" * 32


def seated_facts(account):
    return replace(call_facts(account, OWNER), agent_listens=False, owner_account=None, owner_present=False)


class Scene:
    """A seeded service on a clock the test moves: Anna opened a table, and Mozart's owner is Anna."""

    def __init__(self) -> None:
        self.store = FakeTableStore()
        self.now = START
        self.commands = itertools.count(1)
        numbers = itertools.count(1)
        self.service = TableService(
            self.store,
            new_table_id=lambda: TableId(f"{next(numbers):032x}"),
            random_source=random.Random(1),  # noqa: S311 - a seeded source makes the deal reproducible
            now=lambda: self.now,
        )
        self.signals: list[tuple[frozenset[str], tuple[TableStanding, ...]]] = []
        self.service = self.service.with_standing_signal(self._record_signal)
        self.table_id = self.service.create(OPENER, CreateTable(command_id="command-open")).id
        self.signals.clear()

    def _record_signal(self, accounts: frozenset[str]) -> None:
        """What the store shows an agent at the moment it is told: a signal comes after its commit."""
        shown = tuple(standing for account in sorted(accounts) for standing in self.service.standings_of(account))
        self.signals.append((accounts, shown))

    @property
    def table(self):
        return self.store.tables[self.table_id]

    def invite(self, agent=MOZART, *, owner=OWNER, inviter=OWNER, lasting=INVITATION_SECONDS, table_id=None, **facts):
        return self.service.invite_agent(
            TableId(table_id or self.table_id),
            call_facts(agent.account_id, owner, inviter, **facts),
            timedelta(seconds=lasting),
        )

    def accept(self, offer, agent=MOZART, *, owner=OWNER, connected=frozenset({OWNER}), **changes):
        arguments = {"table_id": self.table_id, "invitation_id": offer.id, "epoch": offer.epoch, **changes}
        return self.service.accept_invitation(agent, owner, Acceptance(**arguments), connected)

    def sit(self, person, seat):
        return self.service.sit(person, SitDown(f"command-{next(self.commands)}", self.table_id, seat), NOBODY)

    def stand(self, person):
        return self.service.stand(person, StandUp(f"command-{next(self.commands)}", self.table_id), NOBODY)

    def standing(self, agent=MOZART):
        return self.service.standings_of(agent.account_id)

    def book(self, agent=MOZART):
        with self.store.begin() as transaction:
            return transaction.locked_book_entry(TableId(self.table_id), agent.account_id)

    def offers_to_the_caller(self, **facts):
        calls = [call_facts(MOZART.account_id, OWNER, **facts)]
        (offer,) = self.service.offers_at(TableId(self.table_id), calls, seated_facts).listed
        return offer

    def occupants(self):
        return [None if chair.occupant is None else chair.occupant.display_name for chair in self.table.chairs]

    def at(self, moment: datetime) -> Scene:
        self.now = moment
        return self

    def snapshot(self):
        return copy.deepcopy((self.store.tables, self.store.book))


@pytest.fixture
def scene():
    return Scene()


def active_standing(scene):
    return TableStanding(TableId(scene.table_id), MembershipState.ACTIVE)


def invited_standing(scene, offer):
    return TableStanding(TableId(scene.table_id), MembershipState.INVITED, offer)


class TestInviteAnAgent:
    def test_an_invitation_shows_in_the_agents_standing_with_its_id_epoch_and_expiry(self, scene):
        offer = scene.invite()

        assert isinstance(offer, InvitationOffer)
        assert (offer.epoch, offer.expires_at) == (0, START + timedelta(seconds=INVITATION_SECONDS))
        assert scene.standing() == (invited_standing(scene, offer),)

    def test_no_other_agent_stands_at_the_table(self, scene):
        scene.invite()

        assert scene.standing(BACH) == ()

    @pytest.mark.parametrize(
        ("arrange", "inviter"),
        [
            pytest.param(lambda scene: scene.invite(inviter=VISITOR.account_id), OWNER, id="someone-else-invited-it"),
            pytest.param(lambda scene: scene.sit(MOZART, 2), OWNER, id="the-agent-holds-a-chair"),
        ],
    )
    def test_is_refused_and_writes_nothing_when_the_agent_is_invited_by_someone_else_or_seated(
        self, scene, arrange, inviter
    ):
        arrange(scene)
        before = scene.snapshot()

        assert scene.invite(inviter=inviter) is InviteRefusal.NOT_OFFERED
        assert scene.snapshot() == before

    @pytest.mark.parametrize(
        ("facts", "refusal"),
        [
            ({"viewer_present": False}, InviteRefusal.NOT_PRESENT),
            ({"viewer_is_member": False}, InviteRefusal.NOT_A_MEMBER),
            ({"agent_listens": False}, InviteRefusal.NOT_OFFERED),
            ({"owner_present": False}, InviteRefusal.OWNER_ABSENT),
        ],
    )
    def test_is_refused_and_writes_nothing_when_a_fact_of_the_call_is_against_it(self, scene, facts, refusal):
        before = scene.snapshot()

        assert scene.invite(**facts) is refusal
        assert scene.snapshot() == before

    def test_is_refused_and_writes_nothing_when_no_chair_is_free(self, scene):
        scene.sit(VISITOR, 2)
        scene.sit(CLEO, 3)
        before = scene.snapshot()

        assert scene.invite() is InviteRefusal.NO_FREE_CHAIR
        assert scene.snapshot() == before

    def test_the_expiry_is_the_duration_after_the_services_own_clock(self, scene):
        scene.at(START + timedelta(minutes=7))

        offer = scene.invite(lasting=45)

        assert offer.expires_at == START + timedelta(minutes=7, seconds=45)

    def test_the_inviter_who_asks_again_gets_the_open_invitation_and_nothing_is_written_or_told(self, scene):
        first = scene.invite()
        before = scene.snapshot()
        scene.signals.clear()

        again = scene.invite(lasting=5)

        assert again == first
        assert scene.snapshot() == before
        assert scene.signals == []

    @pytest.mark.parametrize("table_id", [UNKNOWN_TABLE, "not-a-table"])
    def test_is_refused_for_a_table_that_is_not_live(self, scene, table_id):
        assert scene.invite(table_id=table_id) is InviteRefusal.NO_TABLE
        assert scene.book() is None

    def test_is_refused_for_a_table_that_ended(self, scene):
        scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 60)

        assert scene.invite() is InviteRefusal.NO_TABLE

    def test_an_invitation_that_ran_out_is_replaced_by_a_new_one(self, scene):
        first = scene.invite()
        scene.at(START + timedelta(seconds=INVITATION_SECONDS))

        second = scene.invite()

        assert isinstance(second, InvitationOffer)
        assert second.id != first.id
        assert scene.standing() == (invited_standing(scene, second),)


class TestOffersAtATable:
    def offers(self, scene, *agents, table_id=None, **facts):
        calls = [call_facts(agent.account_id, OWNER, **facts) for agent in agents]
        return scene.service.offers_at(TableId(table_id or scene.table_id), calls, seated_facts)

    def test_each_agent_has_its_own_offer_from_one_read(self, scene):
        scene.invite(MOZART)

        offers = self.offers(scene, MOZART, BACH)

        assert offers.listed == (CallOffer(OfferState.INVITING, INVITATION_SECONDS), CallOffer(OfferState.AVAILABLE))

    def test_an_inviting_row_counts_down_on_the_services_clock(self, scene):
        scene.invite(MOZART)
        scene.at(START + timedelta(seconds=INVITATION_SECONDS - 30))

        assert self.offers(scene, MOZART).listed == (CallOffer(OfferState.INVITING, 30),)

    def test_an_invitation_that_ran_out_is_available_again_with_its_outcome_and_the_read_forgets_nothing(self, scene):
        scene.invite(MOZART)
        scene.at(START + timedelta(seconds=INVITATION_SECONDS))
        before = scene.snapshot()

        assert self.offers(scene, MOZART).listed == (CallOffer(OfferState.AVAILABLE, outcome=CallOutcome.NO_ANSWER),)
        assert scene.snapshot() == before

    @pytest.mark.parametrize("table_id", [UNKNOWN_TABLE, "not-a-table"])
    def test_a_table_that_is_not_live_has_no_offers(self, scene, table_id):
        assert self.offers(scene, MOZART, table_id=table_id) is None

    def test_a_table_that_ended_has_no_offers(self, scene):
        scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 60)

        assert self.offers(scene, MOZART) is None

    def test_a_seated_agent_the_calls_do_not_name_is_answered_with_its_chairs_name_and_a_here_offer(self, scene):
        scene.sit(MOZART, 2)

        offers = self.offers(scene, BACH)

        assert offers.seated == (SeatedOffer(MOZART.account_id, "Mozart", CallOffer(OfferState.HERE)),)

    def test_a_seated_agent_the_calls_name_is_not_answered_twice(self, scene):
        scene.sit(MOZART, 2)

        offers = self.offers(scene, MOZART)

        assert (offers.listed, offers.seated) == ((CallOffer(OfferState.HERE),), ())

    def test_a_person_seated_at_the_table_is_no_seated_agent(self, scene):
        scene.sit(VISITOR, 2)

        assert self.offers(scene).seated == ()


class TestAnAcceptSeatsTheAgent:
    def test_the_agent_holds_the_lowest_free_chair_at_once_and_the_invitation_is_gone(self, scene):
        scene.sit(VISITOR, 2)
        offer = scene.invite()

        result = scene.accept(offer)

        assert result.refusal is None
        assert scene.occupants() == ["Anna", "Ben", "Mozart"]
        assert scene.standing() == (active_standing(scene),)

    def test_the_chair_reads_agent_and_the_table_version_rises_as_for_a_sit(self, scene):
        offer = scene.invite()
        version = scene.table.version

        scene.accept(offer)

        chair = scene.table.chairs[1]
        assert (chair.occupant.display_name, chair.occupant.kind) == ("Mozart", OccupantKind.AGENT)
        assert scene.table.version == version + 1

    def test_takes_the_first_chair_when_the_opener_stood_up_from_it(self, scene):
        scene.sit(VISITOR, 3)
        scene.stand(OPENER)
        offer = scene.invite()

        scene.accept(offer, connected=frozenset({OWNER}))

        assert scene.occupants() == ["Mozart", None, "Ben"]

    def test_an_owner_who_only_watches_the_open_table_is_present(self, scene):
        scene.stand(OPENER)
        offer = scene.invite()

        result = scene.accept(offer, connected=frozenset({OWNER}))

        assert result.refusal is None

    def test_an_agent_that_sits_at_another_table_is_seated_here_too(self, scene):
        other = scene.service.create(MOZART, CreateTable(command_id="command-mozart")).id
        offer = scene.invite()

        scene.accept(offer)

        held = {standing.table_id.value for standing in scene.standing()}
        assert held == {other, scene.table_id}

    def test_the_invitation_ends_and_keeps_neither_person(self, scene):
        offer = scene.invite()

        scene.accept(offer)

        entry = scene.book()
        assert (entry.epoch, entry.invitation) == (0, None)

    def test_the_agent_stays_a_member_when_its_owner_leaves_afterwards(self, scene):
        offer = scene.invite()
        scene.accept(offer)

        scene.stand(OPENER)

        assert scene.standing() == (active_standing(scene),)

    def test_a_retry_of_the_accept_is_stale(self, scene):
        offer = scene.invite()
        scene.accept(offer)

        assert scene.accept(offer).refusal is MemberRefusal.STALE_INVITATION


class TestTheAcceptThatFillsTheThirdChair:
    @pytest.fixture
    def offer(self, scene):
        scene.sit(VISITOR, 2)
        return scene.invite()

    def test_deals_the_hand_as_a_sit_does_with_its_last_played_time(self, scene, offer):
        scene.at(START + timedelta(seconds=60))

        scene.accept(offer, connected=frozenset({OWNER}))

        assert scene.table.hand is not None
        assert scene.store.last_played_at[scene.table_id] == START + timedelta(seconds=60)
        assert scene.store.empty_since_by_table[scene.table_id] is None

    def test_deals_nothing_while_a_chair_stays_free(self, scene):
        offer = scene.invite()

        scene.accept(offer)

        assert (scene.table.hand, scene.table_id in scene.store.last_played_at) == (None, False)

    def test_counts_the_agent_as_ready_while_a_games_result_is_pending(self, scene, offer):
        scene.sit(CLEO, 3)
        scene.store.tables[scene.table_id] = after_the_first_game(scene.table)
        scene.store.tables[scene.table_id] = decide_free_chair(scene.table, CLEO.account_id).table

        result = scene.accept(offer)

        assert result.result_pending is True
        assert [(chair.occupant.display_name, chair.ready) for chair in scene.table.chairs] == [
            ("Anna", False),
            ("Ben", False),
            ("Mozart", True),
        ]
        assert scene.table.hand is None

    def test_deals_nothing_and_marks_nobody_at_a_series_end(self, scene, offer):
        scene.sit(CLEO, 3)
        scene.store.tables[scene.table_id] = after_the_first_game(scene.table)
        scene.store.tables[scene.table_id] = decide_free_chair(scene.table, CLEO.account_id).table
        scene.store.tables[scene.table_id] = replace(scene.table, series=Series(3, 3))

        scene.accept(offer)

        assert (scene.table.hand, [chair.ready for chair in scene.table.chairs]) == (None, [False, False, False])


class TestTheAcceptDuringARunningHand:
    @pytest.fixture
    def left_chair_two(self, scene):
        """The agent held chair 2 of the hand Anna (1) and Ben (3) played with it, and stood up from it."""
        scene.sit(VISITOR, 3)
        scene.sit(MOZART, 2)
        scene.stand(MOZART)
        return scene

    def test_the_agent_sits_in_the_chair_it_held_when_it_is_free_though_a_lower_chair_is_free_too(self, left_chair_two):
        scene = left_chair_two
        scene.stand(OPENER)
        offer = scene.invite()

        result = scene.accept(offer)

        assert result.refusal is None
        assert scene.occupants() == [None, "Mozart", "Ben"]

    def test_the_agent_is_busy_when_the_chair_it_held_is_taken_though_another_is_free(self, left_chair_two):
        scene = left_chair_two
        offer = scene.invite()
        scene.sit(CLEO, 2)
        scene.stand(OPENER)
        before = scene.table

        result = scene.accept(offer)

        assert result.refusal is MemberRefusal.BUSY
        assert (scene.table, scene.standing(), scene.book().invitation.ended) == (before, (), CallOutcome.BUSY)

    def test_an_agent_that_held_no_chair_of_the_hand_takes_the_lowest_free_chair(self, scene):
        scene.sit(VISITOR, 2)
        scene.sit(CLEO, 3)
        scene.stand(OPENER)
        scene.stand(VISITOR)
        offer = scene.invite()

        scene.accept(offer)

        assert scene.occupants() == ["Mozart", None, "Cleo"]

    def test_the_agent_takes_any_free_chair_once_the_hand_is_over(self, left_chair_two):
        scene = left_chair_two
        scene.store.tables[scene.table_id] = replace(scene.table, hand=None, progress=HandProgress())
        scene.stand(OPENER)
        offer = scene.invite()

        scene.accept(offer)

        assert scene.occupants() == ["Mozart", None, "Ben"]


class TestStaleInvitation:
    """Nothing changes: not the table, not the book, and an open invitation stays open."""

    @pytest.mark.parametrize(
        "changes",
        [
            pytest.param({"invitation_id": "another-id"}, id="another-id"),
            pytest.param({"epoch": 1}, id="another-epoch"),
            pytest.param({"table_id": UNKNOWN_TABLE}, id="a-table-that-does-not-exist"),
            pytest.param({"table_id": "not-a-table"}, id="a-table-id-that-is-no-id"),
        ],
    )
    def test_when_the_arguments_do_not_name_the_open_invitation(self, scene, changes):
        offer = scene.invite()
        before = scene.snapshot()

        result = scene.accept(offer, **changes)

        assert result.refusal is MemberRefusal.STALE_INVITATION
        assert scene.snapshot() == before
        assert scene.standing() == (invited_standing(scene, offer),)

    def test_when_the_invitation_ran_out_on_the_services_clock(self, scene):
        offer = scene.invite()
        scene.at(START + timedelta(seconds=INVITATION_SECONDS))
        before = scene.snapshot()

        assert scene.accept(offer).refusal is MemberRefusal.STALE_INVITATION
        assert scene.snapshot() == before

    def test_when_the_table_ended(self, scene):
        offer = scene.invite()
        scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 60)

        assert scene.accept(offer).refusal is MemberRefusal.STALE_INVITATION

    def test_when_another_agent_accepts(self, scene):
        offer = scene.invite()
        before = scene.snapshot()

        result = scene.accept(offer, agent=BACH)

        assert result.refusal is MemberRefusal.STALE_INVITATION
        assert scene.snapshot() == before

    @pytest.mark.parametrize("owner", [None, "account-someone-else"], ids=["a-token-without-an-owner", "another-owner"])
    def test_when_the_owner_of_the_token_is_not_the_owner_of_the_invitation(self, scene, owner):
        offer = scene.invite()
        before = scene.snapshot()

        assert scene.accept(offer, owner=owner).refusal is MemberRefusal.STALE_INVITATION
        assert scene.snapshot() == before

    def test_when_the_agent_sat_down_by_the_tables_link_first(self, scene):
        offer = scene.invite()
        scene.sit(MOZART, 3)
        before = scene.snapshot()

        assert scene.accept(offer).refusal is MemberRefusal.STALE_INVITATION
        assert scene.snapshot() == before
        assert scene.standing() == (active_standing(scene),)

    def test_is_answered_before_the_owner_is_checked(self, scene):
        offer = scene.invite()

        result = scene.accept(offer, connected=NOBODY, invitation_id="another-id")

        assert result.refusal is MemberRefusal.STALE_INVITATION
        assert scene.standing() == (invited_standing(scene, offer),)


class TestSponsorAway:
    @pytest.mark.parametrize(
        "connected",
        [NOBODY, frozenset({VISITOR.account_id})],
        ids=["nobody-is-at-the-table", "only-another-person-is"],
    )
    def test_when_the_owner_has_no_stream_on_the_table_and_the_invitation_ends(self, scene, connected):
        offer = scene.invite()
        before = scene.table

        result = scene.accept(offer, connected=connected)

        assert result.refusal is MemberRefusal.SPONSOR_AWAY
        assert scene.table == before
        assert scene.standing() == ()
        assert scene.book().invitation.ended is CallOutcome.OWNER_ABSENT
        assert scene.offers_to_the_caller(owner_present=False) == CallOffer(
            InviteRefusal.OWNER_ABSENT, outcome=CallOutcome.OWNER_ABSENT
        )

    def test_when_the_owner_is_seated_but_away(self, scene):
        offer = scene.invite()

        result = scene.accept(offer, connected=NOBODY)

        assert scene.table.chairs[0].occupant.account_id == OWNER
        assert result.refusal is MemberRefusal.SPONSOR_AWAY

    def test_is_answered_before_the_table_is_found_full(self, scene):
        offer = scene.invite()
        scene.sit(VISITOR, 2)
        scene.sit(CLEO, 3)

        assert scene.accept(offer, connected=NOBODY).refusal is MemberRefusal.SPONSOR_AWAY


class TestBusy:
    def test_when_no_chair_is_free_and_the_invitation_ends(self, scene):
        offer = scene.invite()
        scene.sit(VISITOR, 2)
        scene.sit(CLEO, 3)
        before = scene.table

        result = scene.accept(offer)

        assert result.refusal is MemberRefusal.BUSY
        assert scene.table == before
        assert scene.standing() == ()
        assert scene.book().invitation.ended is CallOutcome.BUSY
        assert scene.offers_to_the_caller() == CallOffer(InviteRefusal.NO_FREE_CHAIR, outcome=CallOutcome.BUSY)

    def test_a_new_invitation_to_the_same_agent_works_after_a_refusal(self, scene):
        offer = scene.invite()
        scene.accept(offer, connected=NOBODY)

        assert isinstance(scene.invite(), InvitationOffer)


class TestTheStandingFollowsTheChair:
    def test_an_agent_that_sat_by_the_link_or_opened_a_table_is_active(self, scene):
        scene.sit(MOZART, 2)
        opened = scene.service.create(MOZART, CreateTable(command_id="command-mozart")).id

        assert {standing.table_id.value: standing.state for standing in scene.standing()} == {
            scene.table_id: MembershipState.ACTIVE,
            opened: MembershipState.ACTIVE,
        }

    def test_an_agent_that_stood_up_is_absent_and_sits_again(self, scene):
        scene.sit(MOZART, 2)
        scene.stand(MOZART)

        assert scene.standing() == ()
        assert scene.sit(MOZART, 2).refusal is None
        assert scene.standing() == (active_standing(scene),)

    def test_the_holds_freeing_of_the_chair_ends_the_membership(self, scene):
        scene.sit(MOZART, 2)

        assert scene.service.free_chair(TableId(scene.table_id), MOZART.account_id, nullcontext(True)) is True

        assert scene.standing() == ()

    def test_the_holds_freeing_keeps_an_agents_chair_and_its_standing_at_a_dealt_table_between_games(self, scene):
        scene.sit(VISITOR, 2)
        scene.sit(MOZART, 3)
        scene.store.tables[scene.table_id] = after_the_first_game(scene.table)
        scene.signals.clear()
        before = scene.snapshot()

        freed = scene.service.free_chair(TableId(scene.table_id), MOZART.account_id, nullcontext(True))

        assert freed is False
        assert (scene.snapshot(), scene.standing(), scene.signals) == (before, (active_standing(scene),), [])

    def test_the_end_of_the_table_ends_the_membership_and_removes_its_book_rows(self, scene):
        scene.invite(BACH)
        scene.sit(MOZART, 2)
        scene.stand(OPENER)

        assert scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 60) is True

        assert (scene.standing(), scene.standing(BACH)) == ((), ())
        assert scene.store.book == {}

    def test_an_invitation_to_an_agent_that_holds_a_chair_shows_only_the_chair(self, scene):
        scene.invite()
        scene.sit(MOZART, 3)

        assert scene.standing() == (active_standing(scene),)


class TestAnExpiredInvitation:
    def test_is_absent_at_the_next_read_and_the_caller_is_told_it_ran_out_unanswered(self, scene):
        scene.invite()
        scene.at(START + timedelta(seconds=INVITATION_SECONDS))

        assert scene.standing() == ()
        assert scene.offers_to_the_caller() == CallOffer(OfferState.AVAILABLE, outcome=CallOutcome.NO_ANSWER)

    def test_is_forgotten_with_its_two_people_by_the_read_after_the_outcome_is_kept(self, scene):
        scene.invite()
        scene.at(START + timedelta(seconds=INVITATION_SECONDS) + ENDED_CALL_KEPT)

        assert scene.standing() == ()
        assert scene.book().invitation is None

    def test_an_invite_to_the_pair_clears_the_ids_of_the_old_one_by_replacing_them(self, scene):
        scene.invite(inviter="account-first")
        scene.at(START + timedelta(seconds=INVITATION_SECONDS))

        scene.invite(inviter="account-second")

        assert scene.book().invitation.inviter_account == "account-second"

    def test_signals_nothing(self, scene):
        scene.invite()
        scene.signals.clear()

        scene.at(START + timedelta(seconds=INVITATION_SECONDS))

        assert scene.signals == []


class TestSignals:
    """Every written change of an agent's standing is signalled after its commit, to the agents it concerns."""

    def test_an_invitation_signals_the_agent_who_then_reads_it(self, scene):
        offer = scene.invite()

        assert scene.signals == [(frozenset({MOZART.account_id}), (invited_standing(scene, offer),))]

    def test_an_accept_signals_the_agent_who_then_reads_the_table_active(self, scene):
        offer = scene.invite()
        scene.signals.clear()

        scene.accept(offer)

        assert scene.signals == [(frozenset({MOZART.account_id}), (active_standing(scene),))]

    @pytest.mark.parametrize(
        "refuse",
        [
            pytest.param(lambda scene, offer: scene.accept(offer, connected=NOBODY), id="sponsor-away"),
            pytest.param(lambda scene, offer: scene.accept(offer, owner=None), id="stale"),
        ],
    )
    def test_a_refusal_signals_only_when_it_ended_the_invitation(self, scene, refuse):
        offer = scene.invite()
        scene.signals.clear()

        result = refuse(scene, offer)

        ended = result.refusal is MemberRefusal.SPONSOR_AWAY
        assert [accounts for accounts, _ in scene.signals] == ([frozenset({MOZART.account_id})] if ended else [])

    def test_an_agents_sit_stand_and_opening_signal_it_and_a_persons_signal_nobody(self, scene):
        scene.sit(VISITOR, 2)
        scene.stand(VISITOR)
        assert scene.signals == []

        scene.sit(MOZART, 2)
        scene.stand(MOZART)
        scene.service.create(MOZART, CreateTable(command_id="command-mozart"))

        assert [accounts for accounts, _ in scene.signals] == [frozenset({MOZART.account_id})] * 3

    def test_the_holds_freeing_signals_the_agent_who_then_reads_it_absent(self, scene):
        scene.sit(MOZART, 2)
        scene.signals.clear()

        scene.service.free_chair(TableId(scene.table_id), MOZART.account_id, nullcontext(True))

        assert scene.signals == [(frozenset({MOZART.account_id}), ())]

    def test_the_end_of_the_table_signals_every_agent_that_sat_or_was_invited_there(self, scene):
        scene.invite(BACH)
        scene.sit(MOZART, 2)
        scene.stand(OPENER)
        scene.signals.clear()

        scene.service.end_empty_table(TableId(scene.table_id), nullcontext(NOBODY), 60)

        assert scene.signals == [(frozenset({MOZART.account_id, BACH.account_id}), ())]

    def test_the_end_of_a_table_a_late_arrival_finds_up_signals_them_too(self, scene):
        scene.invite(BACH)
        scene.stand(OPENER)
        scene.at(START + timedelta(seconds=120))
        scene.service.note_presence(TableId(scene.table_id), nullcontext(NOBODY), 60)
        scene.at(START + timedelta(seconds=240))
        scene.signals.clear()

        arrival = nullcontext(frozenset({VISITOR.account_id}))
        assert scene.service.note_presence(TableId(scene.table_id), arrival, 60) is True

        assert [accounts for accounts, _ in scene.signals] == [frozenset({BACH.account_id})]

    def test_a_command_that_changes_no_chair_signals_nobody(self, scene):
        scene.sit(VISITOR, 2)
        scene.sit(CLEO, 3)
        scene.signals.clear()

        scene.service.note_presence(TableId(scene.table_id), nullcontext(frozenset({VISITOR.account_id})), 60)

        assert scene.signals == []

    def test_nothing_is_signalled_when_the_transaction_fails(self, scene):
        offer = scene.invite()
        scene.signals.clear()
        failing = TableService(
            FaultyTableTransactions(scene.store, save_failure=ConnectionError("lost")), now=lambda: scene.now
        )
        failing = failing.with_standing_signal(scene.signals.append)
        arguments = Acceptance(scene.table_id, offer.id, offer.epoch)
        owner_present = frozenset({OWNER})

        with pytest.raises(ConnectionError):
            failing.accept_invitation(MOZART, OWNER, arguments, owner_present)

        assert scene.signals == []
