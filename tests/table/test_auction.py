import random
from dataclasses import dataclass, replace

import pytest

from skat.engine.bidding import Auction, AuctionStep, Bid, BidRefusal, Declared, Hold, Pass, Play
from skat.engine.deal import Position, positions_from
from skat.table.auction import AuctionAction, AuctionCommand, action_of, step_of
from skat.table.hand_state import auction_of
from skat.table.records import Actor, CreateTable, HandProgress, Refusal, SitDown, TableRecord, parsed_refusal
from skat.table.service import CommandIdReusedError, TableService
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


@pytest.fixture
def seated(service: TableService, store: FakeTableStore) -> Seated:
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


class TestRetry:
    def test_a_completed_retry_is_recognised_before_its_old_version_is_refused(self, seated: Seated) -> None:
        old_version = seated.table().version
        first = seated.send(seated.middlehand, AuctionAction.BID, value=18, version=old_version)

        again = seated.send(seated.middlehand, AuctionAction.BID, value=18, version=old_version)

        assert again == first
        assert seated.table().progress.auction == (Bid(Position.MIDDLEHAND, 18),)

    def test_a_refused_step_retried_gets_the_same_refusal(self, seated: Seated) -> None:
        first = seated.send(seated.forehand, AuctionAction.PASS)

        assert seated.send(seated.forehand, AuctionAction.PASS).refusal is first.refusal

    @pytest.mark.parametrize(
        ("action", "value", "version_offset"),
        [
            pytest.param(AuctionAction.BID, 20, 0, id="another-value"),
            pytest.param(AuctionAction.PASS, None, 0, id="another-action"),
            pytest.param(AuctionAction.BID, 18, 1, id="another-version"),
        ],
    )
    def test_the_same_id_with_another_request_is_refused(
        self, seated: Seated, action: AuctionAction, value: int | None, version_offset: int
    ) -> None:
        version = seated.table().version
        seated.send(seated.middlehand, AuctionAction.BID, value=18, version=version)

        with pytest.raises(CommandIdReusedError):
            seated.send(seated.middlehand, action, value=value, version=version + version_offset)


class TestStoredLog:
    def test_a_stored_log_the_engine_refuses_raises_at_the_next_command(self, seated: Seated) -> None:
        corrupt = HandProgress(auction=(Bid(Position.MIDDLEHAND, 18), Pass(Position.REARHAND)))
        seated.store.tables[seated.table_id] = replace(seated.table(), progress=corrupt)

        with pytest.raises(ValueError, match="impossible auction log"):
            seated.send(seated.middlehand, AuctionAction.PASS)


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
