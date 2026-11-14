import { isChairCue, type Cue } from "./cues.ts";
import type { MotionSet } from "./motionSets.ts";
import type { LastTrick, Playing } from "../routes/(start)/tables.ts";

export const LAST_TRICK_MODES = ["sweep", "stay"] as const;
/** What happens to a finished trick: it is swept to its taker's pile, or it stays on the felt until the next lead. */
export type LastTrickMode = (typeof LAST_TRICK_MODES)[number];

export const DEFAULT_LAST_TRICK_MODE: LastTrickMode = "sweep";

/** A finished trick lies still, then glides to its taker's pile; a table with no trick on the move is settled. */
export type Phase = "settled" | "resting" | "gliding";

/** The pacing of the trick that is on the move, apart from the table the page received. Times are on the caller's clock. */
export interface StageState {
    readonly phase: Phase;
    /** The moment the phase ends; meaningless while settled. */
    readonly until: number;
    /** The finished trick that lies on the felt or glides off it, null while settled. */
    readonly trick: LastTrick | null;
    /** The playing the table showed before the update that finished the trick, whose last trick the brass rim still marks. */
    readonly before: Playing | null;
    /** How long the glide lasts once the rest is over; none means the trick drops to the next lead with no arc. */
    readonly glideMilliseconds: number;
}

export const SETTLED: StageState = { phase: "settled", until: 0, trick: null, before: null, glideMilliseconds: 0 };

/** What a moving table takes; null is a budget of zero, where every state shows at once. */
export interface Timing {
    readonly restMilliseconds: number;
    readonly glideMilliseconds: number;
}

const MILLISECONDS = 1000;

/** The budget of the table now: zero while the window is hidden or no motion set is in force. */
export function timingOf(motion: MotionSet | undefined, hidden: boolean): Timing | null {
    return motion === undefined || hidden
        ? null
        : {
              restMilliseconds: motion.trickRestSeconds * MILLISECONDS,
              glideMilliseconds: (motion.trickGatherSeconds + motion.trickGlideSeconds) * MILLISECONDS,
          };
}

/** How long the chairs that changed hands in `cues` move in the set: the longest of them, zero with no set in force or a hidden window. */
export function chairMoveMilliseconds(cues: readonly Cue[], motion: MotionSet | undefined, hidden: boolean): number {
    if (motion === undefined || hidden) return 0;
    const seconds = cues
        .filter(isChairCue)
        .map((cue) => (cue.kind === "chair-taken" ? motion.chairSitsSeconds : motion.chairEmptiesSeconds));
    return Math.max(0, ...seconds) * MILLISECONDS;
}

/** The moment the sweep begins, which the swept trick sounds at. */
export type Beat = "glide-started";

export interface Step {
    readonly stage: StageState;
    readonly beats: readonly Beat[];
}

export interface Received {
    readonly cues: readonly Cue[];
    readonly before: Playing | null;
    readonly timing: Timing | null;
    readonly mode: LastTrickMode;
    readonly now: number;
}

/** The moment is over at once: a trick that has not begun to glide still sounds its sweep once. */
export function jump(stage: StageState): Step {
    if (stage.phase === "settled") return { stage, beats: [] };
    return { stage: SETTLED, beats: stage.phase === "resting" && stage.glideMilliseconds > 0 ? ["glide-started"] : [] };
}

// A card laid ends the moment before it, since the table has moved on; the finished trick of this update then begins its own.
export function receive(stage: StageState, { cues, before, timing, mode, now }: Received): Step {
    const jumped = cues.some((cue) => cue.kind === "card-played") ? jump(stage) : { stage, beats: [] };
    const takenAt = cues.findIndex((cue) => cue.kind === "trick-taken");
    if (takenAt === -1) return jumped;
    const { trick } = cues[takenAt] as Extract<Cue, { kind: "trick-taken" }>;
    const leadFollows = cues.slice(takenAt + 1).some((cue) => cue.kind === "card-played");
    if (mode === "stay") {
        // A trick that stays lies on the felt with or without the stage; only a lead in the same update needs the rest.
        return leadFollows && timing !== null
            ? { stage: resting(trick, before, now, timing.restMilliseconds, 0), beats: jumped.beats }
            : { stage: SETTLED, beats: jumped.beats };
    }
    return timing === null
        ? { stage: SETTLED, beats: [...jumped.beats, "glide-started"] }
        : {
              stage: resting(trick, before, now, timing.restMilliseconds, timing.glideMilliseconds),
              beats: jumped.beats,
          };
}

function resting(
    trick: LastTrick,
    before: Playing | null,
    now: number,
    restMilliseconds: number,
    glideMilliseconds: number,
): StageState {
    return { phase: "resting", until: now + restMilliseconds, trick, before, glideMilliseconds };
}

/** The moment the phase ends, the next begins. */
export function advance(stage: StageState, now: number): Step {
    if (stage.phase === "settled" || now < stage.until) return { stage, beats: [] };
    if (stage.phase === "gliding" || stage.glideMilliseconds === 0) return { stage: SETTLED, beats: [] };
    return { stage: { ...stage, phase: "gliding", until: now + stage.glideMilliseconds }, beats: ["glide-started"] };
}
