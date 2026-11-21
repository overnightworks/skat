import { describe, expect, it } from "vitest";
import { cuesBetween } from "#lib/cues.ts";
import { declaringAt, EVERY_HAND_DEALT, FOREHAND, MIDDLEHAND, REARHAND, table } from "#lib/cues.fixtures.ts";
import type { AuctionWord, Declaring, Table } from "../routes/(start)/tables.ts";

describe("the bid a chair said between two versions of a table", () => {
    const BID_EIGHTEEN: AuctionWord = { seat: MIDDLEHAND, action: "bid", value: 18 };
    const HOLD_EIGHTEEN: AuctionWord = { seat: REARHAND, action: "hold", value: 18 };
    const PASS: AuctionWord = { seat: FOREHAND, action: "pass", value: null };
    const auctionTable = (version: number, said: AuctionWord[]): Table =>
        table(version, EVERY_HAND_DEALT, { declaring: null, spoken: said });

    it.each([
        { name: "a bid", said: [BID_EIGHTEEN], cue: { seat: MIDDLEHAND, word: { action: "bid", value: 18 } } },
        {
            name: "a hold, with the standing bid it answered",
            before: [BID_EIGHTEEN],
            said: [BID_EIGHTEEN, HOLD_EIGHTEEN],
            cue: { seat: REARHAND, word: { action: "hold", value: 18 } },
        },
        {
            name: "a pass",
            before: [BID_EIGHTEEN],
            said: [BID_EIGHTEEN, PASS],
            cue: { seat: FOREHAND, word: { action: "pass", value: null } },
        },
        {
            name: "a raised bid of a chair that bid before",
            before: [BID_EIGHTEEN, HOLD_EIGHTEEN],
            said: [BID_EIGHTEEN, HOLD_EIGHTEEN, { ...BID_EIGHTEEN, value: 20 }],
            cue: { seat: MIDDLEHAND, word: { action: "bid", value: 20 } },
        },
    ] satisfies { name: string; said: AuctionWord[]; before?: AuctionWord[]; cue: object }[])(
        "is $name",
        ({ said, before, cue }) => {
            expect(cuesBetween(auctionTable(1, before ?? []), auctionTable(2, said))).toEqual([
                { kind: "bid-said", ...cue },
            ]);
        },
    );

    describe("when the table stepped for the plans, several words in one update", () => {
        const BID_TWENTY: AuctionWord = { ...BID_EIGHTEEN, value: 20 };
        const HOLD_TWENTY: AuctionWord = { ...HOLD_EIGHTEEN, value: 20 };
        const run = [BID_EIGHTEEN, HOLD_EIGHTEEN, BID_TWENTY, HOLD_TWENTY, { ...PASS, seat: MIDDLEHAND }];
        const said = (before: AuctionWord[], after: AuctionWord[]) =>
            cuesBetween(auctionTable(1, before), auctionTable(3, after))
                .filter((cue) => cue.kind === "bid-said")
                .map((cue) => `${String(cue.seat)} ${cue.word.action} ${String(cue.word.value)}`);

        it("is every word of the run as its chair's own, in the order said", () => {
            expect(said([], run)).toEqual(["2 bid 18", "3 hold 18", "2 bid 20", "3 hold 20", "2 pass null"]);
        });

        it("is only the words past the ones the page has seen", () => {
            expect(said(run.slice(0, 2), run)).toEqual(["2 bid 20", "3 hold 20", "2 pass null"]);
        });

        it("is every word of a hand whose words do not continue the ones seen", () => {
            expect(said([BID_TWENTY], [BID_EIGHTEEN, HOLD_EIGHTEEN])).toEqual(["2 bid 18", "3 hold 18"]);
        });
    });

    it.each([
        { name: "the first answer of the page", previous: undefined, next: auctionTable(2, [BID_EIGHTEEN]) },
        {
            name: "a table that is not newer",
            previous: auctionTable(2, []),
            next: auctionTable(2, [BID_EIGHTEEN]),
        },
        {
            name: "words that did not change",
            previous: auctionTable(1, [BID_EIGHTEEN]),
            next: auctionTable(2, [BID_EIGHTEEN]),
        },
        {
            name: "a hand with no words yet",
            previous: { ...auctionTable(1, []), hand: null },
            next: auctionTable(2, []),
        },
        {
            name: "a play, which shows nothing at the table",
            previous: auctionTable(1, []),
            next: auctionTable(2, [{ seat: FOREHAND, action: "play", value: 18 }]),
        },
    ] satisfies { name: string; previous: Table | undefined; next: Table }[])("is not $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).some((cue) => cue.kind === "bid-said")).toBe(false);
    });
});

describe("the game announced between two versions of a table", () => {
    const announced = (declaration: Declaring["declaration"]): Table =>
        table(2, EVERY_HAND_DEALT, { declaring: { ...declaringAt("declared"), declaration } });
    const HERZ_HAND = { game: "herz", hand: true, ouvert: false, announcement: "schneider" } as const;

    it("is the game that the declarer declared, once", () => {
        const before = table(1, EVERY_HAND_DEALT, { declaring: declaringAt("picked") });

        expect(cuesBetween(before, announced(HERZ_HAND))).toContainEqual({ kind: "game-announced", ...HERZ_HAND });
        expect(cuesBetween({ ...announced(HERZ_HAND), version: 2 }, { ...announced(HERZ_HAND), version: 3 })).toEqual(
            [],
        );
    });

    it("is not told to a page that has no table before it", () => {
        expect(cuesBetween(undefined, announced(HERZ_HAND))).toEqual([]);
    });
});
