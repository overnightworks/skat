import type { Cue } from "./cues.ts";
import { MOTION_SETS } from "./motionSets.ts";
import { currentSettings, motionInForce } from "./settings.svelte.ts";
import { advance, jump, receive, SETTLED, timingOf, type StageState, type Step } from "./stage.ts";
import { soundForGlide } from "./tableSound.ts";
import type { LastTrick, Table } from "../routes/(start)/tables.ts";

// The one stage of the page's table: the pacing of the trick that is on the move, apart from the received table.
let stage: StageState = $state(SETTLED);
// The seat whose pile's last trick the player looks at again, or none.
let looking: number | null = $state(null);
let timer: ReturnType<typeof setTimeout> | undefined;

function apply(step: Step): void {
    clearTimeout(timer);
    stage = step.stage;
    if (step.beats.length > 0) soundForGlide();
    if (stage.phase === "settled") return;
    const phaseEnds = stage.until;
    timer = setTimeout(() => {
        apply(advance(stage, phaseEnds));
    }, phaseEnds - Date.now());
}

/** The pacing now; a trick on the move shows apart from the received table. */
export function currentStage(): StageState {
    return stage;
}

/** The seat a finished trick glides to, while it glides. */
export function sweepingTo(): number | null {
    return stage.phase === "gliding" ? (stage.trick as LastTrick).taker_seat : null;
}

/** Whether the table waits for a trick to settle, so nobody is on turn yet. */
export function trickIsMoving(): boolean {
    return stage.phase !== "settled";
}

/** The first table of a page, a reconnect and a table left behind show at once, as the received table says. */
export function resetStage(): void {
    clearTimeout(timer);
    stage = SETTLED;
    looking = null;
}

/** The update `cues` brought to the table that followed `previous`. */
export function receiveOnStage(previous: Table | undefined, cues: readonly Cue[]): void {
    if (previous === undefined) {
        resetStage();
        return;
    }
    if (cues.some((cue) => cue.kind === "card-played")) looking = null;
    const motion = motionInForce();
    apply(
        receive(stage, {
            cues,
            before: previous.hand?.playing ?? null,
            timing: timingOf(motion === undefined ? undefined : MOTION_SETS[motion], document.hidden),
            mode: currentSettings().lastTrick,
            now: Date.now(),
        }),
    );
}

/** A hidden window shows the received table at once. */
export function jumpStage(): void {
    apply(jump(stage));
}

/** The seat whose pile's last trick is shown again, or none. */
export function lookingAt(): number | null {
    return looking;
}

export function lookAtLastTrick(seat: number): void {
    looking = seat;
}

export function stopLooking(): void {
    looking = null;
}
