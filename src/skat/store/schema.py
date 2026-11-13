from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
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
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.engine.schieberamsch import GrandHandRule, PushingRule
from skat.table.records import (
    SERIES_LENGTH_MAX,
    SERIES_LENGTH_MIN,
    SERIES_LENGTH_STEP,
    EndReason,
    OccupantKind,
    RamschOccasion,
    RamschSetting,
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


def _ramsch_columns() -> tuple[Column[Any], ...]:
    return (
        Column("ramsch_occasion", Text),
        Column("ramsch_scoring", Text),
        Column("ramsch_jungfrau", Text),
        Column("ramsch_durchmarsch", Text),
        Column("ramsch_pushing", Text),
        Column("ramsch_grand_hand", Text),
    )


def _ramsch_checks(table_name: str) -> tuple[CheckConstraint, ...]:
    return (
        CheckConstraint(
            "num_nonnulls(ramsch_occasion, ramsch_scoring, ramsch_jungfrau, ramsch_durchmarsch) IN (0, 4)",
            name=f"{table_name}_ramsch_is_all_or_nothing",
        ),
        one_of(
            "ramsch_occasion",
            (occasion.value for occasion in RamschOccasion),
            f"{table_name}_ramsch_occasion_is_an_occasion",
        ),
        one_of(
            "ramsch_scoring",
            (scoring.value for scoring in RamschScoring),
            f"{table_name}_ramsch_scoring_is_a_scoring",
        ),
        one_of(
            "ramsch_jungfrau",
            (rule.value for rule in JungfrauRule),
            f"{table_name}_ramsch_jungfrau_is_a_jungfrau_rule",
        ),
        one_of(
            "ramsch_durchmarsch",
            (rule.value for rule in DurchmarschRule),
            f"{table_name}_ramsch_durchmarsch_is_a_durchmarsch_rule",
        ),
        one_of(
            "ramsch_pushing", (rule.value for rule in PushingRule), f"{table_name}_ramsch_pushing_is_a_pushing_rule"
        ),
        CheckConstraint(
            "ramsch_pushing IS NULL OR ramsch_occasion IS NOT NULL", name=f"{table_name}_ramsch_pushing_needs_a_ramsch"
        ),
        one_of(
            "ramsch_grand_hand",
            (rule.value for rule in GrandHandRule),
            f"{table_name}_ramsch_grand_hand_is_a_grand_hand_rule",
        ),
        CheckConstraint(
            "ramsch_grand_hand IS NULL OR ramsch_pushing IS NOT NULL",
            name=f"{table_name}_ramsch_grand_hand_needs_pushing",
        ),
    )


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
        *_ramsch_columns(),
        *_ramsch_checks(table_name),
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
    ramsch = None
    if row.ramsch_occasion is not None:
        ramsch = RamschSetting(
            RamschOccasion(row.ramsch_occasion),
            RamschOptions(
                RamschScoring(row.ramsch_scoring),
                JungfrauRule(row.ramsch_jungfrau),
                DurchmarschRule(row.ramsch_durchmarsch),
            ),
            None if row.ramsch_pushing is None else PushingRule(row.ramsch_pushing),
            GrandHandRule.OFF if row.ramsch_grand_hand is None else GrandHandRule(row.ramsch_grand_hand),
        )
    return TableOptions(show_running_points=row.show_running_points, kontra=kontra, bock=bock, ramsch=ramsch)


def option_values(options: TableOptions) -> dict[str, object]:
    """The column values that store the options, as `options_of` reads them back."""
    kontra = options.kontra
    bock = options.bock
    ramsch = options.ramsch
    return {
        "show_running_points": options.show_running_points,
        "kontra_sayer": None if kontra is None else kontra.sayer.value,
        "kontra_reach": None if kontra is None else kontra.reach.value,
        "kontra_deadline": None if kontra is None else kontra.deadline.value,
        # sorted by token, so the column reads the same however the request listed the triggers
        "bock_triggers": None if bock is None else sorted(trigger.value for trigger in bock.triggers),
        "bock_overlap": None if bock is None else bock.overlap.value,
        "ramsch_occasion": None if ramsch is None else ramsch.occasion.value,
        "ramsch_scoring": None if ramsch is None else ramsch.reckoning.scoring.value,
        "ramsch_jungfrau": None if ramsch is None else ramsch.reckoning.jungfrau.value,
        "ramsch_durchmarsch": None if ramsch is None else ramsch.reckoning.durchmarsch.value,
        "ramsch_pushing": None if ramsch is None or ramsch.pushing is None else ramsch.pushing.value,
        "ramsch_grand_hand": None if ramsch is None or ramsch.pushing is None else ramsch.grand_hand.value,
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
    Column("unplayed_days", Integer),
    Column("empty_since", DateTime(timezone=True)),
    Column("last_played_at", DateTime(timezone=True)),
    Column("opener_name", Text),
    Column("series_length", SmallInteger),
    Column("series_deals", SmallInteger),
    Column("series_number", SmallInteger, nullable=False, server_default="1"),
    Column("series_ended_early", Boolean, nullable=False, server_default=false()),
    Column("series_end_proposer", SmallInteger),
    Column("series_end_accepter", SmallInteger),
    Column("give_up_asked_by", Text),
    Column("give_up_declined_by", Text),
    Column("abort_yes_seats", ARRAY(SmallInteger), nullable=False, server_default=text("'{}'")),
    Column("hand_aborted", Boolean, nullable=False, server_default=false()),
    *option_columns("tables"),
    Column("bock_rounds", ARRAY(SmallInteger), nullable=False, server_default=text("'{}'")),
    CheckConstraint("dealer BETWEEN 1 AND 3", name="tables_dealer_is_a_seat"),
    CheckConstraint("(ended_at IS NULL) = (end_reason IS NULL)", name="tables_end_time_comes_with_its_reason"),
    CheckConstraint(
        f"(empty_seconds IS NOT NULL) = (end_reason IS NOT DISTINCT FROM '{EndReason.EMPTY.value}')",
        name="tables_empty_seconds_only_for_an_empty_end",
    ),
    CheckConstraint("empty_seconds > 0", name="tables_empty_seconds_are_positive"),
    CheckConstraint(
        f"(unplayed_days IS NOT NULL) = (end_reason IS NOT DISTINCT FROM '{EndReason.UNPLAYED.value}')",
        name="tables_unplayed_days_only_for_an_unplayed_end",
    ),
    CheckConstraint("unplayed_days > 0", name="tables_unplayed_days_are_positive"),
    CheckConstraint(
        "(dealer IS NULL) = (last_played_at IS NULL)", name="tables_a_dealt_table_has_its_last_played_time"
    ),
    CheckConstraint("ended_at IS NULL OR opener_name IS NULL", name="tables_an_ended_table_keeps_no_opener_name"),
    CheckConstraint("char_length(opener_name) >= 1", name="tables_opener_name_is_not_empty"),
    CheckConstraint("(series_length IS NULL) = (series_deals IS NULL)", name="tables_series_is_both_or_neither"),
    CheckConstraint(
        f"series_length BETWEEN {SERIES_LENGTH_MIN} AND {SERIES_LENGTH_MAX}"
        f" AND series_length % {SERIES_LENGTH_STEP} = 0",
        name="tables_series_length_is_a_length",
    ),
    CheckConstraint("series_deals BETWEEN 0 AND series_length", name="tables_series_deals_are_within_the_length"),
    CheckConstraint("series_number >= 1", name="tables_series_number_is_a_number"),
    CheckConstraint("series_length IS NOT NULL OR series_number = 1", name="tables_series_numbers_only_with_a_series"),
    CheckConstraint(
        "series_end_proposer BETWEEN 1 AND 3 AND series_end_accepter BETWEEN 1 AND 3",
        name="tables_series_end_seats_are_seats",
    ),
    CheckConstraint(
        "series_end_accepter IS NULL"
        " OR (series_end_proposer IS NOT NULL AND series_end_accepter <> series_end_proposer)",
        name="tables_series_end_accepter_follows_a_proposer",
    ),
    CheckConstraint(
        "series_length IS NOT NULL OR (series_end_proposer IS NULL AND NOT series_ended_early)",
        name="tables_series_end_needs_a_series",
    ),
    CheckConstraint(
        "NOT series_ended_early OR series_end_proposer IS NULL", name="tables_series_ended_early_holds_no_proposal"
    ),
    one_of("end_reason", (reason.value for reason in EndReason), "tables_end_reason_is_a_reason"),
    one_of("give_up_asked_by", POSITION_TEXT.values(), "tables_give_up_asker_is_a_position"),
    one_of("give_up_declined_by", POSITION_TEXT.values(), "tables_give_up_decliner_is_a_position"),
    CheckConstraint(
        "give_up_declined_by IS NULL OR give_up_asked_by IS NOT NULL", name="tables_give_up_no_comes_with_an_ask"
    ),
    CheckConstraint("give_up_declined_by <> give_up_asked_by", name="tables_give_up_no_comes_from_another_position"),
    CheckConstraint(
        "abort_yes_seats <@ ARRAY[1, 2, 3]::smallint[] AND array_position(abort_yes_seats, NULL) IS NULL",
        name="tables_abort_yes_are_seats",
    ),
    CheckConstraint(
        "NOT hand_aborted OR cardinality(abort_yes_seats) = 0", name="tables_an_aborted_hand_holds_no_proposal"
    ),
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
    # Who an agent at this chair works for, as its token named them when it sat; it goes with the chair.
    Column("owner_account", Text),
    Column("ready", Boolean, nullable=False, server_default=false()),
    # The accounts that held this chair in the running hand and left it; they no longer sit here, so a query of an
    # account's tables reads `account_id` and never counts them.
    Column("held_in_hand", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    # The name of whoever last held this chair in the running hand and left it, while the chair stays open.
    Column("former_holder_name", Text),
    CheckConstraint("account_id IS NOT NULL OR NOT ready", name="chairs_ready_only_when_occupied"),
    CheckConstraint("array_position(held_in_hand, NULL) IS NULL", name="chairs_held_in_hand_has_no_null"),
    CheckConstraint("(account_id IS NULL) = (occupant_kind IS NULL)", name="chairs_kind_only_when_occupied"),
    one_of("occupant_kind", (kind.value for kind in OccupantKind), "chairs_occupant_kind_is_a_kind"),
    CheckConstraint(
        f"owner_account IS NULL OR occupant_kind IS NOT DISTINCT FROM '{OccupantKind.AGENT.value}'",
        name="chairs_owner_only_of_an_agent",
    ),
    Index("chairs_by_account", "account_id", postgresql_where=text("account_id IS NOT NULL")),
)

member_book = Table(
    "member_book",
    metadata,
    Column("table_id", Text, ForeignKey(tables.c.id), primary_key=True),
    Column("agent_account", Text, primary_key=True),
    Column("epoch", Integer, nullable=False, server_default="0"),
    Column("invitation_id", Text),
    Column("invitation_expires_at", DateTime(timezone=True)),
    Column("owner_account", Text),
    Column("inviter_account", Text),
    Column("ended_outcome", Text),
    CheckConstraint(
        "num_nonnulls(invitation_id, invitation_expires_at, owner_account, inviter_account) IN (0, 4)",
        name="member_book_invitation_is_all_or_nothing",
    ),
    CheckConstraint(
        "ended_outcome IS NULL OR invitation_id IS NOT NULL", name="member_book_an_outcome_ends_an_invitation"
    ),
    CheckConstraint("epoch >= 0", name="member_book_epoch_is_not_negative"),
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
