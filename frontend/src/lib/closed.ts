import { words } from "#lib/words.ts";
import type { EndReason, Ended } from "../routes/(start)/tables.ts";

const SECONDS_PER_MINUTE = 60;

// Whole minutes rounded down from a minute on, so the wait never reads longer than the stored one; below that, seconds.
function waitWords(seconds: number): string {
    if (seconds < SECONDS_PER_MINUTE) return `${String(seconds)} ${seconds === 1 ? words.second : words.seconds}`;
    const minutes = Math.floor(seconds / SECONDS_PER_MINUTE);
    return `${String(minutes)} ${minutes === 1 ? words.minute : words.minutes}`;
}

// Each reason names its own heading; a reason added to the wire has to add its words here.
const HEADINGS: Record<EndReason, (ended: Ended) => string> = {
    empty: (ended) => `${waitWords(ended.empty_seconds)} ${words.nobodyThereClosed}`,
};

export function closedWords(ended: Ended): string {
    return HEADINGS[ended.reason](ended);
}
