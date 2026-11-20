from dataclasses import dataclass
from typing import TYPE_CHECKING

from skat.engine.deal import Position, positions_from
from skat.table.auction import AuctionAction, AuctionCommand
from skat.table.auction_plans import AuctionPlanCommand
from skat.table.records import Actor, AuctionPlan, CreateTable, SitDown, TableRecord

if TYPE_CHECKING:
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
    """Anna, Ben and Cleo at a dealt table, told apart by the position the deal gave them."""

    service: TableService
    store: FakeTableStore
    table_id: str
    forehand: Actor
    middlehand: Actor
    rearhand: Actor

    def table(self) -> TableRecord:
        record = self.store.tables[self.table_id]
        assert isinstance(record, TableRecord)
        return record

    def seat_of(self, actor: Actor) -> int:
        return next(
            chair.seat
            for chair in self.table().chairs
            if chair.occupant is not None and chair.occupant.account_id == actor.account_id
        )

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

    def plan(self, actor: Actor, plan: AuctionPlan | None, *, command_id: str = FIRST_COMMAND):
        command = AuctionPlanCommand(command_id=command_id, table_id=self.table_id, plan=plan)
        return self.service.set_auction_plan(actor, command, NOBODY_CONNECTED)


def open_table(service: TableService) -> str:
    return service.create(ANNA, CreateTable(command_id="command-open")).id


def seat_three(service: TableService, store: FakeTableStore) -> Seated:
    table_id = open_table(service)
    service.sit(BEN, SitDown("command-ben", table_id, 2), NOBODY_CONNECTED)
    service.sit(CLEO, SitDown("command-cleo", table_id, 3), NOBODY_CONNECTED)
    table = store.tables[table_id]
    assert isinstance(table, TableRecord)
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
