import { describe, expect, it } from "vitest";
import type { Cue } from "#lib/cues.ts";
import { MOTION_SETS } from "#lib/motionSets.ts";
import { advance, jump, receive, SETTLED, timingOf, type Received, type StageState, type Timing } from "#lib/stage.ts";
import type { LastTrick, Playing } from "../routes/(start)/tables.ts";

const NOW = 10_000;
const TIMING: Timing = { restMilliseconds: 800, glideMilliseconds: 1000 };
const TRICK: LastTrick = {
    cards: [
        { suit: "kreuz", rank: "king" },
        { suit: "herz", rank: "nine" },
        { suit: "kreuz", rank: "ace" },
    ],
    leader_seat: 1,
    taker_seat: 3,
};
const BEFORE = { turn_seat: 3 } as Playing;
const LEAD: Cue = { kind: "card-played", seat: 3, card: { suit: "pik", rank: "ten" } };
const COMPLETING: Cue = { kind: "card-played", seat: 3, card: { suit: "kreuz", rank: "ace" } };
const TAKEN: Cue = { kind: "trick-taken", trick: TRICK };

function received(changes: Partial<Received>): Received {
    return { cues: [], before: BEFORE, timing: TIMING, mode: "sweep", now: NOW, ...changes };
}

function resting(glideMilliseconds = TIMING.glideMilliseconds): StageState {
    return { phase: "resting", until: NOW + TIMING.restMilliseconds, trick: TRICK, before: BEFORE, glideMilliseconds };
}

describe("the budget of a table", () => {
    it("is the set's rest and the time from gathering to landing", () => {
        expect(timingOf(MOTION_SETS.verspielt, false)).toEqual({ restMilliseconds: 800, glideMilliseconds: 1000 });
    });

    it.each([
        { name: "the window is hidden", motion: MOTION_SETS.verspielt, hidden: true },
        { name: "no motion set is in force", motion: undefined, hidden: false },
    ])("is zero when $name", ({ motion, hidden }) => {
        expect(timingOf(motion, hidden)).toBeNull();
    });
});

describe("a finished trick under „wegfegen“", () => {
    it("rests first, with no beat yet", () => {
        const step = receive(SETTLED, received({ cues: [COMPLETING, TAKEN] }));

        expect(step).toEqual({ stage: resting(), beats: [] });
    });

    it("holds the lead of the same update back until the moment is over", () => {
        const step = receive(SETTLED, received({ cues: [COMPLETING, TAKEN, LEAD] }));

        expect(step.stage).toEqual(resting());
    });

    it("jumps to the settled table at once with a budget of zero, and still sounds the sweep", () => {
        const step = receive(SETTLED, received({ cues: [COMPLETING, TAKEN], timing: null }));

        expect(step).toEqual({ stage: SETTLED, beats: ["glide-started"] });
    });

    it("glides when the rest is over, with one beat, and settles when the glide is over", () => {
        const glide = advance(resting(), NOW + TIMING.restMilliseconds);
        const settled = advance(glide.stage, NOW + TIMING.restMilliseconds + TIMING.glideMilliseconds);

        expect(glide).toEqual({
            stage: { ...resting(), phase: "gliding", until: NOW + 800 + 1000 },
            beats: ["glide-started"],
        });
        expect(settled).toEqual({ stage: SETTLED, beats: [] });
    });

    it.each([
        { name: "the rest", stage: resting(), now: NOW + 799 },
        { name: "a settled table", stage: SETTLED, now: NOW + 5000 },
    ])("does not move before the end of $name", ({ stage, now }) => {
        expect(advance(stage, now)).toEqual({ stage, beats: [] });
    });

    it("only refreshes the received table on an update with no card", () => {
        const step = receive(resting(), received({ cues: [{ kind: "word-said", said: { seat: 1, word: "kontra" } }] }));

        expect(step).toEqual({ stage: resting(), beats: [] });
    });

    it("jumps a resting trick with one beat when the next card lands, then applies it", () => {
        const step = receive(resting(), received({ cues: [LEAD] }));

        expect(step).toEqual({ stage: SETTLED, beats: ["glide-started"] });
    });

    it("jumps a gliding trick without a second beat when the next card lands", () => {
        const gliding = { ...resting(), phase: "gliding" } satisfies StageState;

        expect(receive(gliding, received({ cues: [LEAD] }))).toEqual({ stage: SETTLED, beats: [] });
    });

    it("jumps a resting trick when the window turns hidden, and a settled one stays", () => {
        expect(jump(resting())).toEqual({ stage: SETTLED, beats: ["glide-started"] });
        expect(jump(SETTLED)).toEqual({ stage: SETTLED, beats: [] });
    });

    it("begins the moment of the next trick after the jump when one card finishes another", () => {
        const step = receive(resting(), received({ cues: [COMPLETING, TAKEN] }));

        expect(step).toEqual({ stage: resting(), beats: ["glide-started"] });
    });
});

describe("a finished trick under „liegen lassen“", () => {
    it("needs no moment when no lead follows", () => {
        const step = receive(SETTLED, received({ cues: [COMPLETING, TAKEN], mode: "stay" }));

        expect(step).toEqual({ stage: SETTLED, beats: [] });
    });

    it("rests with the lead of the same update, then drops with no arc and no beat", () => {
        const step = receive(SETTLED, received({ cues: [COMPLETING, TAKEN, LEAD], mode: "stay" }));
        const dropped = advance(step.stage, NOW + TIMING.restMilliseconds);

        expect(step).toEqual({ stage: resting(0), beats: [] });
        expect(dropped).toEqual({ stage: SETTLED, beats: [] });
    });

    it("jumps with a budget of zero and sounds nothing", () => {
        const step = receive(SETTLED, received({ cues: [COMPLETING, TAKEN, LEAD], mode: "stay", timing: null }));

        expect(step).toEqual({ stage: SETTLED, beats: [] });
    });

    it("jumps a resting trick without a beat when the window turns hidden", () => {
        expect(jump(resting(0))).toEqual({ stage: SETTLED, beats: [] });
    });
});
