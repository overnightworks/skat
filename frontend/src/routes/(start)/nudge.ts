import type { SeatNotice } from "#lib/openChair.ts";
import { TABLE_NUDGE_SUFFIX } from "#lib/wire.ts";
import { words } from "#lib/words.ts";
import { post, type Chair, type Outcome, type Table } from "./tables.ts";

// How often the chair was nudged at this version, whether the viewer may nudge it (the minute is the server's to judge)
// and, in the nudged chair's own answer only, who nudged last.
export type Nudge = { nudges: number; may_nudge: boolean; by_name: string | null };

// The chairs nudged since `previous` was shown: a table at the same version counts from the nudges it showed, a newer one
// from none, since the nudges go with the version.
export function nudgedChairs(previous: Table, table: Table): (Chair & { nudge: Nudge })[] {
    return table.chairs.flatMap((chair) => {
        if (chair.nudge === null) return [];
        const seen = previous.version === table.version ? previous.chairs.find((each) => each.seat === chair.seat) : undefined;
        return chair.nudge.nudges > (seen?.nudge?.nudges ?? 0) ? [{ ...chair, nudge: chair.nudge }] : [];
    });
}

// The sentence the nudged person reads once, when a nudge of the viewer's own chair arrives that the page had not seen.
export function nudgedNote(previous: Table, table: Table): SeatNotice | null {
    const nudge = nudgedChairs(previous, table).find((chair) => chair.is_mine)?.nudge;
    if (nudge?.by_name == null) return null;
    return {
        text: `${nudge.by_name} ${words["table.nudgesYou"]}`,
        initials: [nudge.by_name.slice(0, 1)],
        seat: null,
        occupied: false,
    };
}

// The version, the seat and the nudges are the ones the page shows; the server alone decides whether the minute has
// passed, and a refused nudge changes nothing, so the answer is not read: the stream shows the table as it is.
export function nudgeSeat(id: string, version: number, seat: number, nudges: number): Promise<Outcome> {
    return post(id, TABLE_NUDGE_SUFFIX, { version, seat, nudges });
}
