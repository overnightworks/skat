import { words } from "#lib/words.ts";
import type { Chair, Hand, Table } from "../routes/(start)/tables.ts";

// The sentence the others read once about the faces it names, each an initial; a null initial draws the agent's mark. A
// notice about a chair names its `seat` and whether it is `occupied`, and stands only while the chair stays so; one
// about no chair has a null seat.
export type SeatNotice = { text: string; initials: (string | null)[]; seat: number | null; occupied: boolean };

// Names ending in these letters take the apostrophe of the genitive instead of an s.
const APOSTROPHE_ENDINGS = /(?:[sßxz]|ce)$/i;

// While a running hand has an open chair it waits: no chair is on turn and nobody has a step to take.
export function handWaits(hand: Hand | null | undefined): boolean {
    return (hand?.waiting_seat ?? null) !== null;
}

// The line under the question before a sit: whose cards the sitter takes over; a chair freed before its holder was
// written down names nobody.
export function sitQuestionLine(formerHolder: string | null): string {
    if (formerHolder === null) return words["table.takeOverUnnamed"];
    const sentence = APOSTROPHE_ENDINGS.test(formerHolder)
        ? words["table.takeOverApostrophe"]
        : words["table.takeOverNamed"];
    return sentence({ name: formerHolder });
}

function chairAt(chairs: readonly Chair[], seat: number): Chair | undefined {
    return chairs.find((chair) => chair.seat === seat);
}

// A chair of the running hand that is open now and was held a moment before by an agent or by another person; the one
// who stood up reads no notice about herself; an agent's leave goes to the seated others only, a person's stand-up to
// every viewer.
function chairLeft(previous: Table, table: Table): SeatNotice | null {
    if (!handWaits(table.hand)) return null;
    const left = previous.chairs.find(
        (was) => !was.is_mine && was.occupant_name !== null && chairAt(table.chairs, was.seat)?.occupant_name === null,
    );
    if (left === undefined) return null;
    const name = left.occupant_name as string;
    const { seat } = left;
    if (left.occupant_kind !== "agent") {
        return { text: words["table.standUpNotice"]({ name }), initials: [name.slice(0, 1)], seat, occupied: false };
    }
    return table.chairs.some((chair) => chair.is_mine)
        ? { text: words["table.agentLeft"]({ name }), initials: [null], seat, occupied: false }
        : null;
}

// A chair that was open in the running hand and is taken now, by a person or an agent; the one who sat reads no notice
// about herself.
function openChairTaken(previous: Table, table: Table): SeatNotice | null {
    if (!handWaits(previous.hand)) return null;
    const taker = table.chairs.find(
        (chair) => chair.occupant_name !== null && chairAt(previous.chairs, chair.seat)?.occupant_name === null,
    );
    if (taker === undefined || taker.is_mine) return null;
    const name = taker.occupant_name as string;
    return {
        text: words["table.playsOn"]({ name }),
        initials: [taker.occupant_kind === "agent" ? null : name.slice(0, 1)],
        seat: taker.seat,
        occupied: true,
    };
}

// What the others read once when a streamed table shows a chair of the running hand open that an agent or a person held
// a moment before, or an open chair of the running hand taken; null when neither happened. A chair that opens or is
// taken between hands is the agent notice's.
export function seatNotice(previous: Table, table: Table): SeatNotice | null {
    return chairLeft(previous, table) ?? openChairTaken(previous, table);
}

// The notice a viewer still reads on a streamed table: it goes as soon as its chair changes hands again.
export function noticeStanding(shown: SeatNotice | null, table: Table): SeatNotice | null {
    if (shown === null || shown.seat === null) return shown;
    const occupied = chairAt(table.chairs, shown.seat)?.occupant_name !== null;
    return occupied === shown.occupied ? shown : null;
}

// The open chairs a person who stood up from this hand may not sit in: she may return only to the chair she left, even
// when someone else has taken it since, so every other open chair is locked for her; a viewer who held no chair of
// the hand has none.
export function lockedChairs(table: Table): ReadonlySet<number> {
    if (!table.chairs.some((chair) => chair.is_mine_to_return)) return new Set();
    return new Set(
        table.chairs
            .filter((chair) => chair.occupant_name === null && !chair.is_mine_to_return)
            .map((chair) => chair.seat),
    );
}
