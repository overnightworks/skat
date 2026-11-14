import type { Cue } from "./cues.ts";
import { grumbleOf } from "./voice.ts";
import { words } from "./words.ts";

/** The cowbell swings in, rings and settles well within this long, and the grumble stays as long. */
const RINGING_MILLISECONDS = 3000;

interface Ringing {
    readonly seat: number;
    readonly line: string;
}

// The chairs whose bell rings now, each with the line it grumbles; the cue's pick makes it the same line on every page.
// Raw, so a ring is the object the timer later removes and no proxy of it.
let ringing: readonly Ringing[] = $state.raw([]);
// Kept apart from the state, so that stopping from an effect reads nothing it tracks.
let timers: ReturnType<typeof setTimeout>[] = [];

/** Starts the bell at the chair the cue names; the table seen again, as after a reload, never rings. */
export function ring(cue: Extract<Cue, { kind: "nudged" }>): void {
    const rung = { seat: cue.seat, line: words[grumbleOf(cue.pick)] };
    ringing = [...ringing.filter(({ seat }) => seat !== cue.seat), rung];
    timers.push(
        setTimeout(() => {
            ringing = ringing.filter((each) => each !== rung);
        }, RINGING_MILLISECONDS),
    );
}

/** The line a chair grumbles while its bell rings, or none. */
export function grumblingAt(seat: number): string | null {
    return ringing.find((each) => each.seat === seat)?.line ?? null;
}

/** A table left behind or shown again rings no bell. */
export function stopRinging(): void {
    for (const timer of timers) clearTimeout(timer);
    timers = [];
    ringing = [];
}
