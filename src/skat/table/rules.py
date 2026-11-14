from dataclasses import dataclass, replace
from datetime import UTC, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Final, overload

from skat.engine.bock import BockRounds, advance
from skat.engine.deal import deal, draw_dealer, next_dealer, positions_from
from skat.engine.kontra import KontraDeadline
from skat.engine.schieberamsch import GrandHandRule
from skat.table.records import (
    Actor,
    Chair,
    CreateTable,
    Decision,
    EndProposal,
    FormerHolder,
    GiveUpAsked,
    HandProgress,
    NewHand,
    NoWordSaid,
    Occupant,
    Receipt,
    Refusal,
    Replay,
    SeatHeld,
    Series,
    SitDown,
    StandUp,
    TableId,
    TableRecord,
    Visibility,
)

if TYPE_CHECKING:
    import random
    from collections.abc import Callable
    from datetime import datetime

    from skat.engine.bock import BockOptions
    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.table.records import EndedTable, RamschSetting, TableOptions

CHAIRS_PER_TABLE: Final = 3
FIRST_VERSION: Final = 1
CREATE_TABLE_COMMAND: Final = "create-table"
SIT_DOWN_COMMAND: Final = "sit-down"
STAND_UP_COMMAND: Final = "stand-up"
PLAY_CARD_COMMAND: Final = "play-card"
GIVE_UP_COMMAND: Final = "give-up"
SHORTEN_COMMAND: Final = "shorten"
PLAY_OPEN_COMMAND: Final = "play-open"
THROW_DOWN_COMMAND: Final = "throw-down"
AGREE_TO_GIVE_UP_COMMAND: Final = "give-up-agree"
DECLINE_GIVE_UP_COMMAND: Final = "give-up-decline"
STEP_OF_PLAY_COMMANDS: Final = frozenset(
    {
        PLAY_CARD_COMMAND,
        GIVE_UP_COMMAND,
        SHORTEN_COMMAND,
        PLAY_OPEN_COMMAND,
        AGREE_TO_GIVE_UP_COMMAND,
        THROW_DOWN_COMMAND,
    }
)


class CommandIdReusedError(Exception):
    """A command id came back with a request other than the one it first carried."""


def decide_create(
    actor: Actor, table_id: TableId, series_length: int | None, options: TableOptions, visibility: Visibility
) -> TableRecord:
    """A new table with its opener in chair 1 and the other chairs free, a series of no deals if it has a length, the
    options it is opened with and the visibility it is listed by.
    """
    opener = Chair(1, Occupant(actor.account_id, actor.display_name, actor.kind, actor.owner_account))
    return TableRecord(
        id=table_id,
        version=FIRST_VERSION,
        chairs=(opener, *(Chair(seat, None) for seat in range(2, CHAIRS_PER_TABLE + 1))),
        dealer=None,
        hand=None,
        progress=HandProgress(),
        game_list=(),
        series=None if series_length is None else Series(series_length, 0),
        options=options,
        bock=BockRounds.start(),
        visibility=visibility,
    )


def _pushing_member(ramsch: RamschSetting) -> str:
    if ramsch.pushing is None:
        return ""
    grand_hand = '"grand_hand":"allowed",' if ramsch.grand_hand is GrandHandRule.ALLOWED else ""
    return f'"pushing":{{{grand_hand}"rule":"{ramsch.pushing.value}"}},'


def create_payload(command: CreateTable) -> str:
    """The receipt's payload: a table with no length and every option off keeps the text it always had, so older
    receipts replay; an option that is on adds its own member, the Grand Hand a stage allows among them, and so does a
    private table, while an open one adds none.
    """
    members = [] if command.series_length is None else [f'"series_length":{command.series_length}']
    if command.options.show_running_points:
        members.append('"show_running_points":true')
    kontra = command.options.kontra
    if kontra is not None:
        members.append(
            f'"kontra":{{"sayer":"{kontra.sayer.value}","reach":"{kontra.reach.value}",'
            f'"deadline":"{kontra.deadline.value}"}}'
        )
    bock = command.options.bock
    if bock is not None:
        triggers = ",".join(f'"{trigger.value}"' for trigger in sorted(bock.triggers))
        members.append(f'"bock":{{"overlap":"{bock.overlap.value}","triggers":[{triggers}]}}')
    ramsch = command.options.ramsch
    if ramsch is not None:
        members.append(
            f'"ramsch":{{"durchmarsch":"{ramsch.reckoning.durchmarsch.value}",'
            f'"jungfrau":"{ramsch.reckoning.jungfrau.value}","occasion":"{ramsch.occasion.value}",'
            f'{_pushing_member(ramsch)}"scoring":"{ramsch.reckoning.scoring.value}"}}'
        )
    if command.visibility is Visibility.PRIVATE:
        members.append(f'"visibility":"{Visibility.PRIVATE.value}"')
    return "{" + ",".join(members) + "}"


def create_receipt(actor: Actor, command: CreateTable, table: TableRecord) -> Receipt:
    return Receipt(actor.account_id, command.command_id, CREATE_TABLE_COMMAND, create_payload(command), table.id)


def replayed_table(replay: Replay, command: CreateTable) -> TableRecord | EndedTable:
    """The table a create request already made; any other request under its key is refused."""
    return _replayed(replay, CREATE_TABLE_COMMAND, create_payload(command)).table


def _replayed(replay: Replay, command: str, payload: str) -> Replay:
    if (replay.command, replay.payload) != (command, payload):
        raise CommandIdReusedError
    return replay


def seat_of(table: TableRecord, account_id: str) -> Chair | None:
    return next((chair for chair in table.chairs if chair.occupant and chair.occupant.account_id == account_id), None)


def with_occupant(table: TableRecord, seat: int, occupant: Occupant | None) -> TableRecord:
    """The table with a chair's new occupant, the one way a chair changes hands.

    A freed chair is never ready, and whoever sits while a result is pending counts as ready, unless the series is
    over: a mark at the end is consent to „Neue Serie“, which only a tap gives. The chair's holder leaves his part of
    a standing end proposal, of a standing give-up request, of a standing proposal to abort the hand and his no-word
    answers behind. While a hand runs, he is also marked as having held this chair, which bars him from any other
    chair of the hand. A change that leaves no chair of the hand open clears the proposal to abort it, and a change
    that makes the standing yeses more than half of the seated chairs ends the hand at once, in the same version.
    """
    ready = occupant is not None and result_pending(table) and not series_over(table)
    chairs = tuple(Chair(seat, occupant, ready=ready) if chair.seat == seat else chair for chair in table.chairs)
    series = table.series
    if series is not None:
        series = replace(series, end_proposal=_proposal_without(series.end_proposal, seat))
    changed = TableRecord(
        id=table.id,
        version=table.version + 1,
        chairs=chairs,
        dealer=table.dealer,
        hand=table.hand,
        progress=replace(
            table.progress,
            give_up=_give_up_without(table, seat),
            no_words=_no_words_without(table, seat),
            seats_held=_seats_held_after(table, seat, occupant),
            former_holders=_former_holders_after(table, seat, occupant),
            abort_yes=table.progress.abort_yes - {seat},
        ),
        game_list=table.game_list,
        series=series,
        options=table.options,
        bock=table.bock,
        visibility=table.visibility,
    )
    return _abort_if_agreed(_abort_while_open(changed))


def _seats_held_after(table: TableRecord, seat: int, occupant: Occupant | None) -> frozenset[SeatHeld]:
    """The marks once a chair changes hands: a chair freed in a running hand marks its leaver, nothing else does."""
    leaver = table.chairs[seat - 1].occupant
    if occupant is not None or leaver is None or not hand_runs(table):
        return table.progress.seats_held
    return table.progress.seats_held | {SeatHeld(leaver.account_id, seat)}


def _former_holders_after(table: TableRecord, seat: int, occupant: Occupant | None) -> frozenset[FormerHolder]:
    """The former holders once a chair changes hands: a chair freed in a running hand names its leaver, and one taken
    names nobody.
    """
    leaver = table.chairs[seat - 1].occupant
    others = frozenset(holder for holder in table.progress.former_holders if holder.seat != seat)
    if occupant is not None or leaver is None or not hand_runs(table):
        return others
    return others | {FormerHolder(seat, leaver.display_name)}


def _proposal_without(proposal: EndProposal | None, seat: int) -> EndProposal | None:
    """A chair's change takes its holder's part of the proposal: the proposer's goes with the proposal, an accepter's
    acceptance alone, anyone else's changes nothing.
    """
    if proposal is None or proposal.proposer == seat:
        return None
    if proposal.accepter == seat:
        return EndProposal(proposal.proposer)
    return proposal


def _give_up_without(table: TableRecord, seat: int) -> GiveUpAsked | None:
    """A chair's change takes its holder's part of the standing request: the asker's goes with the request, an
    opponent's no to a give-up or yes to a shortening alone, anyone else's changes nothing.
    """
    asked = table.progress.give_up
    if asked is None or table.dealer is None:
        return asked
    position = positions_from(table.dealer)[seat]
    if asked.asker is position:
        return None
    if asked.declined_by is position:
        return GiveUpAsked(asked.asker)
    if asked.agreed_by is position:
        return GiveUpAsked(asked.asker, claim=asked.claim)
    return asked


def _no_words_without(table: TableRecord, seat: int) -> frozenset[NoWordSaid]:
    """A chair's change takes its holder's answers of no word, so whoever sits there is asked the word afresh; at a
    table whose words end with the first card the answer is a decline for good and stays with the seat.
    """
    kontra = table.options.kontra
    if table.dealer is None or (kontra is not None and kontra.deadline is KontraDeadline.FIRST_CARD):
        return table.progress.no_words
    position = positions_from(table.dealer)[seat]
    return frozenset(answered for answered in table.progress.no_words if answered.position is not position)


def abort_agreed(table: TableRecord) -> bool:
    """The seats that voted to abort the running hand are more than half of the seated chairs: one of one, two of two,
    two of three.
    """
    seated = sum(chair.occupant is not None for chair in table.chairs)
    return 2 * len(table.progress.abort_yes) > seated


def _abort_while_open(table: TableRecord) -> TableRecord:
    """The table with no proposal to abort once no chair of its hand is open, since the hand moves again."""
    if waiting_seat_of(table) is not None or not table.progress.abort_yes:
        return table
    return TableRecord(
        id=table.id,
        version=table.version,
        chairs=table.chairs,
        dealer=table.dealer,
        hand=table.hand,
        progress=replace(table.progress, abort_yes=frozenset()),
        game_list=table.game_list,
        series=table.series,
        options=table.options,
        bock=table.bock,
        visibility=table.visibility,
    )


def _abort_if_agreed(table: TableRecord) -> TableRecord:
    return aborted_hand(table) if abort_agreed(table) else table


def aborted_hand(table: TableRecord) -> TableRecord:
    """The table once the vote ended its running hand, in the table's version: no hand, no entry, no result and no
    step is kept, and the deal counted when it was dealt stays. The hand uses up a Bock game and meets no trigger,
    since it was no pass.
    """
    bock = bock_rounds_after(table, lambda _options: False)
    return TableRecord(
        id=table.id,
        version=table.version,
        chairs=table.chairs,
        dealer=table.dealer,
        hand=None,
        progress=HandProgress(aborted=True),
        game_list=table.game_list,
        series=table.series,
        options=table.options,
        bock=bock,
        visibility=table.visibility,
    )


def bock_at_series_end() -> BockRounds:
    """The pending Bock rounds once a series ends, with its last game or early by consent: every round lapses."""
    return BockRounds.start()


def bock_rounds_after(table: TableRecord, triggered_by: Callable[[BockOptions], bool]) -> BockRounds:
    """The pending Bock rounds and Ramsch-round games once the table's running hand has ended: it uses up a Bock game,
    or a Ramsch-round game while no Bock game is pending, then a trigger acts by the option, and a Bock round it ended
    adds its Ramsch round at a table that plays one; no Bock options mean no rounds, and the series' last game lets
    every round lapse (an early end by consent goes through `skat.table.series_end`). `triggered_by` is asked only
    when the rounds go on.
    """
    options = table.options.bock
    if options is None:
        return BockRounds.start()
    if series_games_left(table) == 1:  # the running hand counts as a game left
        return bock_at_series_end()
    ramsch = table.options.ramsch
    ramsch_follows = ramsch is not None and ramsch.occasion.after_bock_rounds
    return advance(table.bock, options.overlap, triggered=triggered_by(options), ramsch_follows=ramsch_follows)


def sit_deals(table: TableRecord) -> bool:
    """A sit deals when it fills the last free chair, no hand runs, no result is pending and the series is not over."""
    free_chairs = sum(chair.occupant is None for chair in table.chairs)
    return free_chairs == 1 and not hand_runs(table) and not result_pending(table) and not series_over(table)


def hand_runs(table: TableRecord) -> bool:
    return table.hand is not None


def is_deal_or_step_of_play(command: str, before: TableRecord, after: TableRecord) -> bool:
    """An accepted decision dealt a hand, or was a step of play that changed the table.

    A step is a played card, a give-up or shortening request, its agreement or a throw-down whose table version rose: a
    second request while one stands changes nothing. A take, a put-back and a push are none of these. The third pass
    that starts a Ramsch deals nothing, since the hand runs before and after it.
    """
    dealt = not hand_runs(before) and hand_runs(after)
    return dealt or (command in STEP_OF_PLAY_COMMANDS and after.version > before.version)


def series_games_left(table: TableRecord) -> int | None:
    """The games the series still deals, a running hand included; None for a table with no series."""
    if table.series is None:
        return None
    return table.series.length - table.series.deals + hand_runs(table)


def series_number_of(table: TableRecord) -> int:
    """The number of the table's series, 1 for the first and for a table with no series."""
    return 1 if table.series is None else table.series.number


def series_over(table: TableRecord) -> bool:
    """The series ran its last game or ended early by consent, and no hand runs any more; a table with no series
    never ends.
    """
    ended_early = table.series is not None and table.series.ended_early and not hand_runs(table)
    return ended_early or series_games_left(table) == 0


def seated_if_hand_ended(before: TableRecord, after: TableRecord) -> frozenset[str]:
    """Who sat at the table when this change ended its hand; nobody when it ended none."""
    if not hand_runs(before) or hand_runs(after):
        return frozenset()
    return frozenset(chair.occupant.account_id for chair in after.chairs if chair.occupant is not None)


def dealt(table: TableRecord, new_hand: NewHand, *, version: int) -> TableRecord:
    """The table with a new hand: its dealer, its cards, an empty auction, no chair ready and one more deal counted
    in its series; at a series' end this deal is the next series' first, so the list empties, the count starts at
    one and the series' number rises. A deal clears the end proposal and the early end. Every deal goes through here.
    """
    starts_series = series_over(table)
    series = table.series
    if series is not None:
        series = replace(
            series,
            deals=1 if starts_series else series.deals + 1,
            ended_early=False,
            end_proposal=None,
            number=series.number + 1 if starts_series else series.number,
        )
    return TableRecord(
        id=table.id,
        version=version,
        chairs=tuple(replace(chair, ready=False) for chair in table.chairs),
        dealer=new_hand.dealer,
        hand=new_hand.hand,
        progress=HandProgress(),
        game_list=() if starts_series else table.game_list,
        series=series,
        options=table.options,
        bock=table.bock,
        visibility=table.visibility,
    )


def hand_was_dealt_by(dealer: int | None) -> bool:
    """A hand was dealt at some time, by the stored dealer: the store writes the dealer with the first hand."""
    return dealer is not None


def hand_was_dealt(table: TableRecord) -> bool:
    """A hand was dealt on the table at some time."""
    return hand_was_dealt_by(table.dealer)


def result_pending(table: TableRecord) -> bool:
    """A played game's result stands: no hand runs, a dealer and a list entry exist, and no auction steps are kept.

    A passed-in hand keeps its steps until the next deal, which tells it apart from a played one; an aborted hand
    leaves no result.
    """
    return (
        not hand_runs(table)
        and hand_was_dealt(table)
        and bool(table.game_list)
        and not table.progress.auction
        and not table.progress.aborted
    )


@overload
def present_at(
    table: TableRecord, streams: frozenset[str], leases: frozenset[str]
) -> frozenset[str]: ...  # pragma: no cover - an overload's body is its signature


@overload
def present_at(
    table: TableRecord, streams: frozenset[str] | None, leases: frozenset[str]
) -> frozenset[str] | None: ...  # pragma: no cover - an overload's body is its signature


def present_at(table: TableRecord, streams: frozenset[str] | None, leases: frozenset[str]) -> frozenset[str] | None:
    """Who counts as present at the table: whoever holds an open stream, and every occupant with a live lease; a
    lease never counts for anyone who does not sit here. None says the presence cannot tell any more.
    """
    if streams is None:
        return None
    occupants = {chair.occupant.account_id for chair in table.chairs if chair.occupant is not None}
    return streams | (leases & occupants)


def ends_empty(table: TableRecord, connected_accounts: frozenset[str] | None) -> bool:
    """A table ends for being empty only while no hand was dealt on it and nobody is connected; a table with a dealer
    pauses and is kept. None says the presence cannot tell any more.
    """
    return not hand_was_dealt(table) and connected_accounts is not None and not connected_accounts


def unplayed_end(last_played_at: datetime, days: int) -> datetime:
    """The instant, in UTC, a dealt table ends: `days` days after its last deal or step of play. The paused list names
    it and the end happens at it.
    """
    return last_played_at.astimezone(UTC) + timedelta(days=days)


def ends_unplayed(table: TableRecord, last_played_at: datetime | None, now: datetime, days: int) -> bool:
    """A table on which a hand was dealt ends once its `unplayed_end` has come, whether a hand runs or anybody is
    connected; a table with no hand dealt has no last played time and never ends this way.
    """
    return hand_was_dealt(table) and last_played_at is not None and unplayed_end(last_played_at, days) <= now


class PresenceStep(Enum):
    KEEP = "keep"
    STAMP = "stamp"
    CLEAR = "clear"
    END = "end"


def wait_left(empty_since: datetime, now: datetime, empty_seconds: int) -> timedelta:
    """What is left of a table's wait of `empty_seconds`, counted from the time since when nobody has been at it; the
    wait is up when nothing is left.
    """
    return timedelta(seconds=empty_seconds) - (now - empty_since)


def wait_up(empty_since: datetime, now: datetime, empty_seconds: int) -> bool:
    """Whether a table's wait is up: nothing is left of it."""
    return wait_left(empty_since, now, empty_seconds) <= timedelta(0)


def presence_step(
    table: TableRecord,
    connected_accounts: frozenset[str] | None,
    empty_since: datetime | None,
    now: datetime,
    empty_seconds: int,
) -> PresenceStep:
    """What a change of who is present does to the time since when nobody has been at the table: an empty table
    keeps an earlier time and gets one otherwise, only while no hand was dealt on it; a table someone is at loses
    its time, and ends instead when no hand was dealt and the time was already up. None says the presence cannot
    tell any more.
    """
    if connected_accounts is None:
        return PresenceStep.KEEP
    if not connected_accounts:
        return PresenceStep.STAMP if empty_since is None and not hand_was_dealt(table) else PresenceStep.KEEP
    if empty_since is None:
        return PresenceStep.KEEP
    if not hand_was_dealt(table) and wait_up(empty_since, now, empty_seconds):
        return PresenceStep.END
    return PresenceStep.CLEAR


class ResumeStep(Enum):
    SKIP = "skip"
    STAMP = "stamp"
    WAIT = "wait"
    END = "end"


@dataclass(frozen=True)
class Resume:
    """What the server's start does with a live table: its step and the seconds left of the wait it starts."""

    step: ResumeStep
    seconds_left: float


def resume_step(dealer: int | None, empty_since: datetime | None, now: datetime, empty_seconds: int) -> Resume:
    """What the server's start does with a live table, by the same rules as `presence_step`: a table with a dealt
    hand pauses and gets no wait; an undealt table with no time gets one and a full wait; one with a time waits for
    what is left of it, and ends once nothing is left.
    """
    if hand_was_dealt_by(dealer):
        return Resume(ResumeStep.SKIP, 0.0)
    if empty_since is None:
        return Resume(ResumeStep.STAMP, float(empty_seconds))
    if wait_up(empty_since, now, empty_seconds):
        return Resume(ResumeStep.END, 0.0)
    return Resume(ResumeStep.WAIT, wait_left(empty_since, now, empty_seconds).total_seconds())


def next_deal_due(table: TableRecord, connected_accounts: frozenset[str]) -> bool:
    """The next hand is due when no hand runs, the table has a dealer and all three occupants are connected; while a
    result is pending or at a series' end, all three chairs must be ready too.
    """
    occupants = [chair.occupant.account_id for chair in table.chairs if chair.occupant is not None]
    return (
        not hand_runs(table)
        and hand_was_dealt(table)
        and len(occupants) == CHAIRS_PER_TABLE
        and connected_accounts.issuperset(occupants)
        and (not (result_pending(table) or series_over(table)) or all(chair.ready for chair in table.chairs))
    )


def drawn_hand(table: TableRecord, random_source: random.Random) -> NewHand:
    """The only place a hand is drawn: a table's first dealer by lot, every later one in turn, then the shuffle.

    Randomness enters only here, both from the one source.
    """
    dealer = draw_dealer(random_source) if table.dealer is None else next_dealer(table.dealer)
    return NewHand(dealer, deal(random_source))


def dealt_next(table: TableRecord, new_hand: NewHand) -> TableRecord:
    """The table with the next hand, which is its own change and so bumps the version itself."""
    return dealt(table, new_hand, version=table.version + 1)


def decide_sit(table: TableRecord, actor: Actor, seat: int, new_hand: NewHand | None) -> Decision:
    """The actor takes a free chair; a taken chair names its holder, and nobody holds two chairs.

    The sit that fills the last chair deals `new_hand` in the same version bump, unless a result is pending; then
    the sitter counts as ready instead. At a series end nothing deals and the sitter is not ready. A chair that a
    stand-up or a send-away opened in a running hand is taken like any other, except by an account that left another
    chair of this hand: the sitter holds the seat's cards, role and turn, and the hand moves again once no chair is
    open.
    """
    if seat_of(table, actor.account_id) is not None:
        return Decision(table, Refusal.ALREADY_SEATED)
    held = seat_held_in_hand(table, actor.account_id)
    if held is not None and held != seat:
        return Decision(table, Refusal.OWN_SEAT_ONLY)
    holder = table.chairs[seat - 1].occupant
    if holder is not None:
        return Decision(table, Refusal.SEAT_TAKEN, holder.display_name)
    seated = with_occupant(table, seat, Occupant(actor.account_id, actor.display_name, actor.kind, actor.owner_account))
    if new_hand is not None and sit_deals(table):
        seated = dealt(seated, new_hand, version=seated.version)
    return Decision(seated)


def decide_stand(table: TableRecord, actor: Actor) -> Decision:
    """The actor leaves their own chair, which keeps its number; while a hand runs the chair opens and the hand waits
    for a sitter.
    """
    return decide_free_chair(table, actor.account_id)


def hold_frees_chair(table: TableRecord) -> bool:
    """The away hold may free a chair only at a table on which no hand was ever dealt.

    At a dealt table a chair is kept in every phase until its holder stands up, an agent's chair is sent away or the
    table ends.
    """
    return not hand_was_dealt(table)


def decide_free_chair(table: TableRecord, account_id: str) -> Decision:
    """The account's chair is freed and keeps its number, only while the account still holds it.

    A person standing up asks this alone; the server's away hold asks `hold_frees_chair` first.
    """
    own = seat_of(table, account_id)
    if own is None:
        return Decision(table, Refusal.NOT_SEATED)
    return Decision(with_occupant(table, own.seat, None))


def lowest_free_seat(table: TableRecord) -> int | None:
    return next((chair.seat for chair in table.chairs if chair.occupant is None), None)


def seat_held_in_hand(table: TableRecord, account_id: str) -> int | None:
    """The chair of the running hand that the account left and may sit in again, none when it left no chair of it.

    A mark counts only while a hand runs, so a mark an end of the hand left behind bars nobody.
    """
    if not hand_runs(table):
        return None
    return next((mark.seat for mark in table.progress.seats_held if mark.account_id == account_id), None)


def free_seat_for(table: TableRecord, account_id: str) -> int | None:
    """The chair the account may sit in: the one it left in the running hand if that is free (none if it is taken),
    else the lowest free chair.
    """
    held = seat_held_in_hand(table, account_id)
    if held is None:
        return lowest_free_seat(table)
    return held if table.chairs[held - 1].occupant is None else None


def waiting_seat_of(table: TableRecord) -> int | None:
    """The seat the running hand waits for: its lowest free chair, none while every chair is taken or no hand runs.

    The hand cannot move while this is set; the lowest seat is named, and the number moves on when it is filled.
    """
    return lowest_free_seat(table) if hand_runs(table) else None


def acting_position(table: TableRecord, actor: Actor, version: int) -> Position | Refusal:
    """The actor's position in the running hand, or why a hand command stops: no hand, no chair, a stale version, an
    open chair, which stops every hand command for everyone.
    """
    if table.dealer is None or not hand_runs(table):
        return Refusal.NO_HAND
    chair = seat_of(table, actor.account_id)
    if chair is None:
        return Refusal.NOT_SEATED
    if version != table.version:
        return Refusal.STALE_VERSION
    if waiting_seat_of(table) is not None:
        return Refusal.SEAT_OPEN
    return positions_from(table.dealer)[chair.seat]


def card_text(card: Card) -> str:
    """A card as a receipt's payload names it."""
    return f"{card.suit.name}-{card.rank.name}"


def sit_payload(command: SitDown) -> str:
    return f"{command.table_id}:{command.seat}"


def stand_payload(command: StandUp) -> str:
    return command.table_id


def command_receipt(actor: Actor, command_id: str, command: str, payload: str, decision: Decision) -> Receipt:
    return Receipt(actor.account_id, command_id, command, payload, decision.table.id, decision.refusal, decision.holder)


def replayed_decision(replay: Replay, command: str, payload: str) -> Decision:
    """The outcome a command already had; any other request under its key is refused."""
    first = _replayed(replay, command, payload)
    # Only a create receipt outlives a table's end, and `_replayed` refused every other command.
    assert isinstance(first.table, TableRecord)  # noqa: S101 - narrows the type for a table the end rules out
    return Decision(first.table, first.refusal, first.holder)
