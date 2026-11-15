import { afterEach, describe, expect, it, vi } from "vitest";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { OWN_SEAT, tableSeenFrom } from "#lib/tableSound.fixtures.ts";
import { REACTION_TOKENS, TABLE_REACTION_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import {
    EMOTES,
    isTableObject,
    reactionMark,
    reactionName,
    reactionsBetween,
    throwReaction,
    type Thrown,
} from "./reaction.ts";

const thrown = (number: number): Thrown => ({ number, reaction: "fire", by_seat: 1, by_name: "Anna" });

describe("the reactions a table update brings", () => {
    it("are the ones the page did not show before", () => {
        const before = { ...tableSeenFrom(OWN_SEAT), reactions: [thrown(1), thrown(2)] };
        const after = { ...before, reactions: [thrown(2), thrown(3)] };

        expect(reactionsBetween(before, after)).toEqual([thrown(3)]);
    });

    it("are none for a page that has no table before it, whatever the table carries", () => {
        expect(reactionsBetween(undefined, { ...tableSeenFrom(OWN_SEAT), reactions: [thrown(1)] })).toEqual([]);
    });

    it("are none once the reactions have left the answer", () => {
        const before = { ...tableSeenFrom(OWN_SEAT), reactions: [thrown(1)] };

        expect(reactionsBetween(before, tableSeenFrom(OWN_SEAT))).toEqual([]);
    });
});

describe("the closed set of reactions", () => {
    it.each(REACTION_TOKENS)("names %s in the catalog and tells an emote from an object of the table", (reaction) => {
        expect(reactionName(reaction)).toMatch(/^table\.(reaction|object)/u);
        expect(isTableObject(reaction)).toBe(reactionMark(reaction) === null);
    });

    it("offers the emotes in the tray and the objects of the table not", () => {
        expect(EMOTES).toEqual(REACTION_TOKENS.filter((reaction) => !isTableObject(reaction)));
        expect(EMOTES.length).toBeGreaterThan(0);
        expect(EMOTES.length).toBeLessThan(REACTION_TOKENS.length);
    });
});

describe("throwing a reaction", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("posts the reaction to the table", async () => {
        const fetching = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
        vi.stubGlobal("fetch", fetching);

        await throwReaction(TABLE_ID, "cheers");

        const [path, init] = fetching.mock.calls[0] as [string, RequestInit];
        expect([path, init.method, JSON.parse(init.body as string)]).toEqual([
            `${TABLES_PATH}/${TABLE_ID}${TABLE_REACTION_SUFFIX}`,
            "POST",
            { reaction: "cheers" },
        ]);
    });
});
