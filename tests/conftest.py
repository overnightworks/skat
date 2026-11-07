from functools import partial
from typing import TYPE_CHECKING

import pytest

# Assertion rewriting must be registered before the first import of a support module.
# The `tests` namespace itself is already imported when this conftest loads.
pytest.register_assert_rewrite("tests.support", "tests.e2e.support")

from tests.support.page_build import FIXTURE_DIRECTORY  # noqa: E402
from tests.support.sign_in_settings import SignInSettings, build_sign_in_settings  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture
def sign_in_settings(tmp_path: Path) -> Callable[..., SignInSettings]:
    return partial(build_sign_in_settings, tmp_path)


@pytest.fixture
def fixture_build_directory(monkeypatch: pytest.MonkeyPatch) -> Path:
    """`skat.host.main` loads the committed fixture build, because the unit job has no Node and no build."""
    monkeypatch.setattr("skat.host.main.BUILD_DIRECTORY", FIXTURE_DIRECTORY)
    return FIXTURE_DIRECTORY
