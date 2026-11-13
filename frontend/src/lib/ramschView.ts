import { handWaits } from "#lib/openChair.ts";
import { words } from "#lib/words.ts";
import type { Chair, Playing, Pushing, Table } from "../routes/(start)/tables.ts";

// What the plaque of a Ramsch adds to its name: the pushes with the factor the answer sends, who acts while the stage
// runs, and whether the hand waits for a player to sit down.
export type RamschPlaque = { pushes: string | null; factor: string | null; acting: string | null; waiting: boolean };
export type RamschMarks = { turn: boolean; thinks: boolean; pushed: boolean };

function chairOf(chairs: readonly Chair[], seat: number): Chair {
    // A chair of a running hand is occupied, unless the hand waits for it; no caller asks for that one then.
    return chairs.find((chair) => chair.seat === seat) as Chair;
}

function actingWords(chairs: readonly Chair[], stage: Pushing): string {
    const sentence = stage.stage === "choosing" ? words["table.chooses"] : words["table.discards"];
    return sentence({ name: chairOf(chairs, stage.turn_seat).occupant_name as string });
}

// The plaque of the Ramsch a hand plays, from its third pass to its result; the factor is read from the answer.
export function ramschPlaque(table: Table): RamschPlaque | null {
    const hand = table.hand;
    if (!hand?.ramsch) return null;
    const waiting = handWaits(hand);
    const stage = hand.pushing;
    const ownSeat = table.chairs.find((chair) => chair.is_mine)?.seat;
    const acting = waiting || stage === null || stage.turn_seat === ownSeat ? null : actingWords(table.chairs, stage);
    return {
        pushes: hand.pushes === 0 ? null : words["table.pushCount"]({ count: hand.pushes }),
        factor: hand.push_factor === 1 ? null : words["table.pushFactor"]({ factor: String(hand.push_factor) }),
        acting,
        waiting,
    };
}

// What one chair carries in a Ramsch: the turn mark on the seat the stage or the play waits for, „denkt“ on an agent
// that is on turn in the stage, and the bubble „Schieben“ on a seat that pushed. No chair is on turn while one is open.
export function ramschMarks(table: Table, seat: number): RamschMarks {
    const hand = table.hand;
    if (!hand?.ramsch) return { turn: false, thinks: false, pushed: false };
    const stage = hand.pushing;
    const turnSeat = handWaits(hand) ? null : (stage?.turn_seat ?? hand.playing?.turn_seat);
    const turn = turnSeat === seat;
    return {
        turn,
        thinks: turn && stage !== null && chairOf(table.chairs, seat).occupant_kind === "agent",
        pushed: stage?.moves.some((move) => move.seat === seat && move.action === "pushed") ?? false,
    };
}

// The play of a Ramsch, whose trick lies in the middle like any game's; a stage and a declared game have none.
export function ramschTrick(table: Table): Playing | null {
    return table.hand?.ramsch ? table.hand.playing : null;
}
