from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    false,
    text,
)

from skat.engine.bock import GAMES_IN_A_ROUND, BockOptions, BockOverlap, BockTrigger
from skat.engine.cards import Rank, Suit
from skat.engine.deal import Position
from skat.engine.declaration import Announcement
from skat.engine.games import GameKind
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.table.records import (
    SERIES_LENGTH_MAX,
    SERIES_LENGTH_MIN,
    SERIES_LENGTH_STEP,
    EndReason,
    OccupantKind,
    TableOptions,
)
from skat.table.rule_sets import RULE_SET_NAME_MAX

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy import Row

metadata = MetaData()

BOCK_TRIGGER_LIST: Final = ", ".join(f"'{trigger.value}'" for trigger in BockTrigger)
BOCK_ROUND_LIST: Final = ", ".join(str(games) for games in range(1, GAMES_IN_A_ROUND + 1))


def one_of(column: str, values: Iterable[str], name: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IN ({', '.join(f"'{value}'" for value in values)})", name=name)


def option_columns(table_name: str) -> tuple[Column[Any] | CheckConstraint, ...]:
    """The columns that hold a table's rule options and their checks, for `tables` and `rule_sets` alike; a table
    stored before an option existed reads it as the official default.
    """
    return (
        Column("show_running_points", Boolean, nullable=False, server_default=false()),
        Column("kontra_sayer", Text),
        Column("kontra_reach", Text),
        Column("kontra_deadline", Text),
        Column("bock_triggers", ARRAY(Text)),
        Column("bock_overlap", Text),
        CheckConstraint(
            "num_nonnulls(kontra_sayer, kontra_reach, kontra_deadline) IN (0, 3)",
            name=f"{table_name}_kontra_is_all_or_nothing",
        ),
        one_of("kontra_sayer", (sayer.value for sayer in KontraSayer), f"{table_name}_kontra_sayer_is_a_sayer"),
        one_of("kontra_reach", (reach.value for reach in KontraReach), f"{table_name}_kontra_reach_is_a_reach"),
        one_of(
            "kontra_deadline",
            (deadline.value for deadline in KontraDeadline),
            f"{table_name}_kontra_deadline_is_a_deadline",
        ),
        CheckConstraint(
            "(bock_triggers IS NULL) = (bock_overlap IS NULL)", name=f"{table_name}_bock_is_all_or_nothing"
        ),
        CheckConstraint(
            f"cardinality(bock_triggers) >= 1 AND bock_triggers <@ ARRAY[{BOCK_TRIGGER_LIST}]::text[]",
            name=f"{table_name}_bock_triggers_are_triggers",
        ),
        one_of("bock_overlap", (overlap.value for overlap in BockOverlap), f"{table_name}_bock_overlap_is_an_overlap"),
    )


def options_of(row: Row[Any]) -> TableOptions:
    """The options a stored row holds; its three Kontra columns are all set or all null, so are its two Bock columns."""
    kontra = None
    if row.kontra_sayer is not None and row.kontra_reach is not None and row.kontra_deadline is not None:
        kontra = KontraOptions(
            KontraSayer(row.kontra_sayer), KontraReach(row.kontra_reach), KontraDeadline(row.kontra_deadline)
        )
    bock = None
    if row.bock_triggers is not None and row.bock_overlap is not None:
        bock = BockOptions(
            frozenset(BockTrigger(trigger) for trigger in row.bock_triggers), BockOverlap(row.bock_overlap)
        )
    return TableOptions(show_running_points=row.show_running_points, kontra=kontra, bock=bock)


def option_values(options: TableOptions) -> dict[str, object]:
    """The column values that store the options, as `options_of` reads them back."""
    kontra = options.kontra
    bock = options.bock
    return {
        "show_running_points": options.show_running_points,
        "kontra_sayer": None if kontra is None else kontra.sayer.value,
        "kontra_reach": None if kontra is None else kontra.reach.value,
        "kontra_deadline": None if kontra is None else kontra.deadline.value,
        # sorted by token, so the column reads the same however the request listed the triggers
        "bock_triggers": None if bock is None else sorted(trigger.value for trigger in bock.triggers),
        "bock_overlap": None if bock is None else bock.overlap.value,
    }


POSITION_TEXT: Final = {
    Position.FOREHAND: "forehand",
    Position.MIDDLEHAND: "middlehand",
    Position.REARHAND: "rearhand",
}


tables = Table(
    "tables",
    metadata,
    Column("id", Text, primary_key=True),
    Column("version", Integer, nullable=False),
    Column("dealer", SmallInteger),
    Column("ended_at", DateTime(timezone=True)),
    Column("end_reason", Text),
    Column("empty_seconds", Integer),
    Column("empty_since", DateTime(timezone=True)),
    Column("series_length", SmallInteger),
    Column("series_deals", SmallInteger),
    Column("give_up_asked_by", Text),
    Column("give_up_declined_by", Text),
    *option_columns("tables"),
    Column("bock_rounds", ARRAY(SmallInteger), nullable=False, server_default=text("'{}'")),
    CheckConstraint("dealer BETWEEN 1 AND 3", name="tables_dealer_is_a_seat"),
    CheckConstraint("(ended_at IS NULL) = (end_reason IS NULL)", name="tables_end_time_comes_with_its_reason"),
    CheckConstraint(
        f"(empty_seconds IS NOT NULL) = (end_reason IS NOT DISTINCT FROM '{EndReason.EMPTY.value}')",
        name="tables_empty_seconds_only_for_an_empty_end",
    ),
    CheckConstraint("empty_seconds > 0", name="tables_empty_seconds_are_positive"),
    CheckConstraint("(series_length IS NULL) = (series_deals IS NULL)", name="tables_series_is_both_or_neither"),
    CheckConstraint(
        f"series_length BETWEEN {SERIES_LENGTH_MIN} AND {SERIES_LENGTH_MAX}"
        f" AND series_length % {SERIES_LENGTH_STEP} = 0",
        name="tables_series_length_is_a_length",
    ),
    CheckConstraint("series_deals BETWEEN 0 AND series_length", name="tables_series_deals_are_within_the_length"),
    one_of("end_reason", (reason.value for reason in EndReason), "tables_end_reason_is_a_reason"),
    one_of("give_up_asked_by", POSITION_TEXT.values(), "tables_give_up_asker_is_a_position"),
    one_of("give_up_declined_by", POSITION_TEXT.values(), "tables_give_up_decliner_is_a_position"),
    CheckConstraint(
        "give_up_declined_by IS NULL OR give_up_asked_by IS NOT NULL", name="tables_give_up_no_comes_with_an_ask"
    ),
    CheckConstraint("give_up_declined_by <> give_up_asked_by", name="tables_give_up_no_comes_from_another_position"),
    CheckConstraint(
        f"bock_rounds <@ ARRAY[{BOCK_ROUND_LIST}]::smallint[] AND array_position(bock_rounds, NULL) IS NULL",
        name="tables_bock_rounds_are_rounds_with_games_left",
    ),
    CheckConstraint(
        "bock_triggers IS NOT NULL OR cardinality(bock_rounds) = 0", name="tables_bock_rounds_only_with_bock"
    ),
)

rule_sets = Table(
    "rule_sets",
    metadata,
    Column("id", Text, primary_key=True),
    Column("owner_account", Text, nullable=False),
    Column("name", Text, nullable=False),
    *option_columns("rule_sets"),
    CheckConstraint(f"char_length(name) BETWEEN 1 AND {RULE_SET_NAME_MAX}", name="rule_sets_name_is_a_name"),
    UniqueConstraint("owner_account", "name", name="rule_sets_one_name_per_owner"),
)

chairs = Table(
    "chairs",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("seat", Integer, primary_key=True),
    Column("account_id", Text),
    Column("display_name", Text),
    Column("occupant_kind", Text),
    Column("ready", Boolean, nullable=False, server_default=false()),
    CheckConstraint("account_id IS NOT NULL OR NOT ready", name="chairs_ready_only_when_occupied"),
    CheckConstraint("(account_id IS NULL) = (occupant_kind IS NULL)", name="chairs_kind_only_when_occupied"),
    one_of("occupant_kind", (kind.value for kind in OccupantKind), "chairs_occupant_kind_is_a_kind"),
)

SKAT_HOLDER: Final = "skat"
SUIT_TEXT: Final = {Suit.KARO: "diamonds", Suit.HERZ: "hearts", Suit.PIK: "spades", Suit.KREUZ: "clubs"}
RANK_TEXT: Final = {
    Rank.SEVEN: "seven",
    Rank.EIGHT: "eight",
    Rank.NINE: "nine",
    Rank.TEN: "ten",
    Rank.JACK: "jack",
    Rank.QUEEN: "queen",
    Rank.KING: "king",
    Rank.ACE: "ace",
}
GAME_TEXT: Final = {
    GameKind.KARO: "karo",
    GameKind.HERZ: "herz",
    GameKind.PIK: "pik",
    GameKind.KREUZ: "kreuz",
    GameKind.GRAND: "grand",
    GameKind.NULL: "null",
}
ANNOUNCEMENT_TEXT: Final = {
    Announcement.NONE: "none",
    Announcement.SCHNEIDER: "schneider",
    Announcement.SCHWARZ: "schwarz",
}
SUIT_OF_TEXT: Final = {text: suit for suit, text in SUIT_TEXT.items()}
RANK_OF_TEXT: Final = {text: rank for rank, text in RANK_TEXT.items()}
POSITION_OF_TEXT: Final = {text: position for position, text in POSITION_TEXT.items()}
GAME_OF_TEXT: Final = {text: kind for kind, text in GAME_TEXT.items()}
ANNOUNCEMENT_OF_TEXT: Final = {text: announcement for announcement, text in ANNOUNCEMENT_TEXT.items()}


class StepLogRewrittenError(Exception):
    """The steps being saved do not continue the stored ones: an earlier step would change."""


def unstored_steps[Step](table_id: str, stored: tuple[Step, ...], steps: tuple[Step, ...]) -> tuple[Step, ...]:
    """The steps not yet stored; stored steps that are no prefix of `steps` raise."""
    if steps[: len(stored)] != stored:
        message = f"the steps saved for table {table_id} do not continue the stored ones"
        raise StepLogRewrittenError(message)
    return steps[len(stored) :]


hand_cards = Table(
    "hand_cards",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("suit", Text, primary_key=True),
    Column("rank", Text, primary_key=True),
    Column("holder", Text, nullable=False),
    one_of("suit", SUIT_TEXT.values(), "hand_cards_suit_is_a_suit"),
    one_of("rank", RANK_TEXT.values(), "hand_cards_rank_is_a_rank"),
    one_of("holder", (*POSITION_TEXT.values(), SKAT_HOLDER), "hand_cards_holder_is_a_holder"),
)

receipts = Table(
    "receipts",
    metadata,
    Column("account_id", Text, primary_key=True),
    Column("command_id", Text, primary_key=True),
    Column("command", Text, nullable=False),
    Column("payload", Text, nullable=False),
    Column("table_id", Text, nullable=False),
    Column("refusal", Text),
    Column("holder", Text),
    ForeignKeyConstraint(["table_id"], [tables.c.id]),
)
