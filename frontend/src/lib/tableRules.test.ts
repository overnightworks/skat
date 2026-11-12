import { describe, expect, it } from "vitest";
import { bockChip, bockLine } from "#lib/tableRules.ts";
import { words } from "#lib/words.ts";

describe("the Bock chip", () => {
    it("stands only at a table with Bock", () => {
        expect(bockChip(null)).toBeNull();
    });

    it.each([1, 3, 10])("counts the %i games still to come on the chip", (gamesLeft) => {
        expect(bockChip({ games_left: gamesLeft, factor: 2 })).toEqual({
            word: words["rules.chipBock"],
            count: { number: String(gamesLeft), label: words["rules.bockLeft"]({ count: gamesLeft }) },
        });
    });

    it("stands alone while no Bock game is pending", () => {
        expect(bockChip({ games_left: 0, factor: 1 })).toEqual({ word: words["rules.chipBock"], count: null });
    });
});

describe("the plaque's Bock line", () => {
    it.each([2, 4, 8])("names the factor ×%i of a Bock game", (factor) => {
        expect(bockLine({ games_left: 3, factor })).toBe(words["bock.factor"]({ factor: String(factor) }));
    });

    it.each([
        { case: "a table without Bock", bock: null },
        { case: "a game outside any Bock round", bock: { games_left: 0, factor: 1 } },
    ])("says nothing for $case", ({ bock }) => {
        expect(bockLine(bock)).toBeNull();
    });
});
