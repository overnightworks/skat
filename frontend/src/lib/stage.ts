import { isChairCue, type Cue } from "./cues.ts";
import type { MotionSet } from "./motionSets.ts";
import { gatherInstants } from "./takt/gather.ts";
import { landInstants } from "./takt/land.ts";
import type { LastTrick, Playing } from "../routes/(start)/tables.ts";

export const LAST_TRICK_MODES = ["sweep", "stay"] as const;
/** What happens to a finished trick: it is swept to its taker's pile, or it stays on the felt until the next lead. */
export type LastTrickMode = (typeof LAST_TRICK_MODES)[number];

export const DEFAULT_LAST_TRICK_MODE: LastTrickMode = "sweep";

/**
 * A finished trick lies still, lifts the card that took it, then glides to its taker's pile. A table with no trick on
 * the move is settled.
 */
export type Phase = "settled" | "resting" | "lifting" | "gliding";

/** The pacing of the trick that is on the move, apart from the table the page received. Times are on the caller's clock. */
export interface StageState {
    readonly phase: Phase;
    /** The moment the phase ends; meaningless while settled. */
    readonly until: number;
    /** The finished trick that lies on the felt or glides off it, null while settled. */
    readonly trick: LastTrick | null;
    /** The playing the table showed before the update that finished the trick, whose last trick the brass rim still marks. */
    readonly before: Playing | null;
    /** How long the card that took the trick stands lifted once the trick has lain; none for a trick that drops to the next lead. */
    readonly liftMilliseconds: number;
    /** How long the glide lasts once the lift is over; none means the trick drops with no arc. */
    readonly glideMilliseconds: number;
    /** Whether the viewer's turn came with the update that finished this trick; it is shown once the trick has settled. */
    readonly turnPending: boolean;
    /** Whether this finished trick closes the hand, so the result waits and is shown once the trick has settled. */
    readonly resultPending: boolean;
}

export const SETTLED: StageState = {
    phase: "settled",
    until: 0,
    trick: null,
    before: null,
    liftMilliseconds: 0,
    glideMilliseconds: 0,
    turnPending: false,
    resultPending: false,
};

/** What a moving table takes; null is a budget of zero, where every state shows at once. */
export interface Timing {
    /** From the cue of a trick's last card until the card that took the trick lifts: that card lands, and the trick lies. */
    readonly liesMilliseconds: number;
    /** How long the taking card stands lifted before the trick is gathered. */
    readonly liftedMilliseconds: number;
    /** How much longer the taking card of a hand's last trick stands lifted, while the result waits. */
    readonly lastHoldMilliseconds: number;
    /** From the trick's first move to the instant it lies on its taker's pile. */
    readonly glideMilliseconds: number;
    readonly chairSitsMilliseconds: number;
    readonly chairEmptiesMilliseconds: number;
}

const MILLISECONDS = 1000;

/**
 * The budget of the table now: zero while the window is hidden or no motion set is in force. A trick's times are read
 * from the set's landing and gathering, so the trick rests from when its last card lies.
 */
export function timingOf(motion: MotionSet | undefined, hidden: boolean): Timing | null {
    if (motion === undefined || hidden) return null;
    const { lifts, gathers, piled } = gatherInstants(motion.trick);
    return {
        liesMilliseconds: (landInstants(motion.land).lies + lifts) * MILLISECONDS,
        liftedMilliseconds: (gathers - lifts) * MILLISECONDS,
        lastHoldMilliseconds: motion.trick.lastHoldSeconds * MILLISECONDS,
        glideMilliseconds: (piled - gathers) * MILLISECONDS,
        chairSitsMilliseconds: motion.chairSitsSeconds * MILLISECONDS,
        chairEmptiesMilliseconds: motion.chairEmptiesSeconds * MILLISECONDS,
    };
}

/** How long the chairs that changed hands in `cues` move: the longest of them, zero with no budget. */
export function chairMoveMilliseconds(cues: readonly Cue[], timing: Timing | null): number {
    if (timing === null) return 0;
    const milliseconds = cues
        .filter(isChairCue)
        .map((cue) => (cue.kind === "chair-taken" ? timing.chairSitsMilliseconds : timing.chairEmptiesMilliseconds));
    return Math.max(0, ...milliseconds);
}

/** The moments the stage hands to the page: the sweep begins, the table is settled for the viewer's turn, and for the result of the hand the last trick closed. */
export type Beat = "glide-started" | "turn-shown" | "result-shown";

export interface Step {
    readonly stage: StageState;
    readonly beats: readonly Beat[];
}

export interface Received {
    readonly cues: readonly Cue[];
    readonly before: Playing | null;
    readonly timing: Timing | null;
    readonly mode: LastTrickMode;
    /** Whether the trick of these cues is the last of the hand, whose result the page holds back until the stage has settled. */
    readonly closing: boolean;
    readonly now: number;
}

/** The moment is over at once: a trick that has not begun to glide still sounds its sweep once, and a turn or a result that waited is shown. */
export function jump(stage: StageState): Step {
    if (stage.phase === "settled") return { stage, beats: [] };
    const sweeps = stage.phase !== "gliding" && stage.glideMilliseconds > 0;
    return { stage: SETTLED, beats: [...(sweeps ? ["glide-started" as const] : []), ...settledBeats(stage)] };
}

function settledBeats(stage: StageState): readonly Beat[] {
    return [
        ...(stage.turnPending ? ["turn-shown" as const] : []),
        ...(stage.resultPending ? ["result-shown" as const] : []),
    ];
}

// The viewer's turn is shown once the table is settled: at once, or when the moment that holds it is over.
export function receive(stage: StageState, received: Received): Step {
    const step = receiveTrick(stage, received);
    if (!received.cues.some((cue) => cue.kind === "turn-came")) return step;
    return step.stage.phase === "settled"
        ? { stage: step.stage, beats: [...step.beats, "turn-shown"] }
        : { stage: { ...step.stage, turnPending: true }, beats: step.beats };
}

// A card laid ends the moment before it, since the table has moved on, and with it the turn that waited for that moment;
// the finished trick of this update then begins its own.
function receiveTrick(stage: StageState, { cues, before, timing, mode, closing, now }: Received): Step {
    const jumped = cues.some((cue) => cue.kind === "card-played")
        ? jump({ ...stage, turnPending: false })
        : { stage, beats: [] };
    const takenAt = cues.findIndex((cue) => cue.kind === "trick-taken");
    if (takenAt === -1) return jumped;
    const { trick } = cues[takenAt] as Extract<Cue, { kind: "trick-taken" }>;
    const leadFollows = cues.slice(takenAt + 1).some((cue) => cue.kind === "card-played");
    const resultBeats: readonly Beat[] = closing ? ["result-shown"] : [];
    if (mode === "stay") {
        // A trick that stays lies on the felt with or without the stage; only a lead in the same update, or the result
        // that comes after it, needs the rest. It lifts no card but the one that closes the hand.
        return (leadFollows || closing) && timing !== null
            ? { stage: resting(trick, before, now, timing, 0, closing), beats: jumped.beats }
            : { stage: SETTLED, beats: [...jumped.beats, ...resultBeats] };
    }
    return timing === null
        ? { stage: SETTLED, beats: [...jumped.beats, "glide-started", ...resultBeats] }
        : {
              stage: resting(trick, before, now, timing, timing.glideMilliseconds, closing),
              beats: jumped.beats,
          };
}

function resting(
    trick: LastTrick,
    before: Playing | null,
    now: number,
    timing: Timing,
    glideMilliseconds: number,
    resultPending: boolean,
): StageState {
    const lifts = glideMilliseconds > 0 || resultPending;
    const lifted = timing.liftedMilliseconds + (resultPending ? timing.lastHoldMilliseconds : 0);
    return {
        phase: "resting",
        until: now + timing.liesMilliseconds + (lifts ? 0 : lifted),
        trick,
        before,
        liftMilliseconds: lifts ? lifted : 0,
        glideMilliseconds,
        turnPending: false,
        resultPending,
    };
}

/** The moment the phase ends, the next begins. */
export function advance(stage: StageState, now: number): Step {
    if (stage.phase === "settled" || now < stage.until) return { stage, beats: [] };
    if (stage.phase === "resting" && stage.liftMilliseconds > 0)
        return { stage: { ...stage, phase: "lifting", until: now + stage.liftMilliseconds }, beats: [] };
    if (stage.phase === "gliding" || stage.glideMilliseconds === 0)
        return { stage: SETTLED, beats: settledBeats(stage) };
    return { stage: { ...stage, phase: "gliding", until: now + stage.glideMilliseconds }, beats: ["glide-started"] };
}
