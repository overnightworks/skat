import { FOREHAND, MIDDLEHAND, REARHAND, table } from "#lib/cues.fixtures.ts";
import { table as tableWithResult } from "#lib/result.fixtures.ts";
import type { Card, GameSheet, Hand, Table } from "../routes/(start)/tables.ts";

// The last card of a hand on the felt, the table that follows it and the game sheet that names the last trick.
export const KREUZ_KING: Card = { suit: "kreuz", rank: "king" };
export const HERZ_NINE: Card = { suit: "herz", rank: "nine" };
export const KREUZ_ACE: Card = { suit: "kreuz", rank: "ace" };
const LAST_CARD_ON_THE_FELT = [
    { seat: FOREHAND, card: KREUZ_KING },
    { seat: MIDDLEHAND, card: HERZ_NINE },
];
const IN_THE_LAST_TRICK = [...LAST_CARD_ON_THE_FELT, { seat: REARHAND, card: KREUZ_ACE }];
const NINE_TRICKS_TAKEN = [3, 3, 3];

// `takenBefore` counts the tricks each seat took before the last; a game decided early has fewer than nine.
export function sheetOfTheLastTrick(
    taker: number | null,
    cards = IN_THE_LAST_TRICK,
    takenBefore = NINE_TRICKS_TAKEN,
): GameSheet {
    const number = 3;
    return {
        number,
        seat_names: [null, null, null],
        count: { kind: "ramsch", seat_points: [0, 0, 0], durchmarsch_seat: null },
        cards: {
            hands: [],
            skat: [],
            laid_skat: [],
            put_away: [],
            skat_takers: [],
            tricks: [
                ...takenBefore.flatMap((count, index) =>
                    Array.from({ length: count }, () => ({
                        number,
                        cards: [],
                        taker_seat: index + 1,
                        points: 0,
                    })),
                ),
                { number, cards, taker_seat: taker, points: 14 },
            ],
        },
    };
}

export const beforeTheLastCard = table(8, [0, 0, 1], { current: LAST_CARD_ON_THE_FELT });
export const afterTheLastCard: Table = { ...tableWithResult(FOREHAND, { ordinal: 3 }), version: 9 };

// A Null that the declarer in rearhand loses in the third trick: two cards lie on the felt, he holds eight and must
// take the trick with the ace, so the game ends with seven cards left in every hand.
const OWN_CARDS_IN_TRICK_THREE: Card[] = [
    KREUZ_ACE,
    { suit: "pik", rank: "seven" },
    { suit: "pik", rank: "eight" },
    { suit: "pik", rank: "nine" },
    { suit: "herz", rank: "seven" },
    { suit: "herz", rank: "eight" },
    { suit: "karo", rank: "seven" },
    { suit: "karo", rank: "eight" },
];
const TWO_TRICKS_TAKEN = [1, 1, 0];
const beforeTrickThree = table(6, [7, 7, 8], { current: LAST_CARD_ON_THE_FELT });
export const beforeTheDecidingCard: Table = {
    ...beforeTrickThree,
    chairs: beforeTrickThree.chairs.map((chair) => ({ ...chair, is_mine: chair.seat === REARHAND })),
    hand: { ...(beforeTrickThree.hand as Hand), own_cards: OWN_CARDS_IN_TRICK_THREE },
};
export const sheetOfTrickThree = sheetOfTheLastTrick(REARHAND, IN_THE_LAST_TRICK, TWO_TRICKS_TAKEN);
