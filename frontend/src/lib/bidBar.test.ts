import { describe, expect, it } from "vitest";
import {
    bidBar,
    chipTap,
    limitAt,
    livePick,
    passAheadTap,
    passedLimit,
    stepWith,
    takenBack,
    type BidBar,
    type BidStep,
} from "#lib/bidBar.ts";
import { EVERY_HAND_DEALT, FOREHAND, MIDDLEHAND, REARHAND, table as dealtTable } from "#lib/cues.fixtures.ts";
import { auctionWith } from "#lib/table.fixtures.ts";
import { VALID_BIDS } from "#lib/wire.ts";
import type { Auction, AuctionPlan, Hand, Table } from "../routes/(start)/tables.ts";

const ME = MIDDLEHAND;
// What the viewer's cards reach: nothing above 36.
const REACHED: Auction["hand_values"] = [
    { game: "karo", value: 27 },
    { game: "herz", value: 30 },
    { game: "pik", value: 33 },
    { game: "kreuz", value: 36 },
];
const ASK_36: AuctionPlan = { kind: "limit", value: 36, mode: "ask" };
const FIXED_36: AuctionPlan = { kind: "limit", value: 36, mode: "fixed" };
const PASS_AHEAD: AuctionPlan = { kind: "pass", value: null, mode: null };
const MY_PASS: Auction["steps"] = [{ seat: ME, action: "pass", value: null }];

// A table in its auction as the viewer in the middlehand's chair is told it; `viewer` seats somebody else or nobody.
function tableWith(auction: Partial<Auction>, hand: Partial<Hand> = {}, viewer: number | null = ME): Table {
    const dealt = dealtTable(1, EVERY_HAND_DEALT, { declaring: null });
    return {
        ...dealt,
        chairs: dealt.chairs.map((chair) => ({ ...chair, is_mine: chair.seat === viewer })),
        hand: {
            ...(dealt.hand as Hand),
            auction: auctionWith({ turn_seat: FOREHAND, awaiting: "answer", hand_values: REACHED, ...auction }),
            ...hand,
        },
    };
}

function barOf(auction: Partial<Auction>): BidBar {
    return bidBar(tableWith(auction)) as BidBar;
}

describe("who gets the bid bar", () => {
    it("is a seated player who has not passed, off his turn too", () => {
        expect(bidBar(tableWith({}))).toMatchObject({ onTurn: false, step: null });
    });

    it.each([
        { name: "a table between two hands", table: { ...tableWith({}), hand: null } },
        { name: "an auction that is over", table: tableWith({ awaiting: null }) },
        { name: "a viewer without a chair", table: tableWith({}, {}, null) },
        { name: "a hand that waits for a sitter", table: tableWith({}, { waiting_seat: REARHAND }) },
        { name: "a player who passed", table: tableWith({ steps: MY_PASS }) },
    ])("is not $name", ({ table }) => {
        expect(bidBar(table)).toBeNull();
    });

    it("is a player while another chair has passed", () => {
        expect(bidBar(tableWith({ steps: [{ seat: REARHAND, action: "pass", value: null }] }))).not.toBeNull();
    });
});

describe("the one blue key", () => {
    it.each([
        {
            name: "says the next value as the bidder",
            auction: { awaiting: "bid", values: [20, 22, 23] },
            step: { action: "bid", value: 20, says: 20 },
        },
        { name: "says „Ja“ as the responder", auction: { awaiting: "answer", standing: 20 }, step: { action: "hold" } },
        {
            name: "says the lowest bid as the forehand after two passes",
            auction: { awaiting: "play" },
            step: { action: "play", says: VALID_BIDS[0] },
        },
        { name: "is missing at the ladder's top", auction: { awaiting: "bid", values: [] }, step: null },
    ] satisfies { name: string; auction: Partial<Auction>; step: BidStep | null }[])("$name", ({ auction, step }) => {
        expect(barOf({ turn_seat: ME, ...auction }).step).toEqual(step);
    });

    it("is missing off his turn", () => {
        expect(barOf({ turn_seat: FOREHAND, awaiting: "bid", values: [20] }).step).toBeNull();
    });
});

describe("the chips", () => {
    it("are the values his cards reach, each with its game", () => {
        expect(barOf({}).chips).toEqual(REACHED.map((each) => ({ ...each, lit: false, gone: false })));
    });

    it("light his limit and fade every value below the standing bid", () => {
        const chips = barOf({ standing: 33, plan: ASK_36 }).chips;

        expect(chips.map(({ value, lit, gone }) => [value, lit, gone])).toEqual([
            [27, false, true],
            [30, false, true],
            [33, false, false],
            [36, true, false],
        ]);
    });

    it.each([
        {
            name: "sets a value as his first limit, which asks",
            plan: null,
            value: 30,
            sent: { value: 30, mode: "ask" },
        },
        { name: "moves a limit and keeps its mode", plan: FIXED_36, value: 30, sent: { value: 30, mode: "fixed" } },
    ] as const)("a tap $name", ({ plan, value, sent }) => {
        expect(chipTap(barOf({ plan }), value)).toEqual({ kind: "limit", ...sent });
    });

    it("a tap on the lit chip takes the limit back", () => {
        expect(chipTap(barOf({ plan: ASK_36 }), 36)).toBeNull();
    });
});

describe("his plan on the bar", () => {
    it("is his limit with the game whose value it is and its mode", () => {
        expect(barOf({ plan: FIXED_36 })).toMatchObject({
            limit: { value: 36, game: "kreuz", mode: "fixed" },
            passAhead: false,
            asked: null,
        });
    });

    it("is a limit without a game at a value his cards do not reach", () => {
        expect(barOf({ plan: { ...ASK_36, value: 40 } }).limit).toEqual({ value: 40, game: null, mode: "ask" });
    });

    it("is the pass said ahead, which names no limit", () => {
        expect(barOf({ plan: PASS_AHEAD })).toMatchObject({ limit: null, passAhead: true });
    });

    it("is neither without a plan", () => {
        expect(barOf({})).toMatchObject({ limit: null, passAhead: false, asked: null });
    });

    it.each([
        { name: "asks him on his turn above his limit", auction: { turn_seat: ME, awaiting: "bid" }, asked: true },
        { name: "does not ask him off his turn", auction: { turn_seat: FOREHAND, awaiting: "bid" }, asked: false },
        {
            name: "does not ask the forehand after two passes, where a limit says nothing",
            auction: { turn_seat: ME, awaiting: "play" },
            asked: false,
        },
    ] as const)("$name", ({ auction, asked }) => {
        const bar = barOf({ plan: ASK_36, standing: 40, ...auction });

        expect(bar.asked).toEqual(asked ? bar.limit : null);
    });

    it.each([
        { name: "says „Weg“ ahead", plan: null, sent: { kind: "pass" } },
        { name: "says „Weg“ ahead in place of a limit", plan: ASK_36, sent: { kind: "pass" } },
        { name: "takes „Weg“ back", plan: PASS_AHEAD, sent: null },
    ])("a tap on „Weg“ off his turn $name", ({ plan, sent }) => {
        expect(passAheadTap(barOf({ plan }))).toEqual(sent);
    });
});

describe("a plan a tap takes back", () => {
    it.each([
        { name: "is his limit after the cross or the lit chip", plan: ASK_36, choice: null, back: "limit" },
        { name: "is his „Weg“ ahead after its second tap", plan: PASS_AHEAD, choice: null, back: "pass" },
        { name: "is none where a tap sets a plan", plan: ASK_36, choice: { kind: "pass" }, back: null },
        { name: "is none without a plan", plan: null, choice: null, back: null },
    ] as const)("$name", ({ plan, choice, back }) => {
        expect(takenBack(tableWith({ plan }), choice)).toBe(back);
    });
});

describe("his fixed limit after the table said „Weg“ for him", () => {
    it("stays in his sight with its game, in place of the bar", () => {
        const passed = tableWith({ plan: FIXED_36, steps: MY_PASS, standing: 40 });

        expect([passedLimit(passed), bidBar(passed)]).toEqual([{ value: 36, game: "kreuz", mode: "fixed" }, null]);
    });

    it.each([
        { name: "before his pass", table: tableWith({ plan: FIXED_36 }) },
        { name: "after his own pass above an ask limit", table: tableWith({ plan: ASK_36, steps: MY_PASS }) },
        { name: "after his „Weg“ said ahead", table: tableWith({ plan: PASS_AHEAD, steps: MY_PASS }) },
        { name: "after a pass without a plan", table: tableWith({ steps: MY_PASS }) },
        { name: "once the auction is over", table: tableWith({ plan: FIXED_36, steps: MY_PASS, awaiting: null }) },
    ])("is not shown $name", ({ table }) => {
        expect(passedLimit(table)).toBeNull();
    });
});

describe("the whole scale", () => {
    const scale = barOf({ standing: 30, plan: ASK_36 }).scale;
    const at = (value: number) => scale.find((each) => each.value === value);

    it("holds every valid value in order", () => {
        expect(scale.map((each) => each.value)).toEqual([...VALID_BIDS]);
    });

    it.each([
        { name: "a value below the standing bid as gone", value: 27, marks: { gone: true, game: "karo" } },
        { name: "the standing bid", value: 30, marks: { standing: true, gone: false, game: "herz" } },
        { name: "a value no game of his reaches without a game", value: 35, marks: { game: null, overHand: false } },
        { name: "his limit", value: 36, marks: { mine: true, overHand: false, holdHint: false } },
        { name: "the first value above his cards with the hint", value: 40, marks: { overHand: true, holdHint: true } },
        { name: "a higher value above his cards", value: 44, marks: { overHand: true, holdHint: false, mine: false } },
    ])("marks $name", ({ value, marks }) => {
        expect(at(value)).toMatchObject(marks);
    });

    it("marks no value as gone before the first bid", () => {
        expect(barOf({ standing: null }).scale.some((each) => each.gone)).toBe(false);
    });
});

describe("a value picked on the scale", () => {
    const bidder = barOf({ turn_seat: ME, awaiting: "bid", standing: 22, values: [23, 24, 27, 30, 33, 35, 36, 40] });

    it("stays picked while the auction has not passed it", () => {
        expect([livePick(bidder, 40), livePick(bidder, 22)]).toEqual([40, 22]);
    });

    it.each([
        { name: "is none before a pick", picked: null },
        { name: "is none once the standing bid lies above it", picked: 20 },
    ])("$name", ({ picked }) => {
        expect(livePick(bidder, picked)).toBeNull();
    });

    it("makes the bidder's key say the picked value at once", () => {
        expect(stepWith(bidder, 40)).toEqual({ action: "bid", value: 40, says: 40 });
    });

    it.each([
        { name: "the bidder's key without a pick", bar: bidder, pick: null },
        { name: "the bidder's key at the standing bid, which no bid can name", bar: bidder, pick: 22 },
        { name: "the responder's answer", bar: barOf({ turn_seat: ME, awaiting: "answer", standing: 22 }), pick: 40 },
        { name: "the forehand's first bid", bar: barOf({ turn_seat: ME, awaiting: "play" }), pick: 40 },
        { name: "no key off his turn", bar: barOf({}), pick: 40 },
    ])("leaves $name as it is", ({ bar, pick }) => {
        expect(stepWith(bar, pick)).toEqual(bar.step);
    });

    it("becomes his limit in the mode he chose before", () => {
        expect(limitAt(barOf({ plan: FIXED_36 }), 40)).toEqual({ kind: "limit", value: 40, mode: "fixed" });
    });
});
