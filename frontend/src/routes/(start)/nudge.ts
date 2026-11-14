import type { SeatNotice } from "#lib/openChair.ts";
import { words } from "#lib/words.ts";
import type { Table } from "./tables.ts";

// How often the chair was nudged at this version, whether the viewer may nudge it (the minute is the server's to judge)
// and, in the nudged chair's own answer only, who nudged last.
export type Nudge = { nudges: number; may_nudge: boolean; by_name: string | null };

// The sentence the nudged person reads once, when a nudge of the viewer's own chair arrives that the page had not seen.
export function nudgedNote(previous: Table, table: Table): SeatNotice | null {
    const nudge = table.chairs.find((chair) => chair.is_mine)?.nudge;
    if (nudge?.by_name == null) return null;
    const seen = previous.version === table.version ? previous.chairs.find((chair) => chair.is_mine)?.nudge : null;
    if (seen?.nudges === nudge.nudges) return null;
    return {
        text: `${nudge.by_name} ${words["table.nudgesYou"]}`,
        initials: [nudge.by_name.slice(0, 1)],
        seat: null,
        occupied: false,
    };
}
