from sqlalchemy import func, select


def seconds_until_due(engine, due_at, *conditions):
    """The seconds until the stored deadline `due_at` of the row the conditions pick, on the store's clock, or None
    without such a row.
    """
    with engine.connect() as connection:
        return connection.execute(
            select(func.extract("epoch", due_at - func.now())).where(*conditions)
        ).scalar_one_or_none()
