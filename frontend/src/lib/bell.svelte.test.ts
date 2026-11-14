import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { grumblingAt, ring, stopRinging } from "#lib/bell.svelte.ts";
import { grumbleOf } from "#lib/voice.ts";
import { words } from "#lib/words.ts";

const NUDGED_SEAT = 2;
const OTHER_SEAT = 3;
const MILLISECONDS_PER_SECOND = 1000;
// The cowbell is gone within a few seconds, and still there after one.
const AFTER_THE_RING_SECONDS = 10;
const WHILE_IT_RINGS_SECONDS = 1;

describe("the bell that rings at a nudged chair", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        stopRinging();
        vi.useRealTimers();
    });

    it("grumbles the line the pick chooses at the nudged chair and at no other", () => {
        ring({ kind: "nudged", seat: NUDGED_SEAT, pick: 4 });

        expect([grumblingAt(NUDGED_SEAT), grumblingAt(OTHER_SEAT)]).toEqual([words[grumbleOf(4)], null]);
    });

    it("is quiet again after a few seconds, and not before", () => {
        ring({ kind: "nudged", seat: NUDGED_SEAT, pick: 4 });

        vi.advanceTimersByTime(WHILE_IT_RINGS_SECONDS * MILLISECONDS_PER_SECOND);
        const during = grumblingAt(NUDGED_SEAT);
        vi.advanceTimersByTime(AFTER_THE_RING_SECONDS * MILLISECONDS_PER_SECOND);

        expect([during, grumblingAt(NUDGED_SEAT)]).toEqual([words[grumbleOf(4)], null]);
    });

    it("grumbles the line of the later nudge when the chair is nudged again while it rings", () => {
        ring({ kind: "nudged", seat: NUDGED_SEAT, pick: 4 });
        ring({ kind: "nudged", seat: NUDGED_SEAT, pick: 5 });

        expect(grumblingAt(NUDGED_SEAT)).toBe(words[grumbleOf(5)]);
    });

    it("rings two chairs nudged at once, each with its own line", () => {
        ring({ kind: "nudged", seat: NUDGED_SEAT, pick: 4 });
        ring({ kind: "nudged", seat: OTHER_SEAT, pick: 5 });

        expect([grumblingAt(NUDGED_SEAT), grumblingAt(OTHER_SEAT)]).toEqual([words[grumbleOf(4)], words[grumbleOf(5)]]);
    });

    it("stops at once for a table that was left behind", () => {
        ring({ kind: "nudged", seat: NUDGED_SEAT, pick: 4 });

        stopRinging();

        expect(grumblingAt(NUDGED_SEAT)).toBeNull();
    });
});
