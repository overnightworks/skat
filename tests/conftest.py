from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Registers the pytester fixture for the tests that run an inner pytest.
pytest_plugins = ["pytester"]

# Assertion rewriting must be registered before the first import of a support module.
# The `tests` namespace itself is already imported when this conftest loads.
pytest.register_assert_rewrite("tests.support", "tests.e2e.support")

from tests.support.database_relay import DatabaseRelay  # noqa: E402
from tests.support.postgres import created_database, migrated_template  # noqa: E402
from tests.support.redis import fresh_database_url  # noqa: E402
from tests.support.shards import select_shard  # noqa: E402
from tests.support.sign_in_settings import SignInSettings, build_sign_in_settings  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

END_TO_END_DIRECTORY = Path(__file__).parent / "e2e"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Shards the unit suite; the end-to-end conftest shards its own tests the same way."""
    select_shard(config, items, lambda path: not path.is_relative_to(END_TO_END_DIRECTORY))


@pytest.fixture
def sign_in_settings(tmp_path: Path) -> Callable[..., SignInSettings]:
    return partial(build_sign_in_settings, tmp_path)


@pytest.fixture(scope="session")
def postgres_template() -> Iterator[str]:
    """The name of the migrated template database; the first test that asks creates it."""
    with migrated_template() as name:
        yield name


@pytest.fixture
def database_url(postgres_template: str) -> Iterator[str]:
    """A migrated database of this test's own."""
    with created_database(postgres_template) as url:
        yield url


@pytest.fixture
def redis_url() -> str:
    """The URL of this worker's Redis database, emptied for this test."""
    return fresh_database_url()


@pytest.fixture
def unmigrated_database_url() -> Iterator[str]:
    with created_database() as url:
        yield url


@pytest.fixture
def relay_in_front_of() -> Iterator[Callable[[str], DatabaseRelay]]:
    """Puts a relay in front of a database; its `url` reaches the database through the relay."""
    relays: list[DatabaseRelay] = []

    def relay(database_url: str) -> DatabaseRelay:
        relays.append(DatabaseRelay(database_url))
        return relays[-1]

    yield relay
    for each in relays:
        each.close()
