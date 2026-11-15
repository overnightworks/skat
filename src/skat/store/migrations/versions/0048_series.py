"""Each series of a table has a row of its own that holds the length and options it started with, its deals, early end,
standing proposal and Bock rounds; `tables` keeps only the number of the current series. A table that exists reads as
one series with its current settings; a series that already ended gets the same length and options, which were fixed
for the table, with every deal played, no early end and no Bock rounds, and no row of it is read as history. A game
keeps the seat kinds of its three occupants, which a game stored before reads as unknown.
"""

from alembic import op

revision = "0048"
down_revision = "0047"

OPTION_COLUMNS = (
    "show_running_points",
    "kontra_sayer",
    "kontra_reach",
    "kontra_deadline",
    "bock_triggers",
    "bock_overlap",
    "ramsch_occasion",
    "ramsch_scoring",
    "ramsch_jungfrau",
    "ramsch_durchmarsch",
    "ramsch_pushing",
    "ramsch_grand_hand",
)
OPTIONS = ", ".join(OPTION_COLUMNS)
MOVED_COLUMNS = (
    "series_length",
    "series_deals",
    "series_ended_early",
    "series_end_proposer",
    "series_end_accepter",
    *OPTION_COLUMNS,
    "bock_rounds",
    "ramsch_round_games",
)
BOCK_TRIGGERS = (
    "sixty-sixty",
    "won-grand-hand",
    "lost-after-kontra",
    "re",
    "passed-in",
    "schneider",
    "schwarz",
    "total-ending-in-00",
)
ONE_OF = {
    "kontra_sayer": ("any-opponent", "bidders-only"),
    "kontra_reach": ("kontra-re", "kontra-re-standings", "up-to-hirsch"),
    "kontra_deadline": ("own-card", "first-card"),
    "bock_overlap": ("append", "multiply", "ignore"),
    "ramsch_occasion": ("passed-in", "bock-rounds", "passed-in-and-bock-rounds"),
    "ramsch_scoring": ("points", "points-by-ten", "skat-to-loser"),
    "ramsch_jungfrau": ("doubles-loser", "off"),
    "ramsch_durchmarsch": ("wins-120", "wins-120-flat", "off"),
    "ramsch_pushing": ("jacks-stay", "jacks-may-go", "no-doubling"),
    "ramsch_grand_hand": ("allowed", "off"),
}
CHECK_NAME_OF = {
    "kontra_sayer": "series_kontra_sayer_is_a_sayer",
    "kontra_reach": "series_kontra_reach_is_a_reach",
    "kontra_deadline": "series_kontra_deadline_is_a_deadline",
    "bock_overlap": "series_bock_overlap_is_an_overlap",
    "ramsch_occasion": "series_ramsch_occasion_is_an_occasion",
    "ramsch_scoring": "series_ramsch_scoring_is_a_scoring",
    "ramsch_jungfrau": "series_ramsch_jungfrau_is_a_jungfrau_rule",
    "ramsch_durchmarsch": "series_ramsch_durchmarsch_is_a_durchmarsch_rule",
    "ramsch_pushing": "series_ramsch_pushing_is_a_pushing_rule",
    "ramsch_grand_hand": "series_ramsch_grand_hand_is_a_grand_hand_rule",
}
KINDS = ("person", "agent")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def _option_checks() -> list[str]:
    return [
        f"CONSTRAINT {CHECK_NAME_OF[column]} CHECK ({_one_of(column, values)})" for column, values in ONE_OF.items()
    ]


def _create_series() -> None:
    triggers = ", ".join(f"'{trigger}'" for trigger in BOCK_TRIGGERS)
    columns = [
        "table_id text NOT NULL REFERENCES tables (id)",
        "number smallint NOT NULL",
        "length smallint",
        "deals smallint",
        "ended_early boolean NOT NULL DEFAULT false",
        "end_proposer smallint",
        "end_accepter smallint",
        "show_running_points boolean NOT NULL DEFAULT false",
        "kontra_sayer text",
        "kontra_reach text",
        "kontra_deadline text",
        "bock_triggers text[]",
        "bock_overlap text",
        "ramsch_occasion text",
        "ramsch_scoring text",
        "ramsch_jungfrau text",
        "ramsch_durchmarsch text",
        "ramsch_pushing text",
        "ramsch_grand_hand text",
        "bock_rounds smallint[] NOT NULL DEFAULT '{}'",
        "ramsch_round_games smallint NOT NULL DEFAULT 0",
        "PRIMARY KEY (table_id, number)",
        "CONSTRAINT series_number_counts_from_one CHECK (number >= 1)",
        "CONSTRAINT series_length_comes_with_deals CHECK ((length IS NULL) = (deals IS NULL))",
        "CONSTRAINT series_length_is_a_length CHECK (length BETWEEN 3 AND 99 AND length % 3 = 0)",
        "CONSTRAINT series_deals_are_within_the_length CHECK (deals BETWEEN 0 AND length)",
        "CONSTRAINT series_numbers_only_with_a_length CHECK (length IS NOT NULL OR number = 1)",
        "CONSTRAINT series_end_seats_are_seats CHECK (end_proposer BETWEEN 1 AND 3 AND end_accepter BETWEEN 1 AND 3)",
        "CONSTRAINT series_end_accepter_follows_a_proposer CHECK (end_accepter IS NULL"
        " OR (end_proposer IS NOT NULL AND end_accepter <> end_proposer))",
        "CONSTRAINT series_end_needs_a_length CHECK (length IS NOT NULL OR (end_proposer IS NULL AND NOT ended_early))",
        "CONSTRAINT series_ended_early_holds_no_proposal CHECK (NOT ended_early OR end_proposer IS NULL)",
        "CONSTRAINT series_kontra_is_all_or_nothing"
        " CHECK (num_nonnulls(kontra_sayer, kontra_reach, kontra_deadline) IN (0, 3))",
        "CONSTRAINT series_bock_is_all_or_nothing CHECK ((bock_triggers IS NULL) = (bock_overlap IS NULL))",
        "CONSTRAINT series_bock_triggers_are_triggers"
        f" CHECK (cardinality(bock_triggers) >= 1 AND bock_triggers <@ ARRAY[{triggers}]::text[])",
        "CONSTRAINT series_ramsch_is_all_or_nothing CHECK"
        " (num_nonnulls(ramsch_occasion, ramsch_scoring, ramsch_jungfrau, ramsch_durchmarsch) IN (0, 4))",
        "CONSTRAINT series_ramsch_pushing_needs_a_ramsch CHECK (ramsch_pushing IS NULL OR ramsch_occasion IS NOT NULL)",
        "CONSTRAINT series_ramsch_grand_hand_needs_pushing"
        " CHECK (ramsch_grand_hand IS NULL OR ramsch_pushing IS NOT NULL)",
        "CONSTRAINT series_bock_rounds_are_rounds_with_games_left CHECK"
        " (bock_rounds <@ ARRAY[1, 2, 3]::smallint[] AND array_position(bock_rounds, NULL) IS NULL)",
        "CONSTRAINT series_bock_rounds_only_with_bock"
        " CHECK (bock_triggers IS NOT NULL OR cardinality(bock_rounds) = 0)",
        "CONSTRAINT series_ramsch_round_games_are_not_negative CHECK (ramsch_round_games >= 0)",
        *_option_checks(),
    ]
    op.execute(f"CREATE TABLE series ({', '.join(columns)})")


def _backfill_series() -> None:
    """One row per series that a table's pointer or a game names: the current series takes everything `tables` holds,
    an earlier one the length and options that were fixed for the table.
    """
    from_tables = ", ".join(f"t.{column}" for column in OPTION_COLUMNS)
    op.execute(
        "INSERT INTO series (table_id, number, length, deals, ended_early, end_proposer, end_accepter,"
        f" {OPTIONS}, bock_rounds, ramsch_round_games)"
        " SELECT t.id, t.series_number, t.series_length, t.series_deals, t.series_ended_early, t.series_end_proposer,"
        f" t.series_end_accepter, {from_tables}, t.bock_rounds, t.ramsch_round_games FROM tables t"
    )
    op.execute(
        f"INSERT INTO series (table_id, number, length, deals, {OPTIONS})"
        f" SELECT t.id, played.series_number, t.series_length, t.series_length, {from_tables}"
        " FROM tables t JOIN (SELECT DISTINCT table_id, series_number FROM game_list) played ON played.table_id = t.id"
        " WHERE NOT EXISTS (SELECT 1 FROM series s WHERE s.table_id = t.id AND s.number = played.series_number)"
    )


def _assert_every_series_has_its_row() -> None:
    op.execute(
        "DO $$ BEGIN"
        " IF EXISTS (SELECT 1 FROM game_list g WHERE NOT EXISTS"
        "  (SELECT 1 FROM series s WHERE s.table_id = g.table_id AND s.number = g.series_number))"
        " OR EXISTS (SELECT 1 FROM tables t WHERE NOT EXISTS"
        "  (SELECT 1 FROM series s WHERE s.table_id = t.id AND s.number = t.series_number))"
        " THEN RAISE EXCEPTION 'a series of a game or a table has no row to move to'; END IF;"
        " END $$"
    )


def _guard_games_by_their_series() -> None:
    kinds = [f"seat_{seat}_kind" for seat in (1, 2, 3)]
    op.execute(
        "ALTER TABLE game_list DROP CONSTRAINT game_list_table_id_fkey,"
        " ADD CONSTRAINT game_list_table_id_series_number_fkey"
        " FOREIGN KEY (table_id, series_number) REFERENCES series (table_id, number),"
        + ", ".join(f"ADD COLUMN {kind} text" for kind in kinds)
        + f", ADD CONSTRAINT game_list_kinds_are_all_or_nothing CHECK (num_nonnulls({', '.join(kinds)}) IN (0, 3)), "
        + ", ".join(f"ADD CONSTRAINT game_list_{kind}_is_a_kind CHECK ({_one_of(kind, KINDS)})" for kind in kinds)
    )


def upgrade() -> None:
    _create_series()
    _backfill_series()
    _assert_every_series_has_its_row()
    _guard_games_by_their_series()
    # A dropped column takes every check that names it with it.
    op.execute("ALTER TABLE tables " + ", ".join(f"DROP COLUMN {column}" for column in MOVED_COLUMNS))
