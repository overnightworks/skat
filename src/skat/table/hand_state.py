from typing import TYPE_CHECKING, Final

from skat.engine.bidding import Auction, Declared, PassedIn, auction_after
from skat.engine.bock import in_ramsch_round
from skat.engine.declaration import Announcement, Declare, Declaring, declaring_after
from skat.engine.games import GameKind
from skat.engine.kontra import Doubling, bidders_of, doubling_after
from skat.engine.ramsch import ramsch_after, start_ramsch
from skat.engine.schieberamsch import Pushing, RamschOn, pushing_after
from skat.engine.tricks import Playing, playing_after, start_play

if TYPE_CHECKING:
    from skat.engine.deal import Deal
    from skat.engine.ramsch import RamschPlaying
    from skat.table.records import GiveUpAsked, TableRecord


def is_ramsch_round(table: TableRecord) -> bool:
    """The running hand is a Ramsch-round game, dealt as a Ramsch with no auction: no Bock game is pending and the
    table's rounds left Ramsch-round games, the running one included.
    """
    bock = table.options.bock
    return table.hand is not None and bock is not None and in_ramsch_round(table.bock, bock.overlap)


def auction_of(table: TableRecord) -> Auction:
    """The auction of a table, replayed through the engine from its stored steps; a Ramsch round has none and reads as
    passed in from the deal.
    """
    if is_ramsch_round(table):
        return Auction.passed_in_from_the_deal()
    return auction_after(table.progress.auction)


# What a seat that declares a Grand Hand in a Ramsch's stage has declared: the table names the game for him.
_GRAND_HAND_INSTEAD: Final = Declare(GameKind.GRAND, hand=True, ouvert=False, announcement=Announcement.NONE)


def _declared_in_the_stage(table: TableRecord) -> tuple[Declared, Deal] | None:
    """The seat that declared a Grand Hand instead of a Ramsch and the cards as the stage left them; None otherwise."""
    stage = pushing_of(table)
    if stage is None or not isinstance(stage.result, Declared):
        return None
    return stage.result, stage.deal


def declared_in_the_stage_of(table: TableRecord) -> Declared | None:
    """The Grand Hand a seat declared instead of a Ramsch, at the bid the table names for it; None otherwise."""
    in_the_stage = _declared_in_the_stage(table)
    return None if in_the_stage is None else in_the_stage[0]


def declaring_of(table: TableRecord) -> Declaring | None:
    """The declarer's stored steps replayed through the engine; None while no seat is declarer, which is the auction's
    winner or, in a Ramsch's stage, the seat that declared a Grand Hand instead.
    """
    result = auction_of(table).result
    if table.hand is None:
        return None
    if isinstance(result, Declared):
        return declaring_after(Declaring.start(result, table.hand), table.progress.declaring)
    in_the_stage = _declared_in_the_stage(table)
    if in_the_stage is None:
        return None
    declared, deal = in_the_stage
    return declaring_after(Declaring.start(declared, deal), (_GRAND_HAND_INSTEAD, *table.progress.declaring))


def _play_start(table: TableRecord) -> Playing | None:
    declared = declaring_of(table)
    if table.hand is None or declared is None or declared.declaration is None:
        return None
    in_the_stage = _declared_in_the_stage(table)
    return start_play(declared, table.hand if in_the_stage is None else in_the_stage[1])


def playing_of(table: TableRecord) -> Playing | None:
    """The cards played so far replayed through the engine; None until the game is declared."""
    start = _play_start(table)
    return None if start is None else playing_after(start, table.progress.plays)


def pushing_of(table: TableRecord) -> Pushing | None:
    """The stage of takes and pushes a Ramsch with pushing plays before its first card, its stored steps replayed
    through the engine; None at a table without pushing, before the third pass and at a game the auction declared.
    Its result is the Ramsch on, or the seat that declared a Grand Hand instead.
    """
    ramsch = table.options.ramsch
    options = None if ramsch is None else ramsch.push_options
    if table.hand is None or options is None or not isinstance(auction_of(table).result, PassedIn):
        return None
    return pushing_after(Pushing.start(table.hand), table.progress.pushing, options)


def game_of(table: TableRecord) -> Playing | RamschPlaying | None:
    """The game that runs: the declared game's cards played so far, else the Ramsch a table that plays one starts
    when all three pass, or once its stage ended, replayed from its stored cards; None while no game is played.
    """
    declared = playing_of(table)
    if declared is not None:
        return declared
    if table.hand is None or table.options.ramsch is None or not isinstance(auction_of(table).result, PassedIn):
        return None
    stage = pushing_of(table)
    if stage is None:
        return ramsch_after(start_ramsch(table.hand), table.progress.plays)
    if not isinstance(stage.result, RamschOn):
        return None
    return ramsch_after(start_ramsch(stage.deal), table.progress.plays)


def game_waits_for_the_declarers_answer(state: Playing | RamschPlaying | None, asked: GiveUpAsked | None) -> bool:
    """True when an opponent's give-up stands: the game is over by ISkO 4.4.3 unless the declarer demands play on, so
    no card, throw-down, Kontra word or give-up is taken until he answers. A Ramsch and a game not played have none.
    """
    return isinstance(state, Playing) and asked is not None and asked.asker is not state.declared.declarer


def doubling_of(table: TableRecord) -> Doubling | None:
    """The words of the running hand replayed through the engine, each against the cards it followed; None while no
    game is played or the table plays without Kontra.
    """
    start, options = _play_start(table), table.options.kontra
    if start is None or options is None:
        return None
    bidders = bidders_of(table.progress.auction)
    return doubling_after(start, table.progress.plays, table.progress.words, options, bidders)
