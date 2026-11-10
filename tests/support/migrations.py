from alembic import command
from alembic.config import Config

from skat.store.migrate import MIGRATIONS_DIRECTORY


def run_in_transaction(engine, statement):
    with engine.begin() as connection:
        connection.execute(statement)


def upgrade_to(engine, revision):
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
