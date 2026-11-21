import { describe, expect, it } from "vitest";
import { bidRunBetween, type BidRun } from "#lib/bidRun.ts";
import { cuesBetween, type BidSaid } from "#lib/cues.ts";
import { EVERY_HAND_DEALT, FOREHAND, MIDDLEHAND, REARHAND, table } from "#lib/cues.fixtures.ts";
import { seedOf } from "#lib/takt/seed.ts";
import type { Auction, AuctionWord, Hand, Table } from "../routes/(start)/tables.ts";

const BID_EIGHTEEN: AuctionWord = { seat: MIDDLEHAND, action: "bid", value: 18 };
const HOLD_EIGHTEEN: AuctionWord = { seat: FOREHAND, action: "hold", value: 18 };
const BID_TWENTY: AuctionWord = { seat: MIDDLEHAND, action: "bid", value: 20 };
const PASS_OF_FOREHAND: AuctionWord = { seat: FOREHAND, action: "pass", value: null };
const PASS_OF_MIDDLEHAND: AuctionWord = { seat: MIDDLEHAND, action: "pass", value: null };
const PASS_OF_REARHAND: AuctionWord = { seat: REARHAND, action: "pass", value: null };
const PLAY: AuctionWord = { seat: FOREHAND, action: "play", value: 18 };
const RUN = [BID_EIGHTEEN, HOLD_EIGHTEEN, BID_TWENTY, PASS_OF_FOREHAND];
// Before the run middlehand is on turn to bid against forehand.
const WAITING_FOR_MIDDLEHAND = { turn_seat: MIDDLEHAND, facing_seat: FOREHAND, awaiting: "bid" } as const;

function auctionTable(version: number, said: AuctionWord[], changes: Partial<Auction> = {}): Table {
    const dealt = table(version, EVERY_HAND_DEALT, { declaring: null, spoken: said });
    const hand = dealt.hand as Hand;
    return { ...dealt, hand: { ...hand, auction: { ...hand.auction, ...changes } } };
}

const saidBetween = (previous: Table, next: Table): BidSaid[] =>
    cuesBetween(previous, next).filter((cue) => cue.kind === "bid-said");

function runBetween(previous: Table, next: Table): BidRun {
    const run = bidRunBetween(previous, next, saidBetween(previous, next));
    if (run === null) throw new Error("the update brought no run");
    return run;
}

const auctionsOf = (run: BidRun): Auction[] => run.tables.map((each) => (each.hand as Hand).auction);

describe("the run of the words one update brought", () => {
    const before = auctionTable(4, [], WAITING_FOR_MIDDLEHAND);
    const after = auctionTable(5, RUN, { turn_seat: REARHAND, facing_seat: MIDDLEHAND, standing: 20 });

    it("counts each word by its number in the auction, with what it says", () => {
        expect(runBetween(before, after).words).toEqual([
            { step: 0, action: "bid" },
            { step: 1, action: "hold" },
            { step: 2, action: "bid" },
            { step: 3, action: "pass" },
        ]);
    });

    it("counts on from the words the page has seen", () => {
        const seen = auctionTable(4, RUN.slice(0, 2), WAITING_FOR_MIDDLEHAND);

        expect(runBetween(seen, after).words).toEqual([
            { step: 2, action: "bid" },
            { step: 3, action: "pass" },
        ]);
    });

    it("carries the seed of its game, which every seat reads alike", () => {
        expect(runBetween(before, after).seed).toBe(seedOf(after));
    });

    it("has a table after each word but the last, whose table is the one the update brought", () => {
        const { tables } = runBetween(before, after);

        expect(auctionsOf({ tables } as BidRun).map((auction) => auction.steps)).toEqual([
            RUN.slice(0, 1),
            RUN.slice(0, 2),
            RUN.slice(0, 3),
        ]);
    });

    it("shows on each table each chair's latest word and the bid that stands then", () => {
        const [first, second, third] = auctionsOf(runBetween(before, after));

        expect(first?.words).toEqual([BID_EIGHTEEN]);
        expect(first?.standing).toBe(18);
        expect(second?.words).toEqual([BID_EIGHTEEN, HOLD_EIGHTEEN]);
        expect(second?.standing).toBe(18);
        expect(third?.words).toEqual([BID_TWENTY, HOLD_EIGHTEEN]);
        expect(third?.standing).toBe(20);
    });

    it("keeps the turn and the duel as they were before the run, and everything else of that table", () => {
        for (const each of runBetween(before, after).tables) {
            expect((each.hand as Hand).auction).toMatchObject(WAITING_FOR_MIDDLEHAND);
            expect(each.chairs).toBe(before.chairs);
            expect(each.hand).toMatchObject({ ...before.hand, auction: expect.anything() as unknown });
        }
    });

    it("gives each table the version of the update, so a step sent from the table before stays sent", () => {
        expect(runBetween(before, after).tables.map((each) => each.version)).toEqual([5, 5, 5]);
    });

    it("leaves the standing bid as it was while its words name no value", () => {
        const passing = auctionTable(5, [PASS_OF_MIDDLEHAND, PASS_OF_REARHAND], { standing: null });

        expect(auctionsOf(runBetween(before, passing)).map((auction) => auction.standing)).toEqual([null]);
    });

    it("leaves out forehand's play, which shows nothing at the table", () => {
        const played = auctionTable(5, [PASS_OF_MIDDLEHAND, PASS_OF_REARHAND, PLAY]);

        expect(runBetween(before, played).words).toEqual([
            { step: 0, action: "pass" },
            { step: 1, action: "pass" },
        ]);
    });
});

describe("an update that is no run", () => {
    const before = auctionTable(4, [], WAITING_FOR_MIDDLEHAND);
    const after = auctionTable(5, RUN);
    const said = saidBetween(before, after);

    it("is one that brought a single word", () => {
        const single = auctionTable(5, [BID_EIGHTEEN]);

        expect(bidRunBetween(before, single, saidBetween(before, single))).toBeNull();
    });

    it.each([
        { name: "the table before it had no hand", previous: { ...before, hand: null }, next: after },
        { name: "the table it brought has no hand", previous: before, next: { ...after, hand: null } },
        {
            name: "it dealt another hand",
            previous: { ...before, hand: { ...(before.hand as Hand), dealer_seat: FOREHAND } },
            next: after,
        },
        {
            name: "its words do not continue the ones the page has seen",
            previous: auctionTable(4, [BID_TWENTY, PASS_OF_FOREHAND, PASS_OF_REARHAND]),
            next: after,
        },
    ] satisfies { name: string; previous: Table; next: Table }[])("is one where $name", ({ previous, next }) => {
        expect(bidRunBetween(previous, next, said)).toBeNull();
    });
});
