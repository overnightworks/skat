from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from skat.engine.cards import DECK
from skat.engine.deal import seats_from
from skat.engine.giving_up import give_up, opponent_gives_up, throw_down
from skat.engine.ramsch import RamschPlayedOut, RamschPlaying, play_ramsch_card
from skat.engine.tricks import CardPlayed, Playing, PlayRefusal, play_card
from skat.table.bock import bock_after
from skat.table.game_list import GameEnding, list_entry_of, ramsch_entry_of
from skat.table.hand_state import doubling_of, game_of, game_waits_for_the_declarers_answer, playing_of
from skat.table.records import Decision, GiveUpAsked, HandProgress, Refusal, TableRecord
from skat.table.rules import acting_position, card_text

if TYPE_CHECKING:
    from skat.engine.bock import BockRounds
    from skat.engine.cards import Card
    from skat.engine.deal import Position
    from skat.engine.tricks import PlayedOut, PlayOutcome, Sides
    from skat.table.game_list import GameEntry
    from skat.table.kontra import KontraView
    from skat.table.records import Actor


@dataclass(frozen=True)
class PlayCardCommand:
    """A card played; the actor's seat and position come from the session, never from the client."""

    command_id: str
    table_id: str
    version: int
    card: Card


@dataclass(frozen=True)
class GiveUpCommand:
    """The caller gives up the game for his side; the actor's seat and position come from the session, never from the
    client.
    """

    command_id: str
    table_id: str
    version: int


@dataclass(frozen=True)
class ThrowDownCommand:
    """A side throws its cards down; the actor's seat and position come from the session, never from the client."""

    command_id: str
    table_id: str
    version: int


@dataclass(frozen=True)
class AgreeToGiveUpCommand:
    """The other side says yes to a give-up; the actor's seat and position come from the session."""

    command_id: str
    table_id: str
    version: int


@dataclass(frozen=True)
class DeclineGiveUpCommand:
    """The other side says no to a give-up; the actor's seat and position come from the session."""

    command_id: str
    table_id: str
    version: int


@dataclass(frozen=True)
class SeatedCard:
    """A card of the trick in progress and the seat that played it."""

    seat: int
    card: Card


@dataclass(frozen=True)
class LastTrick:
    """The last completed trick: its cards in playing order from the seat that led it, and who took it."""

    cards: tuple[Card, ...]
    leader_seat: int
    taker_seat: int


@dataclass(frozen=True)
class GiveUpView:
    """A give-up waiting for the other side's answer, by seat: who asked, and the opponent who said no to the
    declarer's.
    """

    asking_seat: int
    declined_seat: int | None


@dataclass(frozen=True)
class PlayingView:
    """The game in play as one viewer may see it; the turn is the seat that plays next."""

    turn_seat: int
    current_trick: tuple[SeatedCard, ...]
    last_trick: LastTrick | None
    legal_cards: tuple[Card, ...]
    running_points: Sides | None
    give_up: GiveUpView | None
    kontra: KontraView | None


def card_payload(command: PlayCardCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    return f"{command.table_id}:{command.version}:{card_text(command.card)}"


def decide_card(table: TableRecord, actor: Actor, command: PlayCardCommand) -> Decision:
    """One card: no hand, no chair, a stale version, the wrong phase, an opponent's give-up waiting for the declarer,
    then the engine's reason.

    The card that ends the game, a Ramsch's too, ends the hand; the Bock rounds are asked once its entry exists.
    """
    position = acting_position(table, actor, command.version)
    if isinstance(position, Refusal):
        return Decision(table, position)
    state = game_of(table)
    if state is None:
        return Decision(table, Refusal.WRONG_PHASE)
    if game_waits_for_the_declarers_answer(state, table.progress.give_up):
        return Decision(table, Refusal.REQUEST_PENDING)
    outcome = _card_played(state, position, command.card)
    if outcome.refusal is not None:
        return Decision(table, outcome.refusal)
    plays = (*table.progress.plays, CardPlayed(position, command.card))
    played = outcome.state.result
    if played is None:
        return Decision(
            replace(table, version=table.version + 1, progress=replace(table.progress, plays=plays, give_up=None))
        )
    if isinstance(played, RamschPlayedOut):
        entry = ramsch_entry_of(played, table)
        return Decision(_ended(table, entry, bock_after(table, played, entry)))
    return Decision(_ended_declared(table, played, GameEnding.PLAYED_OUT, None))


def _card_played(
    state: Playing | RamschPlaying, position: Position, card: Card
) -> PlayOutcome[Playing] | PlayOutcome[RamschPlaying]:
    """The card in the game that runs: a Ramsch's cards and a declared game's are played alike by the engine."""
    if isinstance(state, RamschPlaying):
        return play_ramsch_card(state, position, card)
    return play_card(state, position, card)


def give_up_payload(command: GiveUpCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    return f"{command.table_id}:{command.version}"


def decide_give_up(table: TableRecord, actor: Actor, command: GiveUpCommand) -> Decision:
    """The caller gives up for his side: no hand, no chair, a stale version, the wrong phase, another request waiting.

    The declarer's give-up is decided last by the engine, which says whether the game ends at once. Where it asks for
    consent, the request is stored and the opponents are asked; a request already standing changes nothing. An
    opponent's give-up is stored at any moment and the declarer is asked; the other opponent's changes nothing.
    """
    position = acting_position(table, actor, command.version)
    if isinstance(position, Refusal):
        return Decision(table, position)
    state = playing_of(table)
    if state is None:
        return Decision(table, Refusal.WRONG_PHASE)
    asked = table.progress.give_up
    waits = game_waits_for_the_declarers_answer(state, asked)
    if position is state.declared.declarer:
        return Decision(table, Refusal.REQUEST_PENDING) if waits else _declarer_gives_up(table, state, asked)
    if asked is None:
        return _with_request(table, GiveUpAsked(position))
    return Decision(table) if waits else Decision(table, Refusal.REQUEST_PENDING)


def _declarer_gives_up(table: TableRecord, state: Playing, asked: GiveUpAsked | None) -> Decision:
    outcome = give_up(state)
    if outcome.refusal is not PlayRefusal.NEEDS_CONSENT:
        return _end_of(table, outcome, GameEnding.GIVEN_UP, state.declared.declarer)
    if asked is not None:
        return Decision(table)
    return _with_request(table, GiveUpAsked(state.declared.declarer))


def _with_request(table: TableRecord, asked: GiveUpAsked | None) -> Decision:
    return Decision(replace(table, version=table.version + 1, progress=replace(table.progress, give_up=asked)))


def agree_to_give_up_payload(command: AgreeToGiveUpCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    return f"{command.table_id}:{command.version}"


def decline_give_up_payload(command: DeclineGiveUpCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    return f"{command.table_id}:{command.version}"


def _answerer(
    table: TableRecord, actor: Actor, version: int
) -> tuple[Playing, GiveUpAsked, Position] | Refusal | PlayRefusal:
    """Who may answer a request: no hand, no chair, a stale version, the wrong phase, nothing asked, then the other
    side than the one that asked: an opponent for the declarer's request, the declarer for an opponent's.
    """
    position = acting_position(table, actor, version)
    if isinstance(position, Refusal):
        return position
    state = playing_of(table)
    if state is None:
        return Refusal.WRONG_PHASE
    asked = table.progress.give_up
    if asked is None:
        return Refusal.NO_REQUEST
    if game_waits_for_the_declarers_answer(state, asked):
        return (state, asked, position) if position is state.declared.declarer else Refusal.NOT_DECLARER
    if position is state.declared.declarer:
        return PlayRefusal.NOT_AN_OPPONENT
    return state, asked, position


def decide_agree_to_give_up(table: TableRecord, actor: Actor, command: AgreeToGiveUpCommand) -> Decision:
    """The other side says yes: the game ends as the engine settles the give-up, by the seat that asked."""
    answering = _answerer(table, actor, command.version)
    if not isinstance(answering, tuple):
        return Decision(table, answering)
    state, asked, _ = answering
    if game_waits_for_the_declarers_answer(state, asked):
        return _end_of(table, opponent_gives_up(state), GameEnding.GIVEN_UP, asked.asker)
    return _end_of(table, give_up(state, consented=True), GameEnding.GIVEN_UP, asked.asker)


def decide_decline_give_up(table: TableRecord, actor: Actor, command: DeclineGiveUpCommand) -> Decision:
    """The other side says no. The declarer's no to an opponent's give-up demands play on: the request ends. An
    opponent's no to the declarer's keeps the request for the other opponent, whose no ends it; a second no of the same
    opponent changes nothing.
    """
    answering = _answerer(table, actor, command.version)
    if not isinstance(answering, tuple):
        return Decision(table, answering)
    state, asked, position = answering
    if game_waits_for_the_declarers_answer(state, asked):
        return _with_request(table, None)
    if asked.declined_by is position:
        return Decision(table)
    if asked.declined_by is not None:
        return _with_request(table, None)
    return _with_request(table, GiveUpAsked(asked.asker, position))


def throw_down_payload(command: ThrowDownCommand) -> str:
    """The receipt's payload: a retry repeats its original version, so another version is another request."""
    return f"{command.table_id}:{command.version}"


def decide_throw_down(table: TableRecord, actor: Actor, command: ThrowDownCommand) -> Decision:
    """A side throws its cards down: no hand, no chair, a stale version, the wrong phase, an opponent's give-up
    waiting for the declarer, then the engine.
    """
    position = acting_position(table, actor, command.version)
    if isinstance(position, Refusal):
        return Decision(table, position)
    state = playing_of(table)
    if state is None:
        return Decision(table, Refusal.WRONG_PHASE)
    if game_waits_for_the_declarers_answer(state, table.progress.give_up):
        return Decision(table, Refusal.REQUEST_PENDING)
    return _end_of(table, throw_down(state, position), GameEnding.THROWN_DOWN, position)


def _end_of(table: TableRecord, outcome: PlayOutcome, ending: GameEnding, ended_by: Position) -> Decision:
    """The hand ended with the result of a give-up or throw-down by `ended_by`."""
    played = outcome.state.result
    assert played is not None  # noqa: S101 - a replayed game is never over and its ending step always leaves a result
    return Decision(_ended_declared(table, played, ending, ended_by))


def _ended_declared(
    table: TableRecord, played: PlayedOut, ending: GameEnding, ended_by: Position | None
) -> TableRecord:
    """The card, give-up or throw-down that ends a declared game ends the hand; the Bock rounds are asked once its
    entry exists. The entry keeps how the game ended, which the engine's ending does not say.
    """
    entry = list_entry_of(played, table, doubling_of(table), ending, ended_by)
    return _ended(table, entry, bock_after(table, played, entry))


def _ended(table: TableRecord, entry: GameEntry, bock: BockRounds) -> TableRecord:
    """The hand ends: its cards and steps go, and its entry joins the list."""
    return TableRecord(
        id=table.id,
        version=table.version + 1,
        chairs=table.chairs,
        dealer=table.dealer,
        hand=None,
        progress=HandProgress(),
        game_list=(*table.game_list, entry),
        series=table.series,
        options=table.options,
        bock=bock,
    )


def _legal_cards(state: Playing | RamschPlaying, viewer_positions: frozenset[Position]) -> tuple[Card, ...]:
    """The cards the engine accepts from the player on turn, in deck order, for that player alone."""
    turn = state.turn
    if turn not in viewer_positions:
        return ()
    held = state.hands[turn]
    return tuple(card for card in DECK if card in held and _card_played(state, turn, card).refusal is None)


def playing_view_of(
    state: Playing | RamschPlaying | None,
    dealer: int,
    viewer_positions: frozenset[Position],
    *,
    show_running_points: bool,
    asked: GiveUpAsked | None,
    kontra: KontraView | None,
) -> PlayingView | None:
    """The game in play for one viewer; None until a game is played.

    Everyone sees the turn, the trick in progress and the last completed trick.
    Only the seated player on turn gets the cards they may play, and nobody while the hand waits for a sitter or the
    game for the declarer's answer to an opponent's give-up, which the caller says by passing no viewer position.
    A table that shows the running points gives everyone the card points of the completed tricks, which leave out
    the skat; a Null game and a Ramsch have none. The words said are the caller's `kontra` view.
    A give-up waiting for an opponent's yes is the same for every viewer.
    """
    if state is None:
        return None
    seats = seats_from(dealer)
    last = state.tricks[-1] if state.tricks else None
    return PlayingView(
        turn_seat=seats[state.turn],
        current_trick=tuple(SeatedCard(seats[play.position], play.card) for play in state.current_plays),
        last_trick=None if last is None else LastTrick(last.cards, seats[last.leader], seats[last.taker]),
        legal_cards=_legal_cards(state, viewer_positions),
        running_points=state.tally.points
        if show_running_points and isinstance(state, Playing) and state.counts_card_points
        else None,
        give_up=None if asked is None else _give_up_view_of(asked, seats),
        kontra=kontra,
    )


def _give_up_view_of(asked: GiveUpAsked, seats: dict[Position, int]) -> GiveUpView:
    return GiveUpView(seats[asked.asker], None if asked.declined_by is None else seats[asked.declined_by])
