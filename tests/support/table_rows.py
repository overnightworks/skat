from sqlalchemy import select

from skat.store.schema import metadata, tables


def rows_of(engine, table_id: str) -> dict[str, list[tuple[object, ...]]]:
    """Every row of the store that belongs to the table, in every store table."""
    with engine.connect() as connection:
        return {
            each.name: [
                tuple(row)
                for row in connection.execute(
                    select(each)
                    .where((each.c.id if each is tables else each.c.table_id) == table_id)
                    .order_by(*each.primary_key.columns)
                )
            ]
            for each in metadata.sorted_tables
        }
