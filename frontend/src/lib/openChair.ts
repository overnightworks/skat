import { words } from "#lib/words.ts";
import type { Cue, OpenedCue, TakenCue } from "./cues.ts";
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

// The chair of the running hand that opened under an agent or another person, whose leave the others read: an agent's
// to the seated others only, a person's stand-up to every viewer; the one who stood up reads no notice about herself.
function openedChairNotice(cues: readonly Cue[], table: Table): SeatNotice | null {
    const opened = cues.find((cue): cue is OpenedCue => cue.kind === "chair-opened" && !cue.mine);
    if (opened === undefined) return null;
    const { seat, name } = opened;
    if (!opened.agent) {
        return { text: words["table.standUpNotice"]({ name }), initials: [name.slice(0, 1)], seat, occupied: false };
    }
    return table.chairs.some((chair) => chair.is_mine)
        ? { text: words["table.agentLeft"]({ name }), initials: [null], seat, occupied: false }
        : null;
}

// The chairs taken in the update: one that was open in the running hand is told as its sitter playing on, never to the
// sitter herself; one that was free between hands is told only for an agent who sat.
function takenChairNotice(cues: readonly Cue[]): SeatNotice | null {
    const taken = cues.filter((cue): cue is TakenCue => cue.kind === "chair-taken");
    const first = taken[0];
    if (first === undefined) return null;
    if (first.inHand) {
        const { name } = first;
        return first.mine
            ? null
            : {
                  text: words["table.playsOn"]({ name }),
                  initials: [first.agent ? null : name.slice(0, 1)],
                  seat: first.seat,
                  occupied: true,
              };
    }
    const agent = taken.find((cue) => cue.agent);
    return agent === undefined
        ? null
        : { text: words["table.agentSits"]({ name: agent.name }), initials: [null], seat: agent.seat, occupied: true };
}

// What the others read once when a streamed table brought a chair of the running hand that opened, or was taken, or an
// agent who sat on a free chair; null when none happened.
export function seatNotice(cues: readonly Cue[], table: Table): SeatNotice | null {
    return openedChairNotice(cues, table) ?? takenChairNotice(cues);
}

// The notice a viewer still reads on a streamed table: it goes as soon as its chair changes hands again.
export function noticeStanding(shown: SeatNotice | null, table: Table): SeatNotice | null {
    const seat = shown?.seat ?? null;
    if (shown === null || seat === null) return shown;
    const occupied = chairAt(table.chairs, seat)?.occupant_name !== null;
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
