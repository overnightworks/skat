import random
from dataclasses import dataclass

import pytest

from skat.engine.bidding import Auction, AuctionStep, Bid, BidRefusal, Declared, Hold, Pass, PassedIn, Play
from skat.engine.deal import Position, next_dealer, positions_from
from skat.table.auction import AuctionAction, AuctionCommand, action_of, step_of
from skat.table.hand_state import auction_of
from skat.table.records import Actor, CreateTable, Refusal, SitDown, StandUp, TableRecord, parsed_refusal
from skat.table.service import TableService
from tests.support.fake_tables import FakeTableStore

ANNA = Actor(account_id="account-anna", display_name="Anna")
BEN = Actor(account_id="account-ben", display_name="Ben")
CLEO = Actor(account_id="account-cleo", display_name="Cleo")
DORA = Actor(account_id="account-dora", display_name="Dora")
NOBODY_CONNECTED: frozenset[str] = frozenset()
FIRST_COMMAND = "command-step"


@dataclass(frozen=True)
class Seated:
    service: TableService
    store: FakeTableStore
    table_id: str
    forehand: Actor
    middlehand: Actor
    rearhand: Actor

    def table(self) -> TableRecord:
        return self.store.tables[self.table_id]

    def send(
        self,
        actor: Actor,
        action: AuctionAction,
        *,
        value: int | None = None,
        version: int | None = None,
        command_id: str = FIRST_COMMAND,
    ):
        command = AuctionCommand(
            command_id=command_id,
            table_id=self.table_id,
            version=self.table().version if version is None else version,
            action=action,
            value=value,
        )
        return self.service.take_auction_step(actor, command, NOBODY_CONNECTED)


@pytest.fixture
def store() -> FakeTableStore:
    return FakeTableStore()


@pytest.fixture
def service(store: FakeTableStore) -> TableService:
    return TableService(store, random_source=random.Random(8))  # noqa: S311 - a seeded source makes the deal reproducible


def open_table(service: TableService) -> str:
    return service.create(ANNA, CreateTable(command_id="command-open")).id


def seat_three(service: TableService, store: FakeTableStore) -> Seated:
    table_id = open_table(service)
    service.sit(BEN, SitDown("command-ben", table_id, 2), NOBODY_CONNECTED)
    service.sit(CLEO, SitDown("command-cleo", table_id, 3), NOBODY_CONNECTED)
    table = store.tables[table_id]
    assert table.dealer is not None
    by_seat = {1: ANNA, 2: BEN, 3: CLEO}
    by_position = {position: by_seat[seat] for seat, position in positions_from(table.dealer).items()}
    return Seated(
        service,
        store,
        table_id,
        forehand=by_position[Position.FOREHAND],
        middlehand=by_position[Position.MIDDLEHAND],
        rearhand=by_position[Position.REARHAND],
    )


@pytest.fixture
def seated(service: TableService, store: FakeTableStore) -> Seated:
    return seat_three(service, store)


class TestRefusalOrder:
    def test_no_hand_comes_before_not_seated(self, service: TableService) -> None:
        table_id = open_table(service)
        command = AuctionCommand("command-1", table_id, 1, AuctionAction.PASS, None)

        result = service.take_auction_step(BEN, command, NOBODY_CONNECTED)

        assert result is not None
        assert result.refusal is Refusal.NO_HAND

    def test_not_seated_comes_before_a_stale_version(self, seated: Seated) -> None:
        result = seated.send(DORA, AuctionAction.PASS, version=seated.table().version - 1)

        assert result.refusal is Refusal.NOT_SEATED

    def test_a_stale_version_comes_before_the_engines_reason(self, seated: Seated) -> None:
        result = seated.send(seated.forehand, AuctionAction.PASS, version=seated.table().version - 1)

        assert result.refusal is Refusal.STALE_VERSION

    def test_the_engines_reason_comes_last(self, seated: Seated) -> None:
        result = seated.send(seated.forehand, AuctionAction.PASS)

        assert result.refusal is BidRefusal.NOT_YOUR_TURN


class TestStep:
    def test_an_accepted_step_is_appended_at_the_actors_position_and_bumps_the_version_by_one(
        self, seated: Seated
    ) -> None:
        before = seated.table().version

        result = seated.send(seated.middlehand, AuctionAction.BID, value=18)

        assert result.refusal is None
        assert seated.table().progress.auction == (Bid(Position.MIDDLEHAND, 18),)
        assert seated.table().version == before + 1
        assert result.view.version == before + 1

    def test_a_refused_step_leaves_the_steps_and_the_version(self, seated: Seated) -> None:
        before = seated.table()

        result = seated.send(seated.middlehand, AuctionAction.BID, value=19)

        assert result.refusal is BidRefusal.INVALID_VALUE
        assert seated.table() == before

    def test_the_fold_reads_the_declarer_from_the_steps(self, seated: Seated) -> None:
        seated.send(seated.middlehand, AuctionAction.PASS, command_id="command-a")
        seated.send(seated.rearhand, AuctionAction.PASS, command_id="command-b")
        seated.send(seated.forehand, AuctionAction.PLAY, command_id="command-c")

        assert auction_of(seated.table()).result == Declared(Position.FOREHAND, 18)

    def test_a_table_without_steps_folds_to_the_start_of_the_auction(self, seated: Seated) -> None:
        assert auction_of(seated.table()) == Auction.start()


class AlwaysDrawsSeatOne(random.Random):
    """Draws seat 1, so a second deal that drew instead of rotating would name seat 1 again."""

    def choice(self, seq):
        return seq[0]


THIRD_PASS = "pass-forehand"
SEATED_ACCOUNTS = {ANNA.account_id, BEN.account_id, CLEO.account_id}


def two_pass(seated: Seated) -> None:
    seated.send(seated.middlehand, AuctionAction.PASS, command_id="pass-middlehand")
    seated.send(seated.rearhand, AuctionAction.PASS, command_id="pass-rearhand")


def pass_in(seated: Seated):
    two_pass(seated)
    return seated.send(seated.forehand, AuctionAction.PASS, command_id=THIRD_PASS)


class TestPassedIn:
    def test_the_third_pass_ends_the_hand_keeps_the_steps_and_bumps_the_version_once(self, seated: Seated) -> None:
        two_pass(seated)
        version = seated.table().version

        result = seated.send(seated.forehand, AuctionAction.PASS, command_id=THIRD_PASS)

        assert result.refusal is None
        assert seated.table().hand is None
        assert auction_of(seated.table()).result == PassedIn()
        assert seated.table().version == version + 1

    def test_the_answer_says_passed_in_and_names_the_next_dealer(self, seated: Seated) -> None:
        result = pass_in(seated)

        assert result.view.hand is None
        assert result.view.passed_in.next_dealer_seat == next_dealer(seated.table().dealer)

    @pytest.mark.parametrize(
        ("action", "value"),
        [
            pytest.param(AuctionAction.BID, 18, id="bid"),
            pytest.param(AuctionAction.HOLD, None, id="hold"),
            pytest.param(AuctionAction.PASS, None, id="pass"),
            pytest.param(AuctionAction.PLAY, None, id="play"),
        ],
    )
    def test_every_auction_step_after_the_hand_ended_is_no_hand(
        self, seated: Seated, action: AuctionAction, value: int | None
    ) -> None:
        pass_in(seated)
        before = seated.table()

        result = seated.send(seated.middlehand, action, value=value, command_id="after-the-end")

        assert result.refusal is Refusal.NO_HAND
        assert seated.table() == before

    def test_the_same_third_pass_again_is_the_same_answer_with_no_bump_and_names_nobody(self, seated: Seated) -> None:
        two_pass(seated)
        version = seated.table().version
        first = seated.send(seated.forehand, AuctionAction.PASS, command_id=THIRD_PASS)
        after_first = seated.table()

        again = seated.send(seated.forehand, AuctionAction.PASS, version=version, command_id=THIRD_PASS)

        assert (again.view, again.refusal) == (first.view, first.refusal)
        assert seated.table() == after_first
        assert again.seated_when_hand_ended == frozenset()

    def test_only_the_command_that_ended_the_hand_names_the_accounts_seated_at_its_end(self, seated: Seated) -> None:
        first = seated.send(seated.middlehand, AuctionAction.PASS, command_id="pass-middlehand")
        refused = seated.send(seated.forehand, AuctionAction.PASS, command_id="out-of-turn")
        second = seated.send(seated.rearhand, AuctionAction.PASS, command_id="pass-rearhand")
        third = seated.send(seated.forehand, AuctionAction.PASS, command_id=THIRD_PASS)

        assert third.seated_when_hand_ended == SEATED_ACCOUNTS
        assert first.seated_when_hand_ended == frozenset()
        assert refused.seated_when_hand_ended == frozenset()
        assert second.seated_when_hand_ended == frozenset()

    def test_standing_up_works_again_and_the_next_dealer_is_gone(self, seated: Seated) -> None:
        pass_in(seated)

        result = seated.service.stand(seated.forehand, StandUp("stand", seated.table_id), NOBODY_CONNECTED)

        assert result.refusal is None
        assert result.view.passed_in is not None
        assert result.view.passed_in.next_dealer_seat is None

    def test_the_sit_that_fills_the_third_chair_deals_by_the_next_dealer_without_a_draw_and_empties_the_auction(
        self, store: FakeTableStore
    ) -> None:
        seated = seat_three(TableService(store, random_source=AlwaysDrawsSeatOne()), store)
        first_dealer = seated.table().dealer
        pass_in(seated)
        seated.service.stand(seated.forehand, StandUp("stand", seated.table_id), NOBODY_CONNECTED)
        version = seated.table().version

        result = seated.service.sit(DORA, SitDown("fills-the-third", seated.table_id, 2), NOBODY_CONNECTED)

        assert first_dealer == 1
        assert seated.table().dealer == 2
        assert seated.table().hand is not None
        assert seated.table().progress.auction == ()
        assert result.view.passed_in is None
        assert seated.table().version == version + 1
        assert result.seated_when_hand_ended == frozenset()

    def test_the_new_hand_starts_a_fresh_auction(self, store: FakeTableStore) -> None:
        seated = seat_three(TableService(store, random_source=AlwaysDrawsSeatOne()), store)
        pass_in(seated)
        seated.service.stand(seated.forehand, StandUp("stand", seated.table_id), NOBODY_CONNECTED)
        seated.service.sit(DORA, SitDown("fills-the-third", seated.table_id, 2), NOBODY_CONNECTED)
        new_middlehand = ANNA

        result = seated.send(new_middlehand, AuctionAction.BID, value=18, command_id="new-bid")

        assert result.refusal is None
        assert seated.table().progress.auction == (Bid(Position.MIDDLEHAND, 18),)


class TestRefusalParser:
    @pytest.mark.parametrize("refusal", [*Refusal, *BidRefusal], ids=str)
    def test_reads_every_owner_s_token_back_to_its_own_enum(self, refusal: Refusal | BidRefusal) -> None:
        assert parsed_refusal(refusal.value) is refusal

    def test_a_token_no_owner_knows_raises(self) -> None:
        with pytest.raises(KeyError):
            parsed_refusal("no-such-reason")


class TestStepOfAction:
    @pytest.mark.parametrize(
        ("action", "value", "step"),
        [
            pytest.param(AuctionAction.BID, 22, Bid(Position.MIDDLEHAND, 22), id="bid"),
            pytest.param(AuctionAction.HOLD, None, Hold(Position.MIDDLEHAND), id="hold"),
            pytest.param(AuctionAction.PASS, None, Pass(Position.MIDDLEHAND), id="pass"),
            pytest.param(AuctionAction.PLAY, None, Play(Position.MIDDLEHAND), id="play"),
        ],
    )
    def test_an_action_and_its_step_name_each_other(
        self, action: AuctionAction, value: int | None, step: AuctionStep
    ) -> None:
        assert step_of(action, value, Position.MIDDLEHAND) == step
        assert action_of(step) is action
