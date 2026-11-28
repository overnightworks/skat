"""Tests for the split of the end-to-end suite across CI runners."""

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

from tests.e2e.support import shards

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pytest

SUITE_DIRECTORY = Path("suite")
SHARD_COUNT = 3


def suite_items(count: int) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(path=SUITE_DIRECTORY / "test_flow.py", nodeid=f"test_flow.py::test_{n:02}")
        for n in range(count)
    ]


def ignore_deselected(items: list[SimpleNamespace]) -> None:
    """The hook the real config offers; the test reads the kept items instead."""


def kept_node_ids(monkeypatch: pytest.MonkeyPatch, items: list[SimpleNamespace], index: int) -> set[str]:
    monkeypatch.setenv(shards.SHARD_VARIABLE, str(index))
    monkeypatch.setenv(shards.SHARDS_VARIABLE, str(SHARD_COUNT))
    config = SimpleNamespace(hook=SimpleNamespace(pytest_deselected=ignore_deselected))
    kept = list(items)
    shards.select_shard(config, kept, SUITE_DIRECTORY)  # type: ignore[arg-type]
    return {item.nodeid for item in kept}


def reordered_runs(count: int) -> Iterator[list[SimpleNamespace]]:
    items = suite_items(count)
    yield items
    yield items[::-1]
    yield items[1::2] + items[::2]


def test_shards_that_collect_in_different_orders_partition_the_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    kept = [kept_node_ids(monkeypatch, items, index) for index, items in enumerate(reordered_runs(12))]

    assert sum(len(share) for share in kept) == 12
    assert set().union(*kept) == {item.nodeid for item in suite_items(12)}
