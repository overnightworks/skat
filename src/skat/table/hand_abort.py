"""The vote of the seated players to abort a hand while one of its chairs is open: the first yes proposes, more than
half of the seated chairs end the hand, a no clears the proposal. The majority and the aborted end are `rules`, which
every change of a chair passes.
"""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from skat.table.records import Decision, Refusal, TableRecord
from skat.table.rules import abort_agreed, aborted_hand, hand_runs, seat_of, waiting_seat_of

if TYPE_CHECKING:
    from skat.table.records import Actor

AGREE_TO_ABORT_COMMAND: Final = "agree-to-abort-hand"
REFUSE_TO_ABORT_COMMAND: Final = "refuse-to-abort-hand"


@dataclass(frozen=True)
class AbortVoteCommand:
    """A yes or a no to aborting the running hand; the chair comes from the session."""

    command_id: str
    table_id: str


def abort_vote_payload(command: AbortVoteCommand) -> str:
    """The receipt's payload: the table alone, because a proposal has no number a client could name."""
    return command.table_id


def decide_agree_to_abort(table: TableRecord, actor: Actor) -> Decision:
    """Yes to aborting the running hand: it proposes, or adds to the standing proposal and ends the hand at once when
    the yeses are more than half of the seated chairs. No chair, no hand, then no open chair of it refuse. A seat that
    already said yes changes nothing.
    """
    chair = seat_of(table, actor.account_id)
    if chair is None:
        return Decision(table, Refusal.NOT_SEATED)
    if not hand_runs(table):
        return Decision(table, Refusal.NO_HAND)
    if waiting_seat_of(table) is None:
        return Decision(table, Refusal.HAND_NOT_OPEN)
    if chair.seat in table.progress.abort_yes:
        return Decision(table)
    agreed = TableRecord(
        id=table.id,
        version=table.version + 1,
        chairs=table.chairs,
        dealer=table.dealer,
        hand=table.hand,
        progress=replace(table.progress, abort_yes=table.progress.abort_yes | {chair.seat}),
        game_list=table.game_list,
        series=table.series,
        options=table.options,
        bock=table.bock,
        visibility=table.visibility,
    )
    return Decision(aborted_hand(agreed) if abort_agreed(agreed) else agreed)


def decide_refuse_to_abort(table: TableRecord, actor: Actor) -> Decision:
    """No to aborting the hand: the proposal goes and the hand keeps waiting; no chair, then no proposal refuse."""
    if seat_of(table, actor.account_id) is None:
        return Decision(table, Refusal.NOT_SEATED)
    if not table.progress.abort_yes:
        return Decision(table, Refusal.NO_PROPOSAL)
    cleared = replace(table.progress, abort_yes=frozenset())
    return Decision(replace(table, version=table.version + 1, progress=cleared))
