import type { Cue } from "./cues.ts";
import type { Card, GameSheet, Hand, LastTrick, Playing, SeatedCard, Table } from "../routes/(start)/tables.ts";

// The card that ends a hand is not on the table that follows it, which has no hand and only the result; the game sheet
// of the result's game names every trick, so the page draws the last one from it before the result appears.

/** The ordinal of the result a page that watched the play receives when the last card ended the hand, else null. A hand that ended by a give-up or a throw-down has no last trick. */
export function closedHandOrdinal(previous: Table, next: Table): number | null {
    const { result } = next;
    if (previous.hand?.playing == null || next.hand !== null || result === null) return null;
    return result.kind === "declared" && result.ending !== "played-out" ? null : result.ordinal;
}

/** The table as the page shows it while the last trick rests and sweeps, and the cues of that trick. */
export interface Closing {
    readonly held: Table;
    readonly cues: readonly Cue[];
}

/** The closing of the hand that took `next` from `previous`, or null when the sheet has no last trick to draw. */
export function closeHand(previous: Table, next: Table, sheet: GameSheet | null): Closing | null {
    const tricks = sheet?.cards?.tricks ?? [];
    const last = tricks.at(-1);
    const hand = previous.hand as Hand;
    const playing = hand.playing as Playing;
    if (last?.taker_seat == null || last.cards.length === 0) return null;
    const trick: LastTrick = {
        cards: last.cards.map(({ card }) => card),
        leader_seat: (last.cards[0] as SeatedCard).seat,
        taker_seat: last.taker_seat,
    };
    return {
        held: {
            ...previous,
            version: next.version,
            chairs: previous.chairs.map((chair) => ({
                ...chair,
                hand: chair.hand === null ? null : { ...chair.hand, card_count: 0 },
            })),
            hand: {
                ...hand,
                own_cards: [],
                playing: {
                    ...playing,
                    turn_seat: null,
                    current_trick: [],
                    last_trick: trick,
                    taken: playing.taken.map(({ seat }) => ({
                        seat,
                        tricks: tricks.filter((each) => each.taker_seat === seat).length,
                    })),
                    legal_cards: [],
                },
            },
        },
        cues: [...laidBetween(playing.current_trick, last.cards).map(cardPlayed), { kind: "trick-taken", trick }],
    };
}

// The cards of the trick that the page has not yet seen laid, when the page saw the start of the trick as it was played.
function laidBetween(onTheFelt: readonly SeatedCard[], trick: readonly SeatedCard[]): SeatedCard[] {
    const seen = trick.slice(0, onTheFelt.length);
    const seenAsLaid =
        seen.length === onTheFelt.length &&
        seen.every((each, index) => sameCard(each.card, (onTheFelt[index] as SeatedCard).card));
    return seenAsLaid ? trick.slice(onTheFelt.length) : [...trick];
}

function sameCard(first: Card, second: Card): boolean {
    return first.suit === second.suit && first.rank === second.rank;
}

function cardPlayed({ seat, card }: SeatedCard): Cue {
    return { kind: "card-played", seat, card };
}
