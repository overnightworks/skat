import { describe, expect, it } from "vitest";
import { closedWords } from "#lib/closed.ts";

describe("the heading of a table that closed itself", () => {
    it.each([
        [1, "1 Sekunde"],
        [5, "5 Sekunden"],
        [59, "59 Sekunden"],
        [60, "1 Minute"],
        [61, "1 Minute"],
        [119, "1 Minute"],
        [120, "2 Minuten"],
        [1800, "30 Minuten"],
        [2700, "45 Minuten"],
    ])("names a stored wait of %i seconds as %s", (seconds, wait) => {
        expect(closedWords({ reason: "empty", empty_seconds: seconds })).toBe(`${wait} niemand da: Tisch geschlossen`);
    });
});
