import type { Bubble } from "./auctionMarks.ts";
import { stampOf, type SaidWord, type Stamp } from "./kontra.ts";
import {
    type AuctionAction,
    type Card,
    type Chair,
    type ChairHand,
    type LastTrick,
    type Playing,
    type SeatedCard,
    type Table,
} from "../routes/(start)/tables.ts";

// What a chair said in the auction that the table shows: a bid or a hold with its value, or a pass.
export type BidWord = { action: Exclude<AuctionAction, "play">; value: number | null };

export type Cue =
    | { kind: "card-played"; seat: number; card: Card }
    | { kind: "auction-ended" }
    // The trick this update's completing card finished, which goes to its taker.
    | { kind: "trick-taken"; trick: LastTrick }
    // The seats of the opponents who both said no to the declarer's give-up.
    | { kind: "give-up-refused"; seats: number[] }
    | { kind: "bid-said"; seat: number; word: BidWord }
    | { kind: "word-said"; said: SaidWord };

// The one owner of what just happened between two versions of a table. A table that is not newer than the one
// before it yields nothing, and so does a change the two versions do not fully explain.
export function cuesBetween(previous: Table | undefined, next: Table): Cue[] {
    if (previous === undefined || next.version <= previous.version) return [];
    const cues: Cue[] = [];
    if (auctionJustEnded(previous, next)) cues.push({ kind: "auction-ended" });
    const { laid, completed } = cardsLaidBetween(previous, next);
    for (const [index, { seat, card }] of laid.entries()) {
        cues.push({ kind: "card-played", seat, card });
        if (index === 0 && completed !== null) cues.push({ kind: "trick-taken", trick: completed });
    }
    const refusers = giveUpRefusedBetween(previous, next);
    if (refusers !== null) cues.push({ kind: "give-up-refused", seats: refusers });
    const bid = bidSaidBetween(previous, next);
    if (bid !== null) cues.push({ kind: "bid-said", ...bid });
    const said = wordSaidBetween(previous, next);
    if (said !== null) cues.push({ kind: "word-said", said });
    return cues;
}

// The stamp of the word an update brought, or null. A page that has no table before it, as after a reload or a dropped
// connection, stamps nothing: the plaque already tells the word.
export function stampBetween(previous: Table | undefined, next: Table): Stamp | null {
    const said = wordSaidBetween(previous, next);
    return said === null ? null : stampOf(next, said);
}

// Whether the bubble a chair shows is the bid this page saw said, which is the one that springs up.
export function springsUp(said: { seat: number; word: BidWord } | null, seat: number, bubble: Bubble | null): boolean {
    return said?.seat === seat && said.word.action === bubble?.kind && said.word.value === bubble.value;
}

// The word the update from `previous` to `next` brought, the last when it brought several.
function wordSaidBetween(previous: Table | undefined, next: Table): SaidWord | null {
    if (previous === undefined || next.version <= previous.version) return null;
    const before = previous.hand?.playing?.kontra?.said ?? [];
    const after = next.hand?.playing?.kontra?.said ?? [];
    return after.length > before.length ? (after.at(-1) as SaidWord) : null;
}

// The auction keeps each chair's latest word in seat order, so a chair whose word is new or changed said it in this
// update; the last of them when several did. A play shows nothing at the table, so it is no cue.
function bidSaidBetween(previous: Table, next: Table): { seat: number; word: BidWord } | null {
    const before = previous.hand?.auction.words ?? [];
    const latest = (next.hand?.auction.words ?? []).findLast(
        (word) =>
            !sameJson(
                before.find((each) => each.seat === word.seat),
                word,
            ),
    );
    return latest === undefined || latest.action === "play"
        ? null
        : { seat: latest.seat, word: { action: latest.action, value: latest.value } };
}

// The second no clears the declarer's request that already carried the first no, while the game goes on with the same
// cards on the felt and the same people in the chairs; a card, a yes and a chair that changed hands clear it otherwise.
function giveUpRefusedBetween(previous: Table, next: Table): number[] | null {
    const before = previous.hand?.playing;
    const after = next.hand?.playing;
    const asked = before?.give_up;
    if (!before || typeof asked?.declined_seat !== "number" || after?.give_up !== null) return null;
    const unchanged =
        sameJson(before.current_trick, after.current_trick) &&
        sameJson(before.last_trick, after.last_trick) &&
        sameJson(
            previous.chairs.map((chair) => chair.occupant_name),
            next.chairs.map((chair) => chair.occupant_name),
        );
    return unchanged ? next.chairs.map((chair) => chair.seat).filter((seat) => seat !== asked.asking_seat) : null;
}

// The auction ended in the update that brings the declaring to a hand that had none; a page that opens later
// or reconnects sees the choosing as it is.
function auctionJustEnded(previous: Table, next: Table): boolean {
    return !!previous.hand && !previous.hand.declaring && next.hand?.declaring?.stage === "choosing";
}

type TrickStep = { laid: SeatedCard[]; completed: LastTrick | null };
const NO_STEP: TrickStep = { laid: [], completed: null };

// The cards this update laid on the felt, in the order they were laid, and the trick they completed if any; nothing
// unless every change is explained.
function cardsLaidBetween(previous: Table, next: Table): TrickStep {
    const before = previous.hand?.playing;
    const after = next.hand?.playing;
    if (!before || !after) return NO_STEP;
    const step = trickStepBetween(before, after, next.chairs);
    return step !== null && handCountsExplain(previous.chairs, next.chairs, step.laid) ? step : NO_STEP;
}

// Either the trick on the felt grew, or it completed: then its last card and the cards on the new trick are laid.
function trickStepBetween(before: Playing, after: Playing, chairs: Chair[]): TrickStep | null {
    if (sameJson(before.last_trick, after.last_trick)) {
        const added = cardsAddedToTrick(before.current_trick, after.current_trick);
        return added === null ? null : { laid: added, completed: null };
    }
    const completed = after.last_trick;
    if (completed === null || before.current_trick.length === 0) return null;
    const completing = completingCard(before.current_trick, chairs, completed);
    return completing === null ? null : { laid: [completing, ...after.current_trick], completed };
}

function cardsAddedToTrick(before: SeatedCard[], after: SeatedCard[]): SeatedCard[] | null {
    return sameJson(after.slice(0, before.length), before) ? after.slice(before.length) : null;
}

// The trick's cards carry no seats, so the card that completed it belongs to the one chair that has not played in it.
function completingCard(trick: SeatedCard[], chairs: Chair[], completed: LastTrick): SeatedCard | null {
    const playedSeats = new Set(trick.map((seated) => seated.seat));
    const waiting = chairs.map((chair) => chair.seat).filter((seat) => !playedSeats.has(seat));
    const trickCards = trick.map((seated) => seated.card);
    const explained =
        waiting.length === 1 &&
        completed.cards.length === trick.length + 1 &&
        sameJson(completed.cards.slice(0, trick.length), trickCards);
    return explained ? { seat: waiting[0] as number, card: completed.cards[trick.length] as Card } : null;
}

// Each card laid takes one card from its player's hand, and no other hand changes.
function handCountsExplain(before: Chair[], after: Chair[], laid: SeatedCard[]): boolean {
    return after.every(
        (chair) =>
            cardCountOf(before, chair.seat) - laid.filter((seated) => seated.seat === chair.seat).length ===
            cardCountOf(after, chair.seat),
    );
}

// Every chair holds a hand while a hand is played, so its count is there to read.
function cardCountOf(chairs: Chair[], seat: number): number {
    return ((chairs.find((chair) => chair.seat === seat) as Chair).hand as ChairHand).card_count;
}

// The server sends one trick and one hand the same way every time, so their JSON is the comparison of their content.
function sameJson(first: unknown, second: unknown): boolean {
    return JSON.stringify(first) === JSON.stringify(second);
}
