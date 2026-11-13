import { describe, expect, it } from "vitest";
import { entries } from "#lib/signInEntries.ts";
import { languages } from "#lib/words/index.ts";

describe("the sign-in entries", () => {
    it("name the language of every catalog once", () => {
        expect(entries().map((entry) => entry.language)).toEqual([...languages]);
    });
});
