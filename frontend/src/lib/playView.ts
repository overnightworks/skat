import { POSITION_TOKENS } from "#lib/wire.ts";
import { words } from "#lib/words.ts";
import {
    drawingOrder,
    includesCard,
    type Card,
    type Chair,
    type ChairHand,
    type Declaring,
    type Game,
    type LastTrick,
    type Playing,
    type SeatedCard,
    type Table,
} from "../routes/(start)/tables.ts";

// The felt's places in the order the chairs are drawn: the two far chairs, then the near one.
const TRICK_SLOTS = ["left", "right", "near"] as const;

export type TrickSlot = (typeof TRICK_SLOTS)[number];
export type LaidCard = { card: Card; seat: number; slot: TrickSlot; name: string };
export type SideNames = { declarer: string; opponents: string };
// What the hand needs while its holder is on turn to play: a first tap lifts a legal card, a second plays it.
export type PlayingHand = { legal: readonly Card[]; lifted: Card | null; disabled: boolean; tap: (card: Card) => void };

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

// The trick in progress, or the last one until the next card is led, each card at its player's side.
export function trickOnTheFelt(chairs: Chair[], playing: Playing): LaidCard[] {
    const { current_trick: current, last_trick: last } = playing;
    const trick = current.length > 0 || last === null ? current : lastTrickBySeat(chairs, last);
    const order = drawingOrder(chairs);
    return trick.map(({ seat, card }) => {
        const place = order.findIndex((chair) => chair.seat === seat);
        return {
            card,
            seat,
            slot: TRICK_SLOTS[place] as TrickSlot,
            name: (order[place] as Chair).occupant_name ?? "",
        };
    });
}

// Each viewer counts their own side as „Wir“; a watcher sees the declarer against the opponents.
export function sideNames(chairs: readonly Chair[], declarerSeat: number): SideNames {
    const declarer = (chairs.find((chair) => chair.seat === declarerSeat) as Chair).occupant_name ?? "";
    const mine = chairs.find((chair) => chair.is_mine);
    if (mine === undefined) return { declarer, opponents: words.sideThem };
    if (mine.seat === declarerSeat) return { declarer: words.sideUs, opponents: words.sideThem };
    return { declarer, opponents: words.sideUs };
}

export type GameInPlay = { declaration: NonNullable<Declaring["declaration"]>; declarerSeat: number; playing: Playing };

// The game being played: a hand is played only once its game is declared, so the declaration is there.
export function gameInPlay(table: Table): GameInPlay | null {
    const hand = table.hand;
    if (!hand?.playing) return null;
    const declaring = hand.declaring as Declaring;
    return {
        declaration: declaring.declaration as NonNullable<Declaring["declaration"]>,
        declarerSeat: declaring.declarer_seat,
        playing: hand.playing,
    };
}

// The cards the viewer may play now, or null when it is not the viewer's turn to play.
export function cardsToPlay(table: Table): readonly Card[] | null {
    const playing = table.hand?.playing;
    const mineSeat = table.chairs.find((chair) => chair.is_mine)?.seat;
    if (mineSeat === undefined || playing?.turn_seat !== mineSeat) return null;
    return playing.legal_cards;
}

export type CardLook = "plain" | "legal" | "lifted" | "dimmed";

// Off turn the hand looks as dealt; on turn the legal cards are lifted and one tapped card lifted further.
export function cardLook(playing: PlayingHand | undefined, card: Card): CardLook {
    if (playing === undefined) return "plain";
    if (playing.lifted !== null && includesCard([playing.lifted], card)) return "lifted";
    return includesCard(playing.legal, card) ? "legal" : "dimmed";
}
