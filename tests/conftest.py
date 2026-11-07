from functools import partial
from typing import TYPE_CHECKING

import pytest

# Assertion rewriting must be registered before the first import of a support module.
# The `tests` namespace itself is already imported when this conftest loads.
pytest.register_assert_rewrite("tests.support", "tests.e2e.support")

from tests.support.postgres import created_database, migrated_template  # noqa: E402
from tests.support.sign_in_settings import SignInSettings, build_sign_in_settings  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


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
def unmigrated_database_url() -> Iterator[str]:
    with created_database() as url:
        yield url
