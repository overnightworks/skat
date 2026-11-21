"""The trace a commit entered in is stored with the version and the acts it wrote, and the release before, which
writes none, leaves what it writes untraced.
"""

import random

import pytest
from sqlalchemy import text

from skat.table.records import Actor, CreateTable, EntryTraces
from skat.table.service import TableService
from tests.support.seated_tables import seated_table
from tests.support.series_store import read

pytestmark = pytest.mark.postgres

TRACE = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


@pytest.fixture
def traced(transactions):
    return TableService(transactions, random_source=random.Random(8)).with_trace(lambda: TRACE)  # noqa: S311 - seeded


def test_a_commit_stores_its_trace_with_the_version_and_the_act_it_wrote(traced, transactions):
    table_id = seated_table(traced, "traced", series_length=36)

    traces = read(transactions, table_id.value).traces

    assert (traces.version, [each for _, each in traces.acts]) == (TRACE, [TRACE])


def test_an_opened_table_stores_the_trace_of_the_request_that_opened_it(traced, transactions):
    opened = traced.create(Actor("account-opener", "Opener"), CreateTable(command_id="command-open"))

    assert read(transactions, opened.id).traces == EntryTraces(TRACE)


def test_a_version_the_release_before_moved_reads_with_no_trace_and_its_acts_keep_theirs(traced, transactions, engine):
    table_id = seated_table(traced, "moved", series_length=36)
    before = read(transactions, table_id.value).traces
    with engine.begin() as connection:
        connection.execute(text("UPDATE tables SET version = version + 1 WHERE id = :id"), {"id": table_id.value})

    assert read(transactions, table_id.value).traces == EntryTraces(None, before.acts)
