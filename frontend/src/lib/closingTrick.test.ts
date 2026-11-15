import { describe, expect, it } from "vitest";
import { closeHand } from "#lib/closingTrick.ts";
import { closedHandOrdinal, cuesBetween } from "#lib/cues.ts";
import { FOREHAND, MIDDLEHAND, REARHAND, table } from "#lib/cues.fixtures.ts";
import { LOST_GAME, ramschResult, table as tableWithResult } from "#lib/result.fixtures.ts";
import type { Card, GameSheet, Table } from "../routes/(start)/tables.ts";

const KREUZ_KING: Card = { suit: "kreuz", rank: "king" };
const HERZ_NINE: Card = { suit: "herz", rank: "nine" };
const KREUZ_ACE: Card = { suit: "kreuz", rank: "ace" };
const LAST_CARD_ON_THE_FELT = [
    { seat: FOREHAND, card: KREUZ_KING },
    { seat: MIDDLEHAND, card: HERZ_NINE },
];
const IN_THE_LAST_TRICK = [...LAST_CARD_ON_THE_FELT, { seat: REARHAND, card: KREUZ_ACE }];
const NINE_TRICKS_TAKEN = [3, 3, 3];

function sheetOfTheLastTrick(taker: number | null, cards = IN_THE_LAST_TRICK): GameSheet {
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
                ...NINE_TRICKS_TAKEN.flatMap((count, index) =>
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

const beforeTheLastCard = table(8, [0, 0, 1], { current: LAST_CARD_ON_THE_FELT });
const afterTheLastCard: Table = { ...tableWithResult(FOREHAND, { ordinal: 3 }), version: 9 };

describe("the hand that the last card ends", () => {
    it.each([
        { name: "a declared game", next: afterTheLastCard },
        { name: "a Ramsch", next: { ...afterTheLastCard, result: ramschResult([0, 0, 0], [0, 0, 0], {}) } },
    ])("is the ordinal of the result of $name that a page which watched its play receives", ({ next }) => {
        expect(closedHandOrdinal(beforeTheLastCard, next)).toBe(next.result?.ordinal);
    });

    it.each([
        {
            name: "a give-up, which has no last trick",
            next: { ...afterTheLastCard, ...tableWithResult(FOREHAND, { ...LOST_GAME, ending: "given-up" }) },
        },
        { name: "a table whose hand still runs", next: { ...beforeTheLastCard, version: 9 } },
        { name: "a table with no result", next: { ...afterTheLastCard, result: null } },
    ])("is none for $name", ({ next }) => {
        expect(closedHandOrdinal(beforeTheLastCard, next)).toBeNull();
    });

    it("is none for a page that watched no play", () => {
        expect(closedHandOrdinal({ ...afterTheLastCard, version: 8 }, afterTheLastCard)).toBeNull();
    });
});

describe("the last trick of a hand that the game sheet names", () => {
    it("shows the felt as the trick that finished, taken by the sheet's taker, and every pile counted", () => {
        const held = closeHand(beforeTheLastCard, afterTheLastCard, sheetOfTheLastTrick(MIDDLEHAND));

        expect(held?.version).toBe(afterTheLastCard.version);
        expect(held?.chairs.map((chair) => chair.hand?.card_count)).toEqual([0, 0, 0]);
        expect(held?.hand?.own_cards).toEqual([]);
        expect(held?.hand?.playing).toMatchObject({
            current_trick: [],
            last_trick: { cards: [KREUZ_KING, HERZ_NINE, KREUZ_ACE], leader_seat: FOREHAND, taker_seat: MIDDLEHAND },
            taken: [
                { seat: 1, tricks: 3 },
                { seat: 2, tricks: 4 },
                { seat: 3, tricks: 3 },
            ],
        });
    });

    it("tells the cards laid and then the trick taken, so the card lands before the trick rests", () => {
        const held = closeHand(beforeTheLastCard, afterTheLastCard, sheetOfTheLastTrick(MIDDLEHAND));

        expect(held && cuesBetween(beforeTheLastCard, held)).toEqual([
            { kind: "card-played", seat: REARHAND, card: KREUZ_ACE },
            {
                kind: "trick-taken",
                trick: { cards: [KREUZ_KING, HERZ_NINE, KREUZ_ACE], leader_seat: FOREHAND, taker_seat: MIDDLEHAND },
            },
        ]);
    });

    it("lays every card of the trick the page did not see when it missed an update", () => {
        const behind = table(7, [1, 1, 1], { current: [] });
        const held = closeHand(behind, afterTheLastCard, sheetOfTheLastTrick(MIDDLEHAND));

        const cues = held === null ? [] : cuesBetween(behind, held);
        expect(cues.filter((cue) => cue.kind === "card-played")).toHaveLength(3);
        expect(cues.at(-1)?.kind).toBe("trick-taken");
    });

    it.each([
        { name: "a sheet that kept no cards", sheet: { ...sheetOfTheLastTrick(1), cards: null } },
        { name: "a last trick with no taker", sheet: sheetOfTheLastTrick(null) },
        { name: "a sheet that cannot be read", sheet: null },
    ])("is none for $name", ({ sheet }) => {
        expect(closeHand(beforeTheLastCard, afterTheLastCard, sheet)).toBeNull();
    });
});
