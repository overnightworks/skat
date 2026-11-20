import { describe, expect, it } from "vitest";
import { closedStandings, closedWords } from "#lib/closed.ts";
import { words } from "#lib/words.ts";
import type { Ended } from "../routes/(start)/tables.ts";

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
        expect(
            closedWords({
                reason: "empty",
                empty_seconds: seconds,
                unplayed_days: null,
                closed_by_name: null,
                standings: null,
                game_count: null,
            }),
        ).toBe(family === "closed.emptyMinutes" ? words[family](count, gaps) : words[family](count));
    });

    it("writes a day-long wait in plain digits without a thousands separator", () => {
        expect(
            closedWords({
                reason: "empty",
                empty_seconds: 86400,
                unplayed_days: null,
                closed_by_name: null,
                standings: null,
                game_count: null,
            }),
        ).toBe("1440 Minuten niemand da: Tisch geschlossen");
    });
});

describe("the heading of a table that closed for want of play", () => {
    it.each([
        [1, "1 Tag nicht gespielt: Tisch geschlossen"],
        [2, "2 Tage nicht gespielt: Tisch geschlossen"],
        [90, "90 Tage nicht gespielt: Tisch geschlossen"],
    ])("names the stored %i days", (days, heading) => {
        expect(
            closedWords({
                reason: "unplayed",
                empty_seconds: null,
                unplayed_days: days,
                closed_by_name: null,
                standings: null,
                game_count: null,
            }),
        ).toBe(heading);
    });
});

describe("the heading of a table its opener closed", () => {
    it("names the closer", () => {
        expect(
            closedWords({
                reason: "closed",
                empty_seconds: null,
                unplayed_days: null,
                closed_by_name: "Anna",
                standings: null,
                game_count: null,
            }),
        ).toBe(words["closed.closedBy"]({ name: "Anna" }));
    });

    it("says only that the table is closed once the closer's name has expired", () => {
        expect(
            closedWords({
                reason: "closed",
                empty_seconds: null,
                unplayed_days: null,
                closed_by_name: null,
                standings: null,
                game_count: null,
            }),
        ).toBe(words["closed.closed"]);
    });
});

describe("the standings of an ended table", () => {
    const closedWith = { reason: "closed", empty_seconds: null, unplayed_days: null, closed_by_name: null } as const;
    const played: Ended = {
        ...closedWith,
        standings: [
            { display_name: "Anna", seat: 1, kind: "person", total: 502, won: 10, lost: 4, place: 1 },
            { display_name: "Mozart", seat: 3, kind: "agent", total: 233, won: 6, lost: 2, place: 2 },
        ],
        game_count: 36,
    };

    it("ranks the last series with its game count and each account's seat and kind, whatever the reason", () => {
        const view = closedStandings(played);

        expect(view?.heading).toBe(words["closed.seriesEnded"]);
        expect(view?.sub).toBe(words["table.seriesGames"](36));
        expect(view?.rows.map((row) => [row.place, row.name, row.seat, row.agent, row.gone])).toEqual([
            [1, "Anna", 1, false, false],
            [2, "Mozart", 3, true, false],
        ]);
    });

    it("has none for a table that finished no game", () => {
        expect(closedStandings({ ...closedWith, standings: null, game_count: null })).toBeNull();
    });
});

describe("the count word of the series stepper", () => {
    it("names one game apart from several", () => {
        expect(words["start.seriesGames"](1)).not.toBe(words["start.seriesGames"](3));
    });
});
