from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from skat.store.migrate import MIGRATIONS_DIRECTORY, migrate


def revision_before_head():
    """The revision the newest migration comes after."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    scripts = ScriptDirectory.from_config(config)
    return scripts.get_revision(scripts.get_current_head()).down_revision


def upgrade_to(engine, revision, operator_account_id=None):
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        config.attributes["operator_account_id"] = operator_account_id
        command.upgrade(config, revision)


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
