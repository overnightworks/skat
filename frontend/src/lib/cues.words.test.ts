import { describe, expect, it } from "vitest";
import { cuesBetween } from "#lib/cues.ts";
import { declaringAt, EVERY_HAND_DEALT, FOREHAND, MIDDLEHAND, REARHAND, table } from "#lib/cues.fixtures.ts";
import type { AuctionWord, Declaring, Table } from "../routes/(start)/tables.ts";

describe("the bid a chair said between two versions of a table", () => {
    const BID_EIGHTEEN: AuctionWord = { seat: MIDDLEHAND, action: "bid", value: 18 };
    const HOLD_EIGHTEEN: AuctionWord = { seat: REARHAND, action: "hold", value: 18 };
    const PASS: AuctionWord = { seat: FOREHAND, action: "pass", value: null };
    const auctionTable = (version: number, spoken: AuctionWord[]): Table =>
        table(version, EVERY_HAND_DEALT, { declaring: null, spoken });

    it.each([
        { name: "a bid", spoken: [BID_EIGHTEEN], cue: { seat: MIDDLEHAND, word: { action: "bid", value: 18 } } },
        {
            name: "a hold, with the standing bid it answered",
            spoken: [BID_EIGHTEEN, HOLD_EIGHTEEN],
            before: [BID_EIGHTEEN],
            cue: { seat: REARHAND, word: { action: "hold", value: 18 } },
        },
        {
            name: "a pass",
            spoken: [PASS, BID_EIGHTEEN],
            before: [BID_EIGHTEEN],
            cue: { seat: FOREHAND, word: { action: "pass", value: null } },
        },
        {
            name: "a raised bid of a chair that bid before",
            spoken: [{ ...BID_EIGHTEEN, value: 20 }],
            before: [BID_EIGHTEEN],
            cue: { seat: MIDDLEHAND, word: { action: "bid", value: 20 } },
        },
    ] satisfies { name: string; spoken: AuctionWord[]; before?: AuctionWord[]; cue: object }[])(
        "is $name",
        ({ spoken, before, cue }) => {
            expect(cuesBetween(auctionTable(1, before ?? []), auctionTable(2, spoken))).toEqual([
                { kind: "bid-said", ...cue },
            ]);
        },
    );

    describe("when several chairs said theirs at once", () => {
        const BID_TWENTY: AuctionWord = { seat: REARHAND, action: "bid", value: 20 };
        const said = (before: AuctionWord[], spoken: AuctionWord[]) =>
            cuesBetween(auctionTable(1, before), auctionTable(3, spoken))
                .filter((cue) => cue.kind === "bid-said")
                .map((cue) => `${String(cue.seat)} ${cue.word.action}`);

        it("is every new word, the bid before the answer it got", () => {
            expect(said([], [PASS, BID_EIGHTEEN])).toEqual(["2 bid", "1 pass"]);
        });

        it("is the first pair's words before the second pair's bid", () => {
            expect(said([], [PASS, BID_EIGHTEEN, BID_TWENTY])).toEqual(["2 bid", "1 pass", "3 bid"]);
        });

        it("is the rearhand's pass after the words of the first pair", () => {
            const rearhandPassed = { seat: REARHAND, action: "pass" as const, value: null };

            expect(said([], [PASS, BID_EIGHTEEN, rearhandPassed])).toEqual(["2 bid", "1 pass", "3 pass"]);
        });

        it("is the answer of the chair that won the first pair after the second pair's bid", () => {
            const lost = { ...BID_EIGHTEEN, action: "pass" as const, value: null };
            const held = { seat: FOREHAND, action: "hold" as const, value: 18 };

            expect(said([], [held, lost, BID_TWENTY])).toEqual(["2 pass", "3 bid", "1 hold"]);
        });

        it("is only the words that are new", () => {
            expect(said([BID_EIGHTEEN], [HOLD_EIGHTEEN, BID_EIGHTEEN])).toEqual(["3 hold"]);
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
