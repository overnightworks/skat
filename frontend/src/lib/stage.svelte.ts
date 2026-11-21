import type { BidRun } from "./bidRun.ts";
import { outcomeSeal, type Closing, type RunTelling, type Seal } from "./closingHand.ts";
import { isChairCue, type ChairCue, type Cue } from "./cues.ts";
import { MOTION_SETS, type MotionSet } from "./motionSets.ts";
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
import { runPace } from "./takt/bids.ts";
import type { LastTrick, Table } from "../routes/(start)/tables.ts";

// The one stage of the page's table: the pacing of the trick that is on the move, apart from the received table.
let stage: StageState = $state(SETTLED);
// The seat whose pile's last trick the player looks at again, or none.
let looking: number | null = $state(null);
let timer: ReturnType<typeof setTimeout> | undefined;
// What the page does with the result of the hand whose last trick the stage moves, once the stage has settled.
let showResult: (() => void) | undefined;
// Whether the declarer of the hand whose last trick the stage moves won it, none in a Ramsch.
let closingWon = $state<boolean | null>(null);
// The chairs that changed hands in the latest update, while their motion lasts.
let moving: readonly ChairCue[] = $state([]);
let movingTimer: ReturnType<typeof setTimeout> | undefined;
// Whether the cards of a new deal are flying in; a table that is shown as it stands never deals.
let dealing = $state(false);
let dealTimer: ReturnType<typeof setTimeout> | undefined;
/** The cards of a deal take well under this long to fly in. */
const DEAL_MILLISECONDS = 2000;
// Whether the table tells the words of a run, of which it has not told the last.
let speaking = $state(false);
let tellTimer: ReturnType<typeof setTimeout> | undefined;
// Ends the run on the stage at once: its last word, if that is still to tell, and the table moves on.
let endTelling: (() => void) | undefined;
const MILLISECONDS = 1000;

// The cues are those of the update that brought the step, which the turn waits for when it is shown at once.
function apply(step: Step, cues: readonly Cue[] = []): void {
    clearTimeout(timer);
    stage = step.stage;
    if (step.beats.includes("glide-started")) soundForGlide();
    if (step.beats.includes("turn-shown")) soundForTurn(cues);
    if (step.beats.includes("result-shown")) {
        const show = showResult;
        showResult = undefined;
        show?.();
    }
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

/**
 * The card that took the trick on the move, once the trick has lain and the card lifts: its seat, and the seal it
 * carries when the trick closes a declared hand. Nothing while the trick lands and lies, and while none moves.
 */
export function takingCard(): { seat: number; seal: Seal | null } | null {
    if (stage.phase !== "lifting" && stage.phase !== "gliding") return null;
    return { seat: (stage.trick as LastTrick).taker_seat, seal: stage.resultPending ? outcomeSeal(closingWon) : null };
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

function stopTelling(): void {
    clearTimeout(tellTimer);
    endTelling = undefined;
    speaking = false;
}

/** Whether the table tells the words of a run, so nobody says a word of their own until its last. */
export function tableSpeaks(): boolean {
    return speaking;
}

/**
 * Tells the words of a run one after another at the pace of its set, which is drawn from the game's seed and the words
 * alone, so every seat tells them at the same instants whatever its voice says: the first word at once, and the table
 * moves on once the last has stood. A word's voice has until the next word is told, and the last word's has no end. The
 * keys are live from the last word. A stage that stops moving meanwhile tells the last word at once and moves on.
 */
export function tellOnStage(run: BidRun, { tell, moveOn }: RunTelling): void {
    stopTelling();
    const last = run.words.length - 1;
    const startedAt = Date.now();
    const bids = motionOnStage()?.bids;
    const pace = bids && runPace(bids, run.seed, run.words);
    // The table may move on to the next run, so this one is over before it does.
    const end = (): void => {
        const untold = speaking;
        stopTelling();
        if (untold) tell(last, Infinity);
        moveOn();
    };
    const at = (seconds: number, then: () => void): void => {
        tellTimer = setTimeout(then, startedAt + seconds * MILLISECONDS - Date.now());
    };
    const step = (word: number): void => {
        if (pace === undefined || !stageMoves()) {
            end();
        } else if (word === last) {
            speaking = false;
            tell(last, Infinity);
            at(pace.over, end);
        } else {
            const next = pace.told[word + 1] as number;
            tell(word, next - (pace.told[word] as number));
            at(next, () => {
                step(word + 1);
            });
        }
    };
    speaking = true;
    endTelling = end;
    step(0);
}

/** The first table of a page, a reconnect and a table left behind show at once, as the received table says. */
export function resetStage(): void {
    clearTimeout(timer);
    stopTelling();
    showResult = undefined;
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

function motionSetInForce(): MotionSet | undefined {
    const motion = motionInForce();
    return motion === undefined ? undefined : MOTION_SETS[motion];
}

/** Whether the stage moves a trick now: a hidden window and a device without motion show every table at once. */
export function stageMoves(): boolean {
    return timingOf(motionSetInForce(), document.hidden) !== null;
}

/** The motion set a moment of the table plays in now; none while the stage does not move, where everything shows at once. */
export function motionOnStage(): MotionSet | undefined {
    return stageMoves() ? motionSetInForce() : undefined;
}

/**
 * The update `cues` brought to the table that followed `previous`. `closing` is given for the cues of the trick that
 * closes the hand: the stage shows its result once that trick has rested and swept, or at once when it does not move.
 */
export function receiveOnStage(previous: Table | undefined, cues: readonly Cue[], closing?: Closing): void {
    if (previous === undefined) {
        resetStage();
        return;
    }
    if (cues.some((cue) => cue.kind === "card-played")) looking = null;
    if (cues.some((cue) => cue.kind === "dealt")) startDealing();
    const timing = timingOf(motionSetInForce(), document.hidden);
    stopChairs();
    const chairMilliseconds = chairMoveMilliseconds(cues, timing);
    if (chairMilliseconds > 0) {
        moving = cues.filter(isChairCue);
        movingTimer = setTimeout(stopChairs, chairMilliseconds);
    }
    showResult = closing?.whenResultShown;
    closingWon = closing?.declarerWon ?? null;
    apply(
        receive(stage, {
            cues,
            before: previous.hand?.playing ?? null,
            timing,
            mode: currentSettings().lastTrick,
            closing: closing !== undefined,
            now: Date.now(),
        }),
        cues,
    );
}

/** A hidden window shows the received table at once. */
export function jumpStage(): void {
    endTelling?.();
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
