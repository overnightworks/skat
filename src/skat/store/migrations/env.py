from alembic import context

from skat.store.migrate import ServingWindow
from skat.store.tables import metadata

# `skat.store.migrate` hands in the connection that holds the migration lock.
connection = context.config.attributes["connection"]
window = ServingWindow()
# Alembic types the hook as positional and calls it by keyword.
context.configure(
    connection=connection,
    target_metadata=metadata,
    on_version_apply=window.step_applied,  # pyright: ignore[reportArgumentType]
)
with context.begin_transaction():
    window.begins_at(context.get_context().get_current_heads())
    context.run_migrations()
    window.record(connection)
