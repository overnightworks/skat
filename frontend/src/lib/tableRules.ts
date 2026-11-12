import type { Bock } from "../routes/(start)/tables.ts";
import { words } from "#lib/words.ts";

// The rules chip of a table with Bock; its count is the games still to come, the running one included, and stays off
// while none is pending.
export type BockChip = { word: string; count: { number: string; label: string } | null };

export function bockChip(bock: Bock | null): BockChip | null {
    if (bock === null) return null;
    const count = bock.games_left;
    return {
        word: words["rules.chipBock"],
        count: count === 0 ? null : { number: String(count), label: words["rules.bockLeft"]({ count }) },
    };
}

// What the plaque of a running game says of Bock: the factor that multiplies its list score.
export function bockLine(bock: Bock | null): string | null {
    return bock !== null && bock.factor > 1 ? words["bock.factor"]({ factor: String(bock.factor) }) : null;
}
