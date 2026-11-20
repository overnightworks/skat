// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { fade, move, placeOf } from "#lib/takt/player.ts";
import type { Pose } from "#lib/takt/timeline.ts";

const POSE: Pose = { x: 5, y: 270.04, turn: -6, wide: 1.2, tall: 1.1, opacity: 0.5 };
const FRAME_SECONDS = 1 / 60;

// A part that keeps what it was asked to play instead of playing it.
function recordingPart() {
    const played: { frames: Keyframe[]; milliseconds: number }[] = [];
    const animate = (frames: Keyframe[], milliseconds: number): Animation => {
        played.push({ frames, milliseconds });
        return {} as Animation;
    };
    return { played, part: { animate } };
}

describe("a moved part", () => {
    it("is played for the moment's length, a frame at most between two looks", () => {
        const { played, part } = recordingPart();

        move(part, () => POSE, 0.5);

        expect(played).toHaveLength(1);
        expect(played[0]?.milliseconds).toBe(500);
        expect(0.5 / ((played[0]?.frames.length as number) - 1)).toBeLessThanOrEqual(FRAME_SECONDS + Number.EPSILON);
    });

    it("is written as a transform and an opacity and nothing else", () => {
        const { played, part } = recordingPart();

        move(part, () => POSE, 0.5);

        for (const frame of played[0]?.frames ?? [])
            expect(frame).toEqual({
                transform: "translate(5.0px, 270.0px) rotate(-6.0deg) scale(1.200, 1.100)",
                opacity: 0.5,
            });
    });

    it("follows its track from the cue to the end", () => {
        const { played, part } = recordingPart();

        move(part, (seconds) => ({ ...POSE, opacity: seconds }), 0.5);

        expect(played[0]?.frames[0]?.opacity).toBe(0);
        expect(played[0]?.frames.at(-1)?.opacity).toBeCloseTo(0.5);
    });
});

describe("a faded part", () => {
    it("is written as an opacity alone, for the moment's length", () => {
        const { played, part } = recordingPart();

        fade(part, (seconds) => seconds * 2, 0.5);

        expect(played[0]?.milliseconds).toBe(500);
        expect(played[0]?.frames[0]).toEqual({ opacity: 0 });
        expect(played[0]?.frames.at(-1)).toEqual({ opacity: expect.closeTo(1) as number });
    });
});

describe("the place of an element", () => {
    afterEach(() => {
        document.body.replaceChildren();
    });

    // An element nested in one parent per transform before it, each drawn in the box the layout would give it.
    function nested(transforms: string[]): HTMLElement {
        let element: HTMLElement = document.body;
        for (const transform of transforms) {
            const child = document.createElement("div");
            child.style.transform = transform;
            child.style.width = "70px";
            child.getBoundingClientRect = () => ({ left: 100, top: 200, width: 80, height: 110 }) as DOMRect;
            element.append(child);
            element = child;
        }
        return element;
    }

    it("is the middle of its box and its laid-out width", () => {
        expect(placeOf(nested([""]))).toEqual({ x: 140, y: 255, width: 70, turn: 0 });
    });

    it.each([
        { name: "a quarter turn", transforms: ["matrix(0, 1, -1, 0, 0, 0)"], turn: 90 },
        { name: "a turn the other way", transforms: ["matrix(0.866025, -0.5, 0.5, 0.866025, 12, 4)"], turn: -30 },
        {
            name: "a turn in space",
            transforms: ["matrix3d(0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)"],
            turn: 90,
        },
        { name: "no transform", transforms: ["none"], turn: 0 },
        {
            name: "its own turn on the turn of the element around it",
            transforms: ["matrix(0, 1, -1, 0, 0, 0)", "matrix(0.866025, 0.5, -0.5, 0.866025, 0, 0)"],
            turn: 120,
        },
    ])("carries $name", ({ transforms, turn }) => {
        expect(placeOf(nested(transforms)).turn).toBeCloseTo(turn, 3);
    });
});
