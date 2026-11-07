"""Tests for the generator that writes the browser's typed copy of the Python paths."""

from typing import TYPE_CHECKING

import pytest

from scripts import generate_wire
from skat.web.constants import ACCOUNT_CONSOLE_PATH, ACCOUNT_PATH, AUTH_START_PATH, LOGOUT_PATH

if TYPE_CHECKING:
    from pathlib import Path


def test_main_check_committed_wire_module_exits_clean() -> None:
    assert generate_wire.main(["--check"]) == 0


def test_render_names_every_path_the_page_uses() -> None:
    rendered = generate_wire.render()

    for name, path in [
        ("AUTH_START_PATH", AUTH_START_PATH),
        ("LOGOUT_PATH", LOGOUT_PATH),
        ("ACCOUNT_PATH", ACCOUNT_PATH),
        ("ACCOUNT_CONSOLE_PATH", ACCOUNT_CONSOLE_PATH),
    ]:
        assert any(name in line and f'"{path}"' in line for line in rendered.splitlines())


def test_main_writes_the_module_and_a_following_check_passes(tmp_path: Path) -> None:
    assert generate_wire.main([], root=tmp_path) == 0
    assert (tmp_path / generate_wire.OUTPUT).read_text() == generate_wire.render()
    assert generate_wire.main(["--check"], root=tmp_path) == 0


@pytest.mark.parametrize("stale_content", [None, "// edited by hand\n"])
def test_main_check_fails_for_a_missing_or_edited_module(tmp_path: Path, stale_content: str | None) -> None:
    if stale_content is not None:
        (tmp_path / generate_wire.OUTPUT).parent.mkdir(parents=True)
        (tmp_path / generate_wire.OUTPUT).write_text(stale_content)

    with pytest.raises(SystemExit, match="out of date"):
        generate_wire.main(["--check"], root=tmp_path)
