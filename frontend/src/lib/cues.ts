import {
    type Card,
    type Chair,
    type ChairHand,
    type LastTrick,
    type Playing,
    type SeatedCard,
    type Table,
} from "../routes/(start)/tables.ts";

export type Cue =
    | { kind: "card-played"; seat: number; card: Card }
    | { kind: "auction-ended" }
    // The seats of the opponents who both said no to the declarer's give-up.
    | { kind: "give-up-refused"; seats: number[] };

// The one owner of what just happened between two versions of a table. A table that is not newer than the one
// before it yields nothing, and so does a change the two versions do not fully explain.
export function cuesBetween(previous: Table | undefined, next: Table): Cue[] {
    if (previous === undefined || next.version <= previous.version) return [];
    const cues: Cue[] = [];
    if (auctionJustEnded(previous, next)) cues.push({ kind: "auction-ended" });
    for (const { seat, card } of cardsLaidBetween(previous, next)) cues.push({ kind: "card-played", seat, card });
    const refusers = giveUpRefusedBetween(previous, next);
    if (refusers !== null) cues.push({ kind: "give-up-refused", seats: refusers });
    return cues;
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

// The cards this update laid on the felt, in the order they were laid; none unless every change is explained.
function cardsLaidBetween(previous: Table, next: Table): SeatedCard[] {
    const before = previous.hand?.playing;
    const after = next.hand?.playing;
    if (!before || !after) return [];
    const laid = trickStepBetween(before, after, next.chairs);
    return laid !== null && handCountsExplain(previous.chairs, next.chairs, laid) ? laid : [];
}

// Either the trick on the felt grew, or it completed: then its last card and the cards on the new trick are laid.
function trickStepBetween(before: Playing, after: Playing, chairs: Chair[]): SeatedCard[] | null {
    if (sameJson(before.last_trick, after.last_trick))
        return cardsAddedToTrick(before.current_trick, after.current_trick);
    const completed = after.last_trick;
    if (completed === null || before.current_trick.length === 0) return null;
    const completing = completingCard(before.current_trick, chairs, completed);
    return completing === null ? null : [completing, ...after.current_trick];
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
