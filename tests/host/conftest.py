from typing import TYPE_CHECKING

import pytest

from tests.support.pods import Pods, running_pods
from tests.support.unplayed_tables import UnplayedTables

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def unplayed(sign_in_settings):
    return UnplayedTables(sign_in_settings)


@pytest.fixture(scope="module")
def pods(postgres_template, tmp_path_factory) -> Iterator[Pods]:
    with running_pods(postgres_template, tmp_path_factory.mktemp("pods")) as running:
        yield running
