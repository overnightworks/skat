import { words } from "#lib/words.ts";
import type { Chair, Hand, Table } from "../routes/(start)/tables.ts";

// The sentence the others read once about a chair of the running hand; a null initial draws the agent's mark.
export type SeatNotice = { text: string; initial: string | null };

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

// A chair of the running hand that is open now and held an agent a moment before.
function agentLeft(previous: Table, table: Table): SeatNotice | null {
    if (!handWaits(table.hand)) return null;
    const left = previous.chairs.find(
        (was) => was.occupant_kind === "agent" && chairAt(table.chairs, was.seat)?.occupant_name === null,
    );
    return left === undefined
        ? null
        : { text: words["table.agentLeft"]({ name: left.occupant_name as string }), initial: null };
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
        initial: taker.occupant_kind === "agent" ? null : name.slice(0, 1),
    };
}

// What the others read once when a streamed table shows a chair of the running hand open that an agent held a moment
// before, or an open chair of the running hand taken; null when neither happened. A person's stand-up has its own
// notice, and a chair taken between hands is the agent notice's.
export function seatNotice(previous: Table, table: Table): SeatNotice | null {
    return agentLeft(previous, table) ?? openChairTaken(previous, table);
}
