import type { GameSheet, Hand, LastTrick, Playing, SeatedCard, Table } from "../routes/(start)/tables.ts";

// The card that ends a hand is not on the table that follows it, which has no hand and only the result; the game sheet
// of the result's game names every trick, so the page draws the last one from it before the result appears.

/** The table as the page shows it while the last trick rests and sweeps, or null when the sheet has no last trick to draw. */
export function closeHand(previous: Table, next: Table, sheet: GameSheet | null): Table | null {
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
    };
}
