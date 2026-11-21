import { describe, expect, it } from "vitest";
import { mix, phase, sampled } from "#lib/takt/timeline.ts";

describe("mix", () => {
    it.each([
        { share: 0, expected: 10 },
        { share: 0.25, expected: 12.5 },
        { share: 1, expected: 20 },
    ])("is $expected at the share $share of the way from 10 to 20", ({ share, expected }) => {
        expect(mix(10, 20, share)).toBe(expected);
    });
});

describe("phase", () => {
    it.each([
        { name: "before the span begins", seconds: 0.9, expected: 0 },
        { name: "as it begins", seconds: 1, expected: 0 },
        { name: "half-way through", seconds: 2, expected: 0.5 },
        { name: "as it ends", seconds: 3, expected: 1 },
        { name: "after it has ended", seconds: 7, expected: 1 },
    ])("is $expected $name", ({ seconds, expected }) => {
        expect(phase(seconds, 1, 2)).toBe(expected);
    });
});

describe("a sampled track", () => {
    const FRAME_SECONDS = 1 / 60;
    const clock = (seconds: number): number => seconds;

    it.each([{ seconds: 0.28 }, { seconds: 0.5 }, { seconds: 0.01 }])(
        "is read at the cue, at the end and evenly between, no further apart than a frame, over $seconds s",
        ({ seconds }) => {
            const instants = sampled(clock, seconds, FRAME_SECONDS);
            const gaps = instants.slice(1).map((instant, index) => instant - (instants[index] as number));

            expect(instants[0]).toBe(0);
            expect(instants.at(-1)).toBeCloseTo(seconds);
            for (const gap of gaps) {
                expect(gap).toBeCloseTo(gaps[0] as number);
                expect(gap).toBeLessThanOrEqual(FRAME_SECONDS + Number.EPSILON);
            }
        },
    );

    it("carries whatever look its track gives", () => {
        const looks = sampled((seconds) => ({ at: seconds }), 0.1, FRAME_SECONDS);

        expect(looks[0]).toEqual({ at: 0 });
    });
});
