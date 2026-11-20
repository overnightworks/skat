"""A seat's private plan for the auction, „halten bis“ or „Weg“ said ahead, lives in a table of its own beside the
chair it belongs to, with the account that made it: it is read only while that account still sits there.

Expand only, so the release before this one serves on the new schema and ignores the table. It ends a table by deleting
its chairs, which takes the plans with them (`ON DELETE CASCADE`). It deals a hand by inserting the hand's cards, so a
trigger clears the table's plans on that insert: a plan never outlives its hand, whichever release deals. The trigger
goes with the release before this one.
"""

from alembic import op

revision = "0057"
down_revision = "0056"

LADDER = (
    "18, 20, 22, 23, 24, 27, 30, 33, 35, 36, 40, 44, 45, 46, 48, 50, 54, 55, 59, 60, 63, 66, 70, 72, 77, 80, 81, 84,"
    " 88, 90, 96, 99, 100, 108, 110, 117, 120, 121, 126, 130, 132, 135, 140, 143, 144, 150, 153, 154, 156, 160, 162,"
    " 165, 168, 170, 176, 180, 187, 192, 198, 204, 216, 240, 264"
)


def upgrade() -> None:
    op.execute(
        "CREATE TABLE auction_plans ("
        " table_id text NOT NULL,"
        " seat integer NOT NULL,"
        " account_id text NOT NULL,"
        " kind text NOT NULL,"
        " value smallint,"
        " mode text,"
        " PRIMARY KEY (table_id, seat),"
        " FOREIGN KEY (table_id, seat) REFERENCES chairs (table_id, seat) ON DELETE CASCADE,"
        " CONSTRAINT auction_plans_kind_is_a_kind CHECK (kind IN ('limit', 'pass')),"
        " CONSTRAINT auction_plans_mode_is_a_mode CHECK (mode IN ('fixed', 'ask')),"
        " CONSTRAINT auction_plans_a_limit_has_a_value_and_a_mode"
        " CHECK ((kind = 'limit') = (value IS NOT NULL AND mode IS NOT NULL)),"
        " CONSTRAINT auction_plans_a_pass_has_no_value_and_no_mode"
        " CHECK ((kind = 'pass') = (value IS NULL AND mode IS NULL)),"
        f" CONSTRAINT auction_plans_value_is_a_bid CHECK (value IN ({LADDER})))"
    )
    op.execute(
        """
        CREATE FUNCTION a_deal_clears_the_auction_plans() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            DELETE FROM auction_plans WHERE table_id IN (SELECT table_id FROM dealt);
            RETURN NULL;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER a_deal_clears_the_auction_plans AFTER INSERT ON hand_cards "
        "REFERENCING NEW TABLE AS dealt FOR EACH STATEMENT EXECUTE FUNCTION a_deal_clears_the_auction_plans()"
    )
