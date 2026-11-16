import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import delete, insert, select

from skat.store.migrate import MIGRATIONS_DIRECTORY, migrate
from skat.store.schema import serving_revisions

if TYPE_CHECKING:
    from pathlib import Path


def _config(extra_versions: Path | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    if extra_versions is not None:
        config.set_main_option("path_separator", "os")
        config.set_main_option(
            "version_locations", os.pathsep.join([str(MIGRATIONS_DIRECTORY / "versions"), str(extra_versions)])
        )
    return config


def head_revision():
    """The newest revision of Skat's own migrations."""
    return ScriptDirectory.from_config(_config()).get_current_head()


def revision_before_head():
    """The revision the newest migration comes after."""
    scripts = ScriptDirectory.from_config(_config())
    return scripts.get_revision(scripts.get_current_head()).down_revision


def revisions_from(first: str):
    """The real revision `first` and every one after it, the oldest first."""
    scripts = ScriptDirectory.from_config(_config())
    newest_first = list(scripts.walk_revisions())
    return list(reversed(newest_first[: [each.revision for each in newest_first].index(first) + 1]))


def declares_contraction(script) -> bool:
    return getattr(script.module, "CONTRACTS", False)


def upgrade_to(engine, revision, operator_account_id=None, *, extra_versions: Path | None = None):
    """Applies the steps up to `revision` through the real `env.py`; `extra_versions` names a directory of further
    revision files, which `write_revisions` fills, that extend the real ones.
    """
    config = _config(extra_versions)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        config.attributes["operator_account_id"] = operator_account_id
        command.upgrade(config, revision)


@dataclass(frozen=True)
class FixtureRevision:
    revision: str
    statements: tuple[str, ...] = ()
    contracts: bool = False


def write_revisions(directory: Path, *revisions: FixtureRevision) -> None:
    """Writes the revisions as a chain that continues the real one, in the order given."""
    down_revision = head_revision()
    for each in revisions:
        calls = "".join(f"    op.execute({statement!r})\n" for statement in each.statements) or "    pass\n"
        (directory / f"{each.revision}.py").write_text(
            f"from alembic import op\n\nrevision = {each.revision!r}\ndown_revision = {down_revision!r}\n"
            f"CONTRACTS = {each.contracts!r}\n\n\ndef upgrade() -> None:\n{calls}"
        )
        down_revision = each.revision


def served_revisions(engine) -> set[str]:
    with engine.connect() as connection:
        return set(connection.execute(select(serving_revisions.c.revision)).scalars())


def serve_only(engine, *revisions):
    """Makes the database list exactly these revisions as served."""
    with engine.begin() as connection:
        connection.execute(delete(serving_revisions))
        if revisions:
            connection.execute(insert(serving_revisions), [{"revision": revision} for revision in revisions])


def migrated_from(engine, revision, *statements):
    """The engine migrated to the head from a store that held the given rows at the revision."""
    upgrade_to(engine, revision)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(statement)
    migrate(engine)
    return engine


def run_in_transaction(engine, statement):
    with engine.begin() as connection:
        connection.execute(statement)


def only_row(engine, statement):
    with engine.connect() as connection:
        return tuple(connection.execute(statement).one())


def insert_into_game_list(columns):
    names, values = ", ".join(columns), ", ".join(str(value) for value in columns.values())
    return f"INSERT INTO game_list ({names}) VALUES ({values})"  # noqa: S608 - only a test's fixed literals reach this text


def list_row(**changed):
    columns = {
        "table_id": "'t'",
        "ordinal": 1,
        "seat_1_account": "'account-anna'",
        "seat_2_account": "'account-ben'",
        "seat_3_account": "'account-cleo'",
        "declarer_seat": 1,
        "game": "'kreuz'",
        "hand": "false",
        "ouvert": "false",
        "announcement": "'none'",
        "schneider": "true",
        "schwarz": "false",
        "matadors_mit": "true",
        "matadors_count": 2,
        "won": "true",
        "bid": 18,
        "game_value": 48,
        "settled_value": 48,
        "score": 48,
        "declarer_points": 95,
        **changed,
    }
    return insert_into_game_list(columns)


def ramsch_list_row(**changed):
    columns = {
        "table_id": "'t'",
        "ordinal": 1,
        "seat_1_account": "'account-anna'",
        "seat_2_account": "'account-ben'",
        "seat_3_account": "'account-cleo'",
        "kind": "'ramsch'",
        "seat_1_points": 47,
        "seat_2_points": 40,
        "seat_3_points": 33,
        "seat_1_score": -47,
        "seat_2_score": 0,
        "seat_3_score": 0,
        "jungfrau": "false",
        **changed,
    }
    return insert_into_game_list(columns)
