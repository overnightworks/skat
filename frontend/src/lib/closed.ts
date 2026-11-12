import { words } from "#lib/words.ts";
import type { EndReason, Ended } from "../routes/(start)/tables.ts";

const SECONDS_PER_MINUTE = 60;

// Whole minutes rounded down from a minute on, so the wait never reads longer than the stored one; below that, seconds.
// The minutes go in as a named gap in plain digits, because the count's thousands separator would change a long wait's reading.
function emptyHeading(seconds: number): string {
    if (seconds < SECONDS_PER_MINUTE) return words["closed.emptySeconds"](seconds);
    const minutes = Math.floor(seconds / SECONDS_PER_MINUTE);
    return words["closed.emptyMinutes"](minutes, { minutes: String(minutes) });
}

// Each reason names its own heading; a reason added to the wire has to add its words here.
const HEADINGS: Record<EndReason, (ended: Ended) => string> = {
    empty: (ended) => emptyHeading(ended.empty_seconds),
};

export function closedWords(ended: Ended): string {
    return HEADINGS[ended.reason](ended);
}
