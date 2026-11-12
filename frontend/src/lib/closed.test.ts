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
        const gaps = { minutes: String(count) };
        expect(closedWords({ reason: "empty", empty_seconds: seconds, unplayed_days: null })).toBe(
            family === "closed.emptyMinutes" ? words[family](count, gaps) : words[family](count),
        );
    });

    it("writes a day-long wait in plain digits without a thousands separator", () => {
        expect(closedWords({ reason: "empty", empty_seconds: 86400, unplayed_days: null })).toBe(
            "1440 Minuten niemand da: Tisch geschlossen",
        );
    });
});

describe("the heading of a table that closed for want of play", () => {
    it.each([
        [1, "1 Tag nicht gespielt: Tisch geschlossen"],
        [2, "2 Tage nicht gespielt: Tisch geschlossen"],
        [90, "90 Tage nicht gespielt: Tisch geschlossen"],
    ])("names the stored %i days", (days, heading) => {
        expect(closedWords({ reason: "unplayed", empty_seconds: null, unplayed_days: days })).toBe(heading);
    });
});

describe("the count word of the series stepper", () => {
    it("names one game apart from several", () => {
        expect(words["start.seriesGames"](1)).not.toBe(words["start.seriesGames"](3));
    });
});
