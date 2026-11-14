import type { Cue } from "./cues.ts";
import { grumbleOf } from "./voice.ts";
import { words } from "./words.ts";

/** The cowbell swings in, rings and settles well within this long, and the grumble stays as long. */
const RINGING_MILLISECONDS = 3000;

interface Ringing {
    readonly seat: number;
    readonly line: string;
    readonly timer: ReturnType<typeof setTimeout>;
}

// The chairs whose bell rings now, each with the line it grumbles; the cue's pick makes it the same line on every page.
let ringing: readonly Ringing[] = $state([]);

/** Starts the bell at the chair the cue names; the table seen again, as after a reload, never rings. */
export function ring(cue: Extract<Cue, { kind: "nudged" }>): void {
    const line = words[grumbleOf(cue.pick)];
    const timer = setTimeout(() => {
        ringing = ringing.filter((each) => each.timer !== timer);
    }, RINGING_MILLISECONDS);
    for (const rung of ringing) if (rung.seat === cue.seat) clearTimeout(rung.timer);
    ringing = [...ringing.filter((each) => each.seat !== cue.seat), { seat: cue.seat, line, timer }];
}

/** The line a chair grumbles while its bell rings, or none. */
export function grumblingAt(seat: number): string | null {
    return ringing.find((each) => each.seat === seat)?.line ?? null;
}

/** A table left behind or shown again rings no bell. */
export function stopRinging(): void {
    for (const { timer } of ringing) clearTimeout(timer);
    ringing = [];
}
