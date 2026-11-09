import { describe, expect, it } from "vitest";
import { awayOnTurn, chairMarks, type ChairMarks } from "#lib/auctionMarks.ts";
import type { Auction, Chair } from "../routes/(start)/tables.ts";

const FOREHAND = 1;
const MIDDLEHAND = 2;
const REARHAND = 3;
const WATCHER = undefined;
const NO_MARKS: ChairMarks = { bubble: null, passed: false, turn: false, waits: false };

function auction(changes: Partial<Auction>): Auction {
    return {
        turn_seat: MIDDLEHAND,
        facing_seat: FOREHAND,
        awaiting: "bid",
        standing: null,
        values: [],
        words: [],
        declared: null,
        ...changes,
    };
}

const middlehandBid18 = auction({
    turn_seat: FOREHAND,
    facing_seat: MIDDLEHAND,
    awaiting: "answer",
    standing: 18,
    words: [{ seat: MIDDLEHAND, action: "bid", value: 18 }],
});

describe("the marks on a chair during the auction", () => {
    it.each([
        {
            name: "a bid is the loud bubble with its value",
            state: middlehandBid18,
            seat: MIDDLEHAND,
            marks: { bubble: { kind: "bid", value: 18 } },
        },
        {
            name: "a hold is the quiet bubble with the value it held",
            state: auction({ standing: 18, words: [{ seat: FOREHAND, action: "hold", value: 18 }] }),
            seat: FOREHAND,
            marks: { bubble: { kind: "hold", value: 18 } },
        },
        {
            name: "a pass greys the chair and drops its bubble",
            state: auction({ turn_seat: REARHAND, words: [{ seat: MIDDLEHAND, action: "pass", value: null }] }),
            seat: MIDDLEHAND,
            marks: { passed: true },
        },
        {
            name: "a chair that has not spoken carries nothing",
            state: auction({}),
            seat: REARHAND,
            marks: {},
        },
    ] satisfies { name: string; state: Auction; seat: number; marks: Partial<ChairMarks> }[])(
        "$name for every viewer but the one on turn",
        ({ state, seat, marks }) => {
            for (const viewer of [FOREHAND, MIDDLEHAND, REARHAND, WATCHER].filter((one) => one !== state.turn_seat)) {
                expect(chairMarks(state, seat, viewer)).toEqual({ ...NO_MARKS, ...marks });
            }
        },
    );

    it("puts the turn mark on exactly the chair on turn for every viewer", () => {
        for (const viewer of [FOREHAND, MIDDLEHAND, REARHAND, WATCHER]) {
            const onTurn = [FOREHAND, MIDDLEHAND, REARHAND].filter(
                (seat) => chairMarks(middlehandBid18, seat, viewer).turn,
            );
            expect(onTurn).toEqual([FOREHAND]);
        }
    });

    it("shows only the last word of a chair", () => {
        const state = auction({
            standing: 23,
            words: [
                { seat: FOREHAND, action: "hold", value: 20 },
                { seat: MIDDLEHAND, action: "bid", value: 23 },
            ],
            turn_seat: FOREHAND,
            facing_seat: MIDDLEHAND,
            awaiting: "answer",
        });

        expect(chairMarks(state, MIDDLEHAND, WATCHER).bubble).toEqual({ kind: "bid", value: 23 });
        expect(chairMarks(state, FOREHAND, WATCHER).bubble).toEqual({ kind: "hold", value: 20 });
    });

    it.each([
        { name: "the forehand answering a bid sees the bidder wait", state: middlehandBid18, viewer: FOREHAND },
        {
            name: "the rearhand bidding against the forehand sees the forehand wait",
            state: auction({
                turn_seat: REARHAND,
                facing_seat: FOREHAND,
                words: [{ seat: MIDDLEHAND, action: "pass", value: null }],
            }),
            viewer: REARHAND,
        },
    ] satisfies { name: string; state: Auction; viewer: number }[])("$name", ({ state, viewer }) => {
        const waiting = [FOREHAND, MIDDLEHAND, REARHAND].filter((seat) => chairMarks(state, seat, viewer).waits);

        expect(waiting).toEqual([state.facing_seat]);
    });

    it("shows the waits mark to nobody but the player on turn", () => {
        const state = middlehandBid18;

        for (const viewer of [MIDDLEHAND, REARHAND, WATCHER]) {
            for (const seat of [FOREHAND, MIDDLEHAND, REARHAND]) {
                expect(chairMarks(state, seat, viewer).waits).toBe(false);
            }
        }
    });

    it("shows no waits mark when the forehand takes 18 alone after two passes", () => {
        const state = auction({
            turn_seat: FOREHAND,
            facing_seat: null,
            awaiting: "play",
            words: [
                { seat: MIDDLEHAND, action: "pass", value: null },
                { seat: REARHAND, action: "pass", value: null },
            ],
        });

        for (const viewer of [FOREHAND, MIDDLEHAND, REARHAND, WATCHER]) {
            const marks = [FOREHAND, MIDDLEHAND, REARHAND].map((seat) => chairMarks(state, seat, viewer));
            expect(marks.filter(({ waits }) => waits)).toEqual([]);
            expect(marks.filter(({ passed }) => passed)).toHaveLength(2);
        }
    });

    it("draws nothing once the auction is over", () => {
        const state = auction({
            turn_seat: null,
            facing_seat: null,
            awaiting: null,
            standing: 18,
            words: [
                { seat: MIDDLEHAND, action: "bid", value: 18 },
                { seat: FOREHAND, action: "pass", value: null },
                { seat: REARHAND, action: "pass", value: null },
            ],
            declared: { seat: MIDDLEHAND, value: 18 },
        });

        for (const seat of [FOREHAND, MIDDLEHAND, REARHAND]) {
            expect(chairMarks(state, seat, MIDDLEHAND)).toEqual(NO_MARKS);
        }
    });

    it("draws nothing before a deal", () => {
        expect(chairMarks(undefined, FOREHAND, FOREHAND)).toEqual(NO_MARKS);
    });

    it("draws no bubble for the forehand's word to play at 18", () => {
        const state = auction({ words: [{ seat: FOREHAND, action: "play", value: 18 }] });

        expect(chairMarks(state, FOREHAND, WATCHER)).toEqual(NO_MARKS);
    });
});

function chair(seat: number, changes: Partial<Chair> = {}): Chair {
    return { seat, occupant_name: `player-${String(seat)}`, is_mine: false, is_away: false, ready: false, hand: null, ...changes };
}

describe("whom the plaque waits for", () => {
    it("names the player on turn while they are away", () => {
        const chairs = [chair(FOREHAND), chair(MIDDLEHAND, { occupant_name: "Anna", is_away: true }), chair(REARHAND)];

        expect(awayOnTurn(auction({}), chairs)).toBe("Anna");
    });

    it.each([
        { name: "the player on turn is there", chairs: [chair(MIDDLEHAND), chair(FOREHAND, { is_away: true })] },
        { name: "nobody is on turn", chairs: [chair(MIDDLEHAND, { is_away: true })], changes: { turn_seat: null } },
    ] satisfies { name: string; chairs: Chair[]; changes?: Partial<Auction> }[])(
        "waits for nobody when $name",
        ({ chairs, changes }) => {
            expect(awayOnTurn(auction(changes ?? {}), chairs)).toBeNull();
        },
    );
});
