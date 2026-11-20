import random

import pytest

from skat.table.service import TableService
from tests.support.fake_tables import FakeTableStore
from tests.support.seated_auction import Seated, seat_three


@pytest.fixture
def store() -> FakeTableStore:
    return FakeTableStore()


@pytest.fixture
def service(store: FakeTableStore) -> TableService:
    return TableService(store, random_source=random.Random(8))  # noqa: S311 - a seeded source makes the deal reproducible


@pytest.fixture
def seated(service: TableService, store: FakeTableStore) -> Seated:
    return seat_three(service, store)
