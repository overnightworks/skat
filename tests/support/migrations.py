from alembic import command
from alembic.config import Config

from skat.store.migrate import MIGRATIONS_DIRECTORY


def upgrade_to(engine, revision, operator_account_id=None):
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        config.attributes["operator_account_id"] = operator_account_id
        command.upgrade(config, revision)


def run_in_transaction(engine, statement):
    with engine.begin() as connection:
        connection.execute(statement)


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
    names, values = ", ".join(columns), ", ".join(str(value) for value in columns.values())
    return f"INSERT INTO game_list ({names}) VALUES ({values})"  # noqa: S608 - only a test's fixed literals reach this text
