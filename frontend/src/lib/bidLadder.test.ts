import { describe, expect, it } from "vitest";
import { bidLadder } from "#lib/bidLadder.ts";
import type { Auction } from "../routes/(start)/tables.ts";

const VIEWER = 2;

function auction(changes: Partial<Auction>): Auction {
    return {
        turn_seat: VIEWER,
        facing_seat: null,
        awaiting: "bid",
        standing: null,
        values: [],
        words: [],
        declared: null,
        ...changes,
    };
}

describe("the viewer's turn on the ladder", () => {
    it.each([
        {
            name: "bids the first value with no held tile before the first bid",
            changes: { awaiting: "bid", values: [18, 20, 22] },
            ladder: { held: null, lit: 18, rungs: [20, 22], rungsBid: true, main: { action: "bid", value: 18 } },
        },
        {
            name: "holds the standing bid and lights the next value",
            changes: { awaiting: "bid", standing: 20, values: [22, 23, 24] },
            ladder: { held: 20, lit: 22, rungs: [23, 24], rungsBid: true, main: { action: "bid", value: 22 } },
        },
        {
            name: "has no rung above the last value",
            changes: { awaiting: "bid", standing: 240, values: [264] },
            ladder: { held: 240, lit: 264, rungs: [], rungsBid: true, main: { action: "bid", value: 264 } },
        },
        {
            name: "lights the standing bid and shows passive rungs to a responder",
            changes: { awaiting: "answer", standing: 20 },
            ladder: { held: null, lit: 20, rungs: [22, 23, 24], rungsBid: false, main: { action: "hold" } },
        },
        {
            name: "holds the responder's own last hold",
            changes: {
                awaiting: "answer",
                standing: 20,
                words: [
                    { seat: 1, action: "hold", value: 23 },
                    { seat: VIEWER, action: "hold", value: 18 },
                ],
            },
            ladder: { held: 18, lit: 20, rungs: [22, 23, 24], rungsBid: false, main: { action: "hold" } },
        },
        {
            name: "does not take the responder's own bid for a hold",
            changes: { awaiting: "answer", standing: 22, words: [{ seat: VIEWER, action: "bid", value: 20 }] },
            ladder: { held: null, lit: 22, rungs: [23, 24, 27], rungsBid: false, main: { action: "hold" } },
        },
        {
            name: "has no passive rung above the top of the ladder",
            changes: { awaiting: "answer", standing: 264 },
            ladder: { held: null, lit: 264, rungs: [], rungsBid: false, main: { action: "hold" } },
        },
        {
            name: "plays at 18 with no held tile and no rung",
            changes: { awaiting: "play", standing: null },
            ladder: { held: null, lit: 18, rungs: [], rungsBid: false, main: { action: "play" } },
        },
    ] satisfies { name: string; changes: Partial<Auction>; ladder: object }[])("$name", ({ changes, ladder }) => {
        expect(bidLadder(auction(changes), VIEWER)).toEqual({ kind: "climb", ...ladder });
    });

    it("leaves only the pass at the top of the ladder", () => {
        expect(bidLadder(auction({ awaiting: "bid", standing: 264, values: [] }), VIEWER)).toEqual({
            kind: "passOnly",
        });
    });

    it.each([
        { name: "another seat's turn", changes: { turn_seat: 1 }, seat: VIEWER },
        { name: "a watcher, who has no seat", changes: {}, seat: undefined },
        { name: "an auction that is over", changes: { turn_seat: null, awaiting: null }, seat: VIEWER },
    ] satisfies { name: string; changes: Partial<Auction>; seat: number | undefined }[])(
        "shows nothing for $name",
        ({ changes, seat }) => {
            expect(bidLadder(auction(changes), seat)).toBeNull();
        },
    );
});
