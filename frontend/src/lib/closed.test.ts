import { describe, expect, it } from "vitest";
import { closedWords } from "#lib/closed.ts";
import { words } from "#lib/words.ts";

describe("the heading of a table that closed itself", () => {
    it.each([
        [1, "closed.emptySeconds", 1],
        [5, "closed.emptySeconds", 5],
        [59, "closed.emptySeconds", 59],
        [60, "closed.emptyMinutes", 1],
        [61, "closed.emptyMinutes", 1],
        [119, "closed.emptyMinutes", 1],
        [120, "closed.emptyMinutes", 2],
        [1800, "closed.emptyMinutes", 30],
        [2700, "closed.emptyMinutes", 45],
    ] as const)("names a stored wait of %i seconds by the family %s at the count %i", (seconds, family, count) => {
        expect(closedWords({ reason: "empty", empty_seconds: seconds })).toBe(words[family](count));
    });
});
