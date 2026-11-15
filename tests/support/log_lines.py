"""The JSON lines a run writes through logline, read back as records."""

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING

from logline.testing import configured

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pytest


@contextmanager
def logged(capsys: pytest.CaptureFixture[str]) -> Iterator[list[dict]]:
    """Runs the body under logline's configuration; the list holds every line it wrote once the body has ended."""
    lines: list[dict] = []
    capsys.readouterr()
    with configured("skat"):
        try:
            yield lines
        finally:
            lines.extend(json.loads(line) for line in capsys.readouterr().out.splitlines())


def lines_of(lines: list[dict], event: str) -> list[dict]:
    return [line for line in lines if line["event"] == event]
