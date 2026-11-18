import {
    includesCard,
    type Card,
    type GameSheet,
    type Hand,
    type LastTrick,
    type Playing,
    type SeatedCard,
    type Table,
} from "../routes/(start)/tables.ts";

// The card that ends a hand is not on the table that follows it, which has no hand and only the result; the game sheet
// of the result's game names every trick, so the page draws the last one from it before the result appears. A game
// decided before its tenth trick ends with cards in every hand, so each hand gives up only the cards the trick took
// from it.

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
    // The cards of the trick that were on the felt already left their hands with the tables before.
    const laid = last.cards.slice(playing.current_trick.length);
    const laidBy = (seat: number): Card[] => laid.filter((seated) => seated.seat === seat).map(({ card }) => card);
    const ownSeat = previous.chairs.find((chair) => chair.is_mine)?.seat;
    const ownLaid = ownSeat === undefined ? [] : laidBy(ownSeat);
    return {
        ...previous,
        version: next.version,
        chairs: previous.chairs.map((chair) => ({
            ...chair,
            hand:
                chair.hand === null
                    ? null
                    : { ...chair.hand, card_count: chair.hand.card_count - laidBy(chair.seat).length },
        })),
        hand: {
            ...hand,
            own_cards: hand.own_cards.filter((card) => !includesCard(ownLaid, card)),
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
