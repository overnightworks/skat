import { describe, expect, it } from "vitest";

import { clockText, secondsLeft } from "#lib/answerClock.ts";

const UNTIL = "2026-11-19T12:01:00Z";
const AT = (secondsAfterNoon: number): number => Date.parse("2026-11-19T12:00:00Z") + secondsAfterNoon * 1000;

describe("the clock of an unanswered ask", () => {
    it.each([
        { now: 0, left: 60, text: "1:00" },
        { now: 18, left: 42, text: "0:42" },
        { now: 59.5, left: 1, text: "0:01" },
        { now: 60, left: 0, text: "0:00" },
        { now: 75, left: 0, text: "0:00" },
    ])("reads $text at $now seconds in", ({ now, left, text }) => {
        expect(secondsLeft(UNTIL, AT(now))).toBe(left);
        expect(clockText(left)).toBe(text);
    });
});
