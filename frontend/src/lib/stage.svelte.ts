import { isChairCue, type ChairCue, type Cue } from "./cues.ts";
import { MOTION_SETS } from "./motionSets.ts";
import { currentSettings, motionInForce } from "./settings.svelte.ts";
import {
    advance,
    chairMoveMilliseconds,
    jump,
    receive,
    SETTLED,
    timingOf,
    type StageState,
    type Step,
} from "./stage.ts";
import { soundForGlide, soundForTurn } from "./tableSound.ts";
import type { LastTrick, Table } from "../routes/(start)/tables.ts";

// The one stage of the page's table: the pacing of the trick that is on the move, apart from the received table.
let stage: StageState = $state(SETTLED);
// The seat whose pile's last trick the player looks at again, or none.
let looking: number | null = $state(null);
let timer: ReturnType<typeof setTimeout> | undefined;
// The chairs that changed hands in the latest update, while their motion lasts.
let moving: readonly ChairCue[] = $state([]);
let movingTimer: ReturnType<typeof setTimeout> | undefined;
// Whether the cards of a new deal are flying in; a table that is shown as it stands never deals.
let dealing = $state(false);
let dealTimer: ReturnType<typeof setTimeout> | undefined;
/** The cards of a deal take well under this long to fly in. */
const DEAL_MILLISECONDS = 2000;

// The cues are those of the update that brought the step, which the turn waits for when it is shown at once.
function apply(step: Step, cues: readonly Cue[] = []): void {
    clearTimeout(timer);
    stage = step.stage;
    if (step.beats.includes("glide-started")) soundForGlide();
    if (step.beats.includes("turn-shown")) soundForTurn(cues);
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

/** What happened to the chair of a seat while its motion lasts, or none. */
export function chairMoving(seat: number): ChairCue["kind"] | null {
    return moving.find((cue) => cue.seat === seat)?.kind ?? null;
}

function stopChairs(): void {
    clearTimeout(movingTimer);
    moving = [];
}

/** The first table of a page, a reconnect and a table left behind show at once, as the received table says. */
export function resetStage(): void {
    clearTimeout(timer);
    clearTimeout(dealTimer);
    stage = SETTLED;
    looking = null;
    stopChairs();
    dealing = false;
}

/** Whether the cards of a new deal fly in now, so only a deal this page saw moves them. */
export function isDealing(): boolean {
    return dealing;
}

function startDealing(): void {
    clearTimeout(dealTimer);
    dealing = true;
    dealTimer = setTimeout(() => {
        dealing = false;
    }, DEAL_MILLISECONDS);
}

/** The update `cues` brought to the table that followed `previous`. */
export function receiveOnStage(previous: Table | undefined, cues: readonly Cue[]): void {
    if (previous === undefined) {
        resetStage();
        return;
    }
    if (cues.some((cue) => cue.kind === "card-played")) looking = null;
    if (cues.some((cue) => cue.kind === "dealt")) startDealing();
    const motion = motionInForce();
    const motionSet = motion === undefined ? undefined : MOTION_SETS[motion];
    stopChairs();
    const chairMilliseconds = chairMoveMilliseconds(cues, motionSet, document.hidden);
    if (chairMilliseconds > 0) {
        moving = cues.filter(isChairCue);
        movingTimer = setTimeout(stopChairs, chairMilliseconds);
    }
    apply(
        receive(stage, {
            cues,
            before: previous.hand?.playing ?? null,
            timing: timingOf(motionSet, document.hidden),
            mode: currentSettings().lastTrick,
            now: Date.now(),
        }),
        cues,
    );
}

/** A hidden window shows the received table at once. */
export function jumpStage(): void {
    stopChairs();
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
