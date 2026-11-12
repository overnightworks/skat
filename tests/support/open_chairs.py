"""Scenes of a running hand, one per phase, and one of every hand command, for the tests of an open chair.

Seat 2 deals: seat 1 is middlehand (account-middlehand), seat 2 rearhand and seat 3 forehand.
"""

from dataclasses import replace

from skat.engine.bidding import Bid, Pass
from skat.engine.cards import DECK
from skat.engine.deal import Position
from skat.engine.declaration import PutBack, TakeSkat
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer, Word
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring, play_ramsch_card
from skat.engine.schieberamsch import Push, PushingRule, Take
from skat.engine.tricks import CardPlayed
from skat.table.auction import AuctionAction, AuctionCommand, decide_step
from skat.table.declaring import DeclaringCommand, decide_declaring_step
from skat.table.hand_state import game_of
from skat.table.kontra import KontraCommand, decide_kontra
from skat.table.playing import (
    AgreeToGiveUpCommand,
    DeclineGiveUpCommand,
    GiveUpCommand,
    PlayCardCommand,
    ThrowDownCommand,
    decide_agree_to_give_up,
    decide_card,
    decide_decline_give_up,
    decide_give_up,
    decide_throw_down,
)
from skat.table.pushing import PushingCommand, PushingKind, decide_pushing_step
from skat.table.records import (
    Actor,
    HandProgress,
    OccupantKind,
    RamschOccasion,
    RamschSetting,
    TableOptions,
    TableRecord,
)
from skat.table.send_away import decide_send_away
from tests.support.played_game import a_whole_game, declared_herz_hand, table_in, with_agents

MIDDLEHAND, REARHAND, FOREHAND = Position.MIDDLEHAND, Position.REARHAND, Position.FOREHAND
MIDDLEHAND_SEAT, REARHAND_SEAT, FOREHAND_SEAT = 1, 2, 3
RAMSCH = TableOptions(
    ramsch=RamschSetting(
        RamschOccasion.PASSED_IN,
        RamschOptions(RamschScoring.SKAT_TO_LOSER, JungfrauRule.OFF, DurchmarschRule.WINS_120_FLAT),
    )
)
PUSHING = TableOptions(
    ramsch=RamschSetting(
        RamschOccasion.PASSED_IN,
        RamschOptions(RamschScoring.SKAT_TO_LOSER, JungfrauRule.OFF, DurchmarschRule.WINS_120_FLAT),
        PushingRule.JACKS_STAY,
    )
)
KONTRA = TableOptions(kontra=KontraOptions(KontraSayer.ANY_OPPONENT, KontraReach.KONTRA_RE, KontraDeadline.OWN_CARD))
ALL_PASS = (Pass(MIDDLEHAND), Pass(REARHAND), Pass(FOREHAND))
OWN_PUT_BACK = PutBack((DECK[10], DECK[11]))


def account_of(position: Position) -> str:
    return f"account-{position.name.lower()}"


def actor_at(table: TableRecord, seat: int) -> Actor:
    """The seat's occupant as the actor behind a request."""
    occupant = table.chairs[seat - 1].occupant
    assert occupant is not None
    return Actor(occupant.account_id, occupant.display_name, occupant.kind)


def sent_away(table: TableRecord, seat: int) -> TableRecord:
    """The table once the agent in `seat` was sent away; the occupant of the seat is made an agent first."""
    agents = with_agents(table, seat)
    occupant = agents.chairs[seat - 1].occupant
    assert occupant is not None
    return decide_send_away(agents, occupant.account_id).table


def newcomer(kind: OccupantKind = OccupantKind.PERSON, name: str = "Dora") -> Actor:
    return Actor(f"account-{name.lower()}", name, kind)


def _after_declaring(*steps: object) -> TableRecord:
    won = (Bid(MIDDLEHAND, 18), Pass(FOREHAND), Pass(REARHAND))
    return table_in(HandProgress(auction=won, declaring=tuple(steps)))  # type: ignore[arg-type]


def in_the_auction() -> TableRecord:
    return table_in(HandProgress(auction=(Bid(MIDDLEHAND, 18),)))


def after_the_take() -> TableRecord:
    return _after_declaring(TakeSkat())


def after_the_put_back() -> TableRecord:
    return _after_declaring(TakeSkat(), OWN_PUT_BACK)


def before_the_first_card() -> TableRecord:
    return table_in(declared_herz_hand())


def in_a_trick() -> TableRecord:
    return _in_play(4)


def between_tricks() -> TableRecord:
    return _in_play(3)


def _in_play(plays: int) -> TableRecord:
    table = table_in(declared_herz_hand())
    return replace(table, progress=replace(table.progress, plays=a_whole_game(table)[:plays]))


def at_the_ramsch_start() -> TableRecord:
    return table_in(HandProgress(auction=ALL_PASS), RAMSCH)


def in_a_ramsch_trick() -> TableRecord:
    table = at_the_ramsch_start()
    state = game_of(table)
    plays: list[CardPlayed] = []
    while len(plays) < 4:
        position = state.turn
        card = next(
            each
            for each in DECK
            if each in state.hands[position] and play_ramsch_card(state, position, each).refusal is None
        )
        state = play_ramsch_card(state, position, card).state
        plays.append(CardPlayed(position, card))
    return replace(table, progress=replace(table.progress, plays=tuple(plays)))


def at_the_pushing_start() -> TableRecord:
    return table_in(HandProgress(auction=ALL_PASS), PUSHING)


def after_the_pushing_take() -> TableRecord:
    return table_in(HandProgress(auction=ALL_PASS, pushing=(Take(FOREHAND),)), PUSHING)


def after_the_push() -> TableRecord:
    return table_in(HandProgress(auction=ALL_PASS, pushing=(Push(FOREHAND),)), PUSHING)


PHASES = {
    "auction": in_the_auction,
    "after-the-take": after_the_take,
    "after-the-put-back": after_the_put_back,
    "before-the-first-card": before_the_first_card,
    "in-a-trick": in_a_trick,
    "between-tricks": between_tricks,
    "ramsch-start": at_the_ramsch_start,
    "in-a-ramsch-trick": in_a_ramsch_trick,
    "pushing-start": at_the_pushing_start,
    "pushing-after-the-take": after_the_pushing_take,
    "pushing-after-the-push": after_the_push,
}


def _hand_commands(table: TableRecord) -> dict[str, object]:
    ids = (table.id.value, table.version)
    return {
        "auction-step": lambda actor: decide_step(
            table, actor, AuctionCommand("command-1", *ids, AuctionAction.PASS, None)
        ),
        "declaring-step": lambda actor: decide_declaring_step(
            table, actor, DeclaringCommand("command-1", *ids, TakeSkat())
        ),
        **{
            f"pushing-{kind.value}": lambda actor, kind=kind: decide_pushing_step(
                table, actor, PushingCommand("command-1", *ids, kind, DECK[:2] if kind is PushingKind.PUT_BACK else ())
            )
            for kind in PushingKind
        },
        "kontra": lambda actor: decide_kontra(table, actor, KontraCommand("command-1", *ids, Word.KONTRA)),
        "card": lambda actor: decide_card(table, actor, PlayCardCommand("command-1", *ids, DECK[0])),
        "give-up": lambda actor: decide_give_up(table, actor, GiveUpCommand("command-1", *ids)),
        "agree-to-give-up": lambda actor: decide_agree_to_give_up(
            table, actor, AgreeToGiveUpCommand("command-1", *ids)
        ),
        "decline-give-up": lambda actor: decide_decline_give_up(table, actor, DeclineGiveUpCommand("command-1", *ids)),
        "throw-down": lambda actor: decide_throw_down(table, actor, ThrowDownCommand("command-1", *ids)),
    }


HAND_COMMANDS = tuple(_hand_commands(in_the_auction()))


def hand_command(name: str, table: TableRecord, actor: Actor):
    """The decision of the named hand command by `actor` at the table's current version."""
    return _hand_commands(table)[name](actor)
