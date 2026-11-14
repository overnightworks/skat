import { describe, expect, it } from "vitest";
import { cuesBetween, type Cue } from "#lib/cues.ts";
import { EVERY_HAND_DEALT, MIDDLEHAND, nudged, REARHAND, table } from "#lib/cues.fixtures.ts";

describe("the nudge a chair had between two versions of a table", () => {
    const running = table(4, EVERY_HAND_DEALT, { current: [] });

    it.each([
        {
            name: "the first nudge at the version the page shows",
            previous: running,
            next: nudged(running, MIDDLEHAND, 1),
            seats: [MIDDLEHAND],
        },
        {
            name: "a second nudge at that version",
            previous: nudged(running, MIDDLEHAND, 1),
            next: nudged(running, MIDDLEHAND, 2),
            seats: [MIDDLEHAND],
        },
        {
            name: "a nudge that comes with the next version",
            previous: running,
            next: nudged(table(5, EVERY_HAND_DEALT, { current: [] }), REARHAND, 1),
            seats: [REARHAND],
        },
        {
            name: "two chairs nudged at once",
            previous: running,
            next: nudged(nudged(running, MIDDLEHAND, 1), REARHAND, 1),
            seats: [MIDDLEHAND, REARHAND],
        },
    ])("is a cue for the chair of $name", ({ previous, next, seats }) => {
        expect(
            cuesBetween(previous, next)
                .filter((cue) => cue.kind === "nudged")
                .map((cue) => cue.seat),
        ).toEqual(seats);
    });

    it.each([
        { name: "nobody nudged", previous: running, next: running },
        {
            name: "the nudge was already shown",
            previous: nudged(running, MIDDLEHAND, 1),
            next: nudged(running, MIDDLEHAND, 1),
        },
        {
            name: "the nudges are fewer than shown",
            previous: nudged(running, MIDDLEHAND, 2),
            next: nudged(running, MIDDLEHAND, 1),
        },
        {
            name: "the table moved on without a nudge",
            previous: nudged(running, MIDDLEHAND, 1),
            next: table(5, EVERY_HAND_DEALT, { current: [] }),
        },
    ])("is no cue when $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).filter((cue) => cue.kind === "nudged")).toEqual([]);
    });

    it("is no cue on the first table of a page, which already shows the nudge as it stands", () => {
        expect(cuesBetween(undefined, nudged(running, MIDDLEHAND, 1))).toEqual([]);
    });

    it("is no cue for a table older than the one shown", () => {
        expect(cuesBetween(nudged(table(5, EVERY_HAND_DEALT, { current: [] }), MIDDLEHAND, 1), running)).toEqual([]);
    });

    it("is the same cue on every page of the table, whoever the viewer is and whatever the nudged seat's answer names", () => {
        const [tapper, nudgedOne] = [
            cuesBetween(running, nudged(running, MIDDLEHAND, 1)),
            cuesBetween(running, nudged(running, MIDDLEHAND, 1, "Felix")),
        ];

        expect(tapper).toEqual(nudgedOne);
        expect(tapper).toHaveLength(1);
    });

    it("picks another grumble for the next nudge of the same chair", () => {
        const picks = [1, 2].map((count) => {
            const [cue] = cuesBetween(running, nudged(running, MIDDLEHAND, count));
            return (cue as Extract<Cue, { kind: "nudged" }>).pick;
        });

        expect(new Set(picks).size).toBe(2);
    });
});
