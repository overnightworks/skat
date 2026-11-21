import { describe, expect, it } from "vitest";
import type { Cue } from "#lib/cues.ts";
import { MOTION_SETS } from "#lib/motionSets.ts";
import {
    advance,
    chairMoveMilliseconds,
    jump,
    receive,
    SETTLED,
    timingOf,
    type Received,
    type Timing,
} from "#lib/stage.ts";
import { gatherInstants } from "#lib/takt/gather.ts";
import { landInstants } from "#lib/takt/land.ts";
import type { LastTrick, Playing } from "../routes/(start)/tables.ts";

const NOW = 10_000;
const TIMING: Timing = timingOf(MOTION_SETS.verspielt, false) as Timing;
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
const TURN: Cue = { kind: "turn-came" };

function received(changes: Partial<Received>): Received {
    return { cues: [], before: BEFORE, timing: TIMING, mode: "sweep", closing: false, now: NOW, ...changes };
}

// The moments of a trick whose last card is received at NOW: the card that took it lifts, the trick is gathered, and it
// lies on its taker's pile.
const LIFTS = NOW + TIMING.liesMilliseconds;
const GATHERED = LIFTS + TIMING.liftedMilliseconds;
const PILED = GATHERED + TIMING.glideMilliseconds;
// The last trick of a hand stands lifted longer.
const LAST_GATHERED = GATHERED + TIMING.lastHoldMilliseconds;

const finishing = (changes: Partial<Received> = {}) =>
    receive(SETTLED, received({ cues: [COMPLETING, TAKEN], ...changes }));
// A trick that is swept, one that only rests before the lead of its update under „liegen lassen“, and the last of a hand.
const RESTING = finishing().stage;
const STAYING = finishing({ cues: [COMPLETING, TAKEN, LEAD], mode: "stay" }).stage;
const CLOSING = finishing({ closing: true }).stage;

describe.each(Object.values(MOTION_SETS).map((set) => ({ set, name: set.id })))(
    "the budget of a table in the set $name",
    ({ set }) => {
        const timing = timingOf(set, false) as Timing;
        const lies = landInstants(set.land).lies * 1000;
        const { lifts, gathers, piled } = gatherInstants(set.trick);

        it("counts a trick's rest from when its last card lies, not from when it was played", () => {
            expect(timing.liesMilliseconds).toBeCloseTo(lies + lifts * 1000);
            expect(timing.liesMilliseconds + timing.liftedMilliseconds).toBeCloseTo(lies + gathers * 1000);
        });

        it("takes the trick's way to its pile and the last trick's longer hold from the set", () => {
            expect(timing.glideMilliseconds).toBeCloseTo((piled - gathers) * 1000);
            expect(timing.lastHoldMilliseconds).toBe(set.trick.lastHoldSeconds * 1000);
        });
    },
);

describe("the budget of a table", () => {
    it.each([
        { name: "the window is hidden", motion: MOTION_SETS.verspielt, hidden: true },
        { name: "no motion set is in force", motion: undefined, hidden: false },
    ])("is zero when $name", ({ motion, hidden }) => {
        expect(timingOf(motion, hidden)).toBeNull();
    });
});

const SITTER = { seat: 2, name: "Nova", agent: true, mine: false };
const TAKEN_CHAIR: Cue = { kind: "chair-taken", inHand: false, ...SITTER };
const STOOD_CHAIR: Cue = { kind: "chair-stood", ...SITTER };
const OPENED_CHAIR: Cue = { kind: "chair-opened", ...SITTER };

describe("the time chairs move", () => {
    it.each(Object.values(MOTION_SETS).map((set) => ({ set, name: set.id })))(
        "is the set's time for a chair that is taken in the set $name",
        ({ set }) => {
            expect(chairMoveMilliseconds([TAKEN_CHAIR], timingOf(set, false))).toBe(set.chairSitsSeconds * 1000);
        },
    );

    it.each(
        Object.values(MOTION_SETS).flatMap((set) =>
            [STOOD_CHAIR, OPENED_CHAIR].map((cue) => ({ set, cue, name: `${cue.kind} in ${set.id}` })),
        ),
    )("is the set's time for a chair that empties: $name", ({ set, cue }) => {
        expect(chairMoveMilliseconds([cue], timingOf(set, false))).toBe(set.chairEmptiesSeconds * 1000);
    });

    it("is the longest of the chairs that move in one update", () => {
        const set = MOTION_SETS.verspielt;

        expect(chairMoveMilliseconds([OPENED_CHAIR, TAKEN_CHAIR], timingOf(set, false))).toBe(
            Math.max(set.chairSitsSeconds, set.chairEmptiesSeconds) * 1000,
        );
    });

    it.each([
        { name: "the window is hidden", motion: MOTION_SETS.verspielt, hidden: true, cues: [TAKEN_CHAIR] },
        { name: "no motion set is in force", motion: undefined, hidden: false, cues: [TAKEN_CHAIR] },
        { name: "no chair changed hands", motion: MOTION_SETS.verspielt, hidden: false, cues: [TAKEN] },
    ])("is zero when $name", ({ motion, hidden, cues }) => {
        expect(chairMoveMilliseconds(cues, timingOf(motion, hidden))).toBe(0);
    });
});

describe("a finished trick under „wegfegen“", () => {
    it("lies until its last card has landed and the card that took it lifts, with no beat yet", () => {
        const step = finishing();

        expect(step.stage).toMatchObject({ phase: "resting", until: LIFTS, trick: TRICK, before: BEFORE });
        expect(step.beats).toEqual([]);
    });

    it("holds the lead of the same update back until the moment is over", () => {
        const step = finishing({ cues: [COMPLETING, TAKEN, LEAD] });

        expect(step.stage).toEqual(RESTING);
    });

    it("jumps to the settled table at once with a budget of zero, and still sounds the sweep", () => {
        const step = finishing({ timing: null });

        expect(step).toEqual({ stage: SETTLED, beats: ["glide-started"] });
    });

    it("lifts the card that took it, glides with one beat when the lift is over, and settles when the glide is over", () => {
        const lifting = advance(RESTING, LIFTS);
        const gliding = advance(lifting.stage, GATHERED);
        const settled = advance(gliding.stage, PILED);

        expect(lifting.stage).toMatchObject({ phase: "lifting", until: GATHERED, trick: TRICK });
        expect(lifting.beats).toEqual([]);
        expect(gliding.stage).toMatchObject({ phase: "gliding", until: PILED, trick: TRICK });
        expect(gliding.beats).toEqual(["glide-started"]);
        expect(settled).toEqual({ stage: SETTLED, beats: [] });
    });

    it.each([
        { name: "the rest", stage: RESTING, now: LIFTS - 1 },
        { name: "the lift", stage: advance(RESTING, LIFTS).stage, now: GATHERED - 1 },
        { name: "a settled table", stage: SETTLED, now: NOW + 5000 },
    ])("does not move before the end of $name", ({ stage, now }) => {
        expect(advance(stage, now)).toEqual({ stage, beats: [] });
    });

    it("only refreshes the received table on an update with no card", () => {
        const step = receive(RESTING, received({ cues: [{ kind: "word-said", said: { seat: 1, word: "kontra" } }] }));

        expect(step).toEqual({ stage: RESTING, beats: [] });
    });

    it.each([
        { name: "resting", stage: RESTING },
        { name: "lifting", stage: advance(RESTING, LIFTS).stage },
    ])("jumps a $name trick with one beat when the next card lands, then applies it", ({ stage }) => {
        const step = receive(stage, received({ cues: [LEAD] }));

        expect(step).toEqual({ stage: SETTLED, beats: ["glide-started"] });
    });

    it("jumps a gliding trick without a second beat when the next card lands", () => {
        const gliding = advance(advance(RESTING, LIFTS).stage, GATHERED).stage;

        expect(receive(gliding, received({ cues: [LEAD] }))).toEqual({ stage: SETTLED, beats: [] });
    });

    it("jumps a resting trick when the window turns hidden, and a settled one stays", () => {
        expect(jump(RESTING)).toEqual({ stage: SETTLED, beats: ["glide-started"] });
        expect(jump(SETTLED)).toEqual({ stage: SETTLED, beats: [] });
    });

    it("begins the moment of the next trick after the jump when one card finishes another", () => {
        const step = receive(RESTING, received({ cues: [COMPLETING, TAKEN] }));

        expect(step).toEqual({ stage: RESTING, beats: ["glide-started"] });
    });
});

describe("a finished trick under „liegen lassen“", () => {
    it("needs no moment when no lead follows", () => {
        const step = finishing({ mode: "stay" });

        expect(step).toEqual({ stage: SETTLED, beats: [] });
    });

    it("rests with the lead of the same update as long as a swept trick lies, then drops with no lift, no arc and no beat", () => {
        const step = finishing({ cues: [COMPLETING, TAKEN, LEAD], mode: "stay" });

        expect(step.stage).toMatchObject({ phase: "resting", until: GATHERED, trick: TRICK });
        expect(step.beats).toEqual([]);
        expect(advance(step.stage, GATHERED)).toEqual({ stage: SETTLED, beats: [] });
    });

    it("jumps with a budget of zero and sounds nothing", () => {
        const step = finishing({ cues: [COMPLETING, TAKEN, LEAD], mode: "stay", timing: null });

        expect(step).toEqual({ stage: SETTLED, beats: [] });
    });

    it("jumps a resting trick without a beat when the window turns hidden", () => {
        expect(jump(STAYING)).toEqual({ stage: SETTLED, beats: [] });
    });
});

describe("the turn that came to the viewer", () => {
    const waiting = finishing({ cues: [COMPLETING, TAKEN, TURN] });

    it("is shown at once when no trick is on the move", () => {
        expect(receive(SETTLED, received({ cues: [LEAD, TURN] }))).toEqual({ stage: SETTLED, beats: ["turn-shown"] });
    });

    it("is shown at once with a budget of zero, after the sweep that sounds", () => {
        const step = finishing({ cues: [COMPLETING, TAKEN, TURN], timing: null });

        expect(step).toEqual({ stage: SETTLED, beats: ["glide-started", "turn-shown"] });
    });

    it("waits for the trick to rest, lift and glide before it is shown", () => {
        const lifting = advance(waiting.stage, LIFTS);
        const gliding = advance(lifting.stage, GATHERED);
        const settled = advance(gliding.stage, PILED);

        expect(waiting.beats).toEqual([]);
        expect(lifting.beats).toEqual([]);
        expect(gliding.beats).toEqual(["glide-started"]);
        expect(settled).toEqual({ stage: SETTLED, beats: ["turn-shown"] });
    });

    it("is shown when a trick that drops with no arc has dropped", () => {
        const step = finishing({ cues: [COMPLETING, TAKEN, LEAD, TURN], mode: "stay" });

        expect(advance(step.stage, GATHERED)).toEqual({ stage: SETTLED, beats: ["turn-shown"] });
    });

    it("is shown when the window turns hidden while the trick rests", () => {
        expect(jump(waiting.stage)).toEqual({ stage: SETTLED, beats: ["glide-started", "turn-shown"] });
    });

    it("is dropped when a card laid ends the moment it waited for", () => {
        const step = receive(waiting.stage, received({ cues: [LEAD] }));

        expect(step).toEqual({ stage: SETTLED, beats: ["glide-started"] });
    });

    it("is not shown again once it has been", () => {
        expect(advance(SETTLED, NOW)).toEqual({ stage: SETTLED, beats: [] });
    });
});

describe("the result of the hand the last trick ends", () => {
    it("waits for the last trick to rest, lift its taking card for its longer hold and glide before it is shown", () => {
        const lifting = advance(CLOSING, LIFTS);
        const gliding = advance(lifting.stage, LAST_GATHERED);
        const settled = advance(gliding.stage, LAST_GATHERED + TIMING.glideMilliseconds);

        expect(CLOSING).toMatchObject({ phase: "resting", until: LIFTS });
        expect(lifting.stage).toMatchObject({ phase: "lifting", until: LAST_GATHERED });
        expect(lifting.beats).toEqual([]);
        expect(gliding.beats).toEqual(["glide-started"]);
        expect(settled).toEqual({ stage: SETTLED, beats: ["result-shown"] });
    });

    it("is shown when the window turns hidden while the last trick lifts its taking card, the sweep still sounding", () => {
        const lifting = advance(CLOSING, LIFTS);

        expect(jump(lifting.stage)).toEqual({ stage: SETTLED, beats: ["glide-started", "result-shown"] });
    });

    it("is shown at once with a budget of zero, the sweep still sounding", () => {
        const step = finishing({ closing: true, timing: null });

        expect(step).toEqual({ stage: SETTLED, beats: ["glide-started", "result-shown"] });
    });

    it("is shown when the window turns hidden while the last trick rests", () => {
        expect(jump(CLOSING)).toEqual({ stage: SETTLED, beats: ["glide-started", "result-shown"] });
    });

    it("is shown after the rest and the lift of a last trick that stays on the felt", () => {
        const step = finishing({ closing: true, mode: "stay" });
        const lifting = advance(step.stage, LIFTS);

        expect(step.stage).toMatchObject({ phase: "resting", until: LIFTS });
        expect(step.beats).toEqual([]);
        expect(lifting.stage).toMatchObject({ phase: "lifting", until: LAST_GATHERED });
        expect(advance(lifting.stage, LAST_GATHERED)).toEqual({ stage: SETTLED, beats: ["result-shown"] });
    });

    it("is shown at once with a budget of zero when the last trick stays on the felt", () => {
        const step = finishing({ closing: true, mode: "stay", timing: null });

        expect(step).toEqual({ stage: SETTLED, beats: ["result-shown"] });
    });
});
