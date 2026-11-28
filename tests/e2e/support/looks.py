from enum import StrEnum


class Look(StrEnum):
    """A surface a page shows the table on: today's, or a look that draws the whole table, named by its id."""

    TODAY = "today"
    LAMPE = "lampe"
