"""A hand's state as one typed log: `hand_steps` holds the steps of the table's latest hand in the order its acts
take, and `hands` its standing state with the table version it was last written for.

Expand only, so the release before this one serves on the new schema and ignores both tables. It keeps writing the
step tables and the table row's hand columns alone, which leaves `hands.stamp_version` behind the table's version: this
release reads the new tables only while the stamp equals the version, and reads the old store otherwise. A table the
release before ends keeps its rows in the new tables, which no release reads for an ended table, until the forgetting
sweep deletes the table and `ON DELETE CASCADE` takes them with it.
"""

from alembic import op

revision = "0060"
down_revision = "0059"

POSITIONS = "'forehand', 'middlehand', 'rearhand'"
SUITS = "'diamonds', 'hearts', 'spades', 'clubs'"
RANKS = "'seven', 'eight', 'nine', 'ten', 'jack', 'queen', 'king', 'ace'"
ANNOUNCEMENTS = "'none', 'schneider', 'schwarz'"
KINDS = (
    "'deal', 'bid', 'hold', 'pass', 'play', 'take-skat', 'put-back', 'declare', 'stage-take', 'stage-put',"
    " 'stage-push', 'stage-grand-hand', 'card', 'word'"
)


def upgrade() -> None:
    _create_hand_steps()
    _create_hands()


def _create_hand_steps() -> None:
    op.execute(
        "CREATE TABLE hand_steps ("
        " table_id text NOT NULL REFERENCES tables (id) ON DELETE CASCADE,"
        " ordinal smallint NOT NULL,"
        " kind text NOT NULL,"
        " position text,"
        " value smallint,"
        " suit text,"
        " rank text,"
        " second_suit text,"
        " second_rank text,"
        " game text,"
        " hand boolean,"
        " ouvert boolean,"
        " announcement text,"
        " word text,"
        " traceparent text,"
        " PRIMARY KEY (table_id, ordinal),"
        f" CONSTRAINT hand_steps_kind_is_a_kind CHECK (kind IN ({KINDS})),"
        f" CONSTRAINT hand_steps_position_is_a_position CHECK (position IN ({POSITIONS})),"
        f" CONSTRAINT hand_steps_suit_is_a_suit CHECK (suit IN ({SUITS})),"
        f" CONSTRAINT hand_steps_rank_is_a_rank CHECK (rank IN ({RANKS})),"
        f" CONSTRAINT hand_steps_second_suit_is_a_suit CHECK (second_suit IN ({SUITS})),"
        f" CONSTRAINT hand_steps_second_rank_is_a_rank CHECK (second_rank IN ({RANKS})),"
        " CONSTRAINT hand_steps_game_is_a_game CHECK (game IN ('karo', 'herz', 'pik', 'kreuz', 'grand', 'null')),"
        f" CONSTRAINT hand_steps_announcement_is_an_announcement CHECK (announcement IN ({ANNOUNCEMENTS})),"
        " CONSTRAINT hand_steps_word_is_a_word CHECK (word IN ('kontra', 're', 'supra', 'hirsch')))"
    )
    op.execute("CREATE UNIQUE INDEX hand_steps_each_card_once ON hand_steps (table_id, suit, rank) WHERE kind = 'card'")


def _create_hands() -> None:
    op.execute(
        "CREATE TABLE hands ("
        " table_id text PRIMARY KEY REFERENCES tables (id) ON DELETE CASCADE,"
        " give_up_asked_by text,"
        " give_up_declined_by text,"
        " give_up_claim text,"
        " give_up_agreed_by text,"
        " give_up_open boolean NOT NULL DEFAULT false,"
        " shortening_refused_by text,"
        " played_open text[] NOT NULL DEFAULT '{}',"
        " abort_yes_seats smallint[] NOT NULL DEFAULT '{}',"
        " aborted boolean NOT NULL DEFAULT false,"
        " end_traceparent text,"
        " stamp_version integer NOT NULL,"
        f" CONSTRAINT hands_give_up_asker_is_a_position CHECK (give_up_asked_by IN ({POSITIONS})),"
        f" CONSTRAINT hands_give_up_decliner_is_a_position CHECK (give_up_declined_by IN ({POSITIONS})),"
        " CONSTRAINT hands_give_up_no_comes_with_an_ask"
        " CHECK (give_up_declined_by IS NULL OR give_up_asked_by IS NOT NULL),"
        " CONSTRAINT hands_give_up_no_comes_from_another_position CHECK (give_up_declined_by <> give_up_asked_by),"
        f" CONSTRAINT hands_give_up_claim_is_an_announcement CHECK (give_up_claim IN ({ANNOUNCEMENTS})),"
        f" CONSTRAINT hands_give_up_agreer_is_a_position CHECK (give_up_agreed_by IN ({POSITIONS})),"
        f" CONSTRAINT hands_shortening_refuser_is_a_position CHECK (shortening_refused_by IN ({POSITIONS})),"
        " CONSTRAINT hands_give_up_claim_comes_with_an_ask"
        " CHECK (give_up_claim IS NULL OR give_up_asked_by IS NOT NULL),"
        " CONSTRAINT hands_give_up_yes_is_to_a_shortening_by_another"
        " CHECK (give_up_agreed_by IS NULL OR (give_up_claim IS NOT NULL AND give_up_agreed_by <> give_up_asked_by)),"
        " CONSTRAINT hands_a_shortening_ends_with_its_first_no"
        " CHECK (give_up_claim IS NULL OR give_up_declined_by IS NULL),"
        " CONSTRAINT hands_an_open_play_is_asked_of_the_declarer_alone"
        " CHECK (NOT give_up_open OR (give_up_asked_by IS NOT NULL AND give_up_claim IS NULL"
        " AND give_up_declined_by IS NULL AND give_up_agreed_by IS NULL)),"
        " CONSTRAINT hands_played_open_are_positions"
        f" CHECK (played_open <@ ARRAY[{POSITIONS}]::text[] AND array_position(played_open, NULL) IS NULL),"
        " CONSTRAINT hands_abort_yes_are_seats"
        " CHECK (abort_yes_seats <@ ARRAY[1, 2, 3]::smallint[] AND array_position(abort_yes_seats, NULL) IS NULL),"
        " CONSTRAINT hands_an_aborted_hand_holds_no_proposal CHECK (NOT aborted OR cardinality(abort_yes_seats) = 0))"
    )
