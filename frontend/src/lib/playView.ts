import { firstCardWait } from "#lib/kontra.ts";
import { POSITION_TOKENS } from "#lib/wire.ts";
import type { LastTrickMode, StageState } from "#lib/stage.ts";
import { words } from "#lib/words.ts";
import {
    drawingOrder,
    includesCard,
    type Card,
    type Chair,
    type ChairHand,
    type Declaring,
    type LastTrick,
    type Playing,
    type SeatedCard,
    type Table,
    type Taken,
} from "../routes/(start)/tables.ts";

// The felt's places in the order the chairs are drawn: the two far chairs, then the near one.
const TRICK_SLOTS = ["left", "right", "near"] as const;

export type TrickSlot = (typeof TRICK_SLOTS)[number];
export type LaidCard = { card: Card; seat: number; slot: TrickSlot; name: string; initial: string };
export type SideNames = { declarer: string; opponents: string };
// What the hand needs while its holder is on turn to play: a first tap lifts a legal card, a second plays it, and a
// card moved upward past the threshold plays at once; a play settles as accepted or refused.
export type PlayingHand = {
    legal: readonly Card[];
    lifted: Card | null;
    disabled: boolean;
    tap: (card: Card) => void;
    play: (card: Card) => Promise<boolean>;
};

// The turn goes forehand, middlehand, rearhand and round again; while a hand runs every chair holds a position.
function seatsInTurnFrom(chairs: readonly Chair[], leaderSeat: number): number[] {
    const turnOf = new Map(
        chairs.map((chair) => [chair.seat, POSITION_TOKENS.indexOf((chair.hand as ChairHand).position)]),
    );
    const lead = turnOf.get(leaderSeat) as number;
    const turnsAfterLead = (seat: number): number =>
        ((turnOf.get(seat) as number) - lead + POSITION_TOKENS.length) % POSITION_TOKENS.length;
    return chairs.map((chair) => chair.seat).sort((first, second) => turnsAfterLead(first) - turnsAfterLead(second));
}

function lastTrickBySeat(chairs: readonly Chair[], last: LastTrick): SeatedCard[] {
    const seats = seatsInTurnFrom(chairs, last.leader_seat);
    return last.cards.map((card, index) => ({ seat: seats[index] as number, card }));
}

// The finished trick that lies on the felt: the one the stage holds or sweeps, or with „liegen lassen“ the last one
// until the next card is led, which a reload shows too.
function finishedTrickOnTheFelt(playing: Playing, stage: StageState, mode: LastTrickMode): LastTrick | null {
    if (stage.trick !== null) return stage.trick;
    return mode === "stay" && playing.current_trick.length === 0 ? playing.last_trick : null;
}

function laidCards(chairs: Chair[], trick: readonly SeatedCard[]): LaidCard[] {
    const order = drawingOrder(chairs);
    return trick.map(({ seat, card }) => {
        const place = order.findIndex((chair) => chair.seat === seat);
        const chair = order[place] as Chair;
        const accountName = chair.occupant_name ?? "";
        return {
            card,
            seat,
            slot: TRICK_SLOTS[place] as TrickSlot,
            name: chair.is_mine ? words["play.sideYou"] : accountName,
            initial: accountName.slice(0, 1),
        };
    });
}

// The trick in progress, or the finished one while the stage moves it or the player lets it lie; each card at its
// player's side.
export function trickOnTheFelt(chairs: Chair[], playing: Playing, stage: StageState, mode: LastTrickMode): LaidCard[] {
    const finished = finishedTrickOnTheFelt(playing, stage, mode);
    return laidCards(chairs, finished === null ? playing.current_trick : lastTrickBySeat(chairs, finished));
}

// The trick the brass rim stands for, which is the one a tap on its pile shows: the last one that lies in a pile.
// While a finished trick still lies on the felt it is not yet in a pile, so the rim stays on the one before it, and
// with „liegen lassen“ on none.
export function trickInPile(playing: Playing, stage: StageState, mode: LastTrickMode): LastTrick | null {
    const finished = finishedTrickOnTheFelt(playing, stage, mode);
    if (finished === null) return playing.last_trick;
    if (stage.phase === "gliding") return finished;
    return mode === "sweep" ? (stage.before?.last_trick ?? null) : null;
}

/** The tricks a seat has taken that lie in its pile, whether the pile holds the last trick, and whether its top card is landing. */
export type Pile = { tricks: number; rimmed: boolean; landing: boolean };

// A pile counts the tricks taken but the one that still lies on the felt; the one that glides onto it lands as its top card.
export function pileOf(seat: number, playing: Playing, stage: StageState, mode: LastTrickMode): Pile {
    const finished = finishedTrickOnTheFelt(playing, stage, mode);
    const gliding = stage.phase === "gliding";
    const { tricks: taken } = playing.taken.find((each) => each.seat === seat) as Taken;
    return {
        tricks: taken - (finished?.taker_seat === seat && !gliding ? 1 : 0),
        rimmed: trickInPile(playing, stage, mode)?.taker_seat === seat,
        landing: gliding && finished?.taker_seat === seat,
    };
}

/** The cards of a trick in the order they were played, each with its player's name. */
export function playedCards(chairs: Chair[], trick: LastTrick): LaidCard[] {
    return laidCards(chairs, lastTrickBySeat(chairs, trick));
}

// The viewer's dashed slot on the felt, where their card will lie: it is their turn and the near place holds no card.
export function ownCardSlotOpen(
    chairs: readonly Chair[],
    laid: readonly LaidCard[],
    turnSeat: number | null | undefined,
): boolean {
    const own = chairs.find((chair) => chair.is_mine);
    return own !== undefined && own.seat === turnSeat && !laid.some(({ slot }) => slot === "near");
}

// The declarer reads „Du“ against the opponents, an opponent counts their own side as „Wir“, and a watcher sees the declarer by name.
export function sideNames(chairs: readonly Chair[], declarerSeat: number): SideNames {
    const declarer = (chairs.find((chair) => chair.seat === declarerSeat) as Chair).occupant_name ?? "";
    const mine = chairs.find((chair) => chair.is_mine);
    if (mine === undefined) return { declarer, opponents: words["play.sideThem"] };
    if (mine.seat === declarerSeat) return { declarer: words["result.sideYou"], opponents: words["result.sideThem"] };
    return { declarer, opponents: words["play.sideUs"] };
}

export type GameInPlay = { declaration: NonNullable<Declaring["declaration"]>; declarerSeat: number; playing: Playing };

// The declared game being played; a Ramsch has no declaration, so none is in play there.
export function gameInPlay(table: Table): GameInPlay | null {
    const hand = table.hand;
    if (!hand?.playing || !hand.declaring) return null;
    const declaring = hand.declaring;
    return {
        declaration: declaring.declaration as NonNullable<Declaring["declaration"]>,
        declarerSeat: declaring.declarer_seat,
        playing: hand.playing,
    };
}

// The bid line of a game that no bid or play word declared: the Grand Hand a seat declared instead of a Ramsch, at the
// bid the table names for it. An auction-won game always carries a bid or play word.
export function bidLineOfGameDeclaredInTheStage(table: Table): string | null {
    const auction = table.hand?.auction;
    if (!auction?.declared || !auction.words.every((word) => word.action === "pass")) return null;
    return words["table.bidValue"]({ value: String(auction.declared.value) });
}

// The cards the viewer may play now, or null when it is not the viewer's turn to play or the first card waits for a word.
export function cardsToPlay(table: Table): readonly Card[] | null {
    const playing = table.hand?.playing;
    const mineSeat = table.chairs.find((chair) => chair.is_mine)?.seat;
    if (mineSeat === undefined || playing?.turn_seat !== mineSeat || firstCardWait(table) !== null) return null;
    return playing.legal_cards;
}

export type CardLook = "plain" | "legal" | "lifted" | "dimmed";

// Off turn the hand looks as dealt; on turn the legal cards are lifted and one tapped card lifted further.
export function cardLook(playing: PlayingHand | undefined, card: Card): CardLook {
    if (playing === undefined) return "plain";
    if (playing.lifted !== null && includesCard([playing.lifted], card)) return "lifted";
    return includesCard(playing.legal, card) ? "legal" : "dimmed";
}

export type DragVerdict = "tap" | "play" | "return";

// A press that moves less than this many pixels is a tap, whatever the pointer's tremor.
const TAP_SLOP_PIXELS = 8;
// A card moved upward by this share of its height is played; a shorter move puts it back.
const PLAY_RISE_SHARE = 0.5;

// What a pressed card comes to when the pointer lets go after moving by dx and dy (dy grows downward).
export function dragVerdict(move: { dx: number; dy: number }, cardHeight: number): DragVerdict {
    if (Math.hypot(move.dx, move.dy) < TAP_SLOP_PIXELS) return "tap";
    return -move.dy >= cardHeight * PLAY_RISE_SHARE ? "play" : "return";
}
