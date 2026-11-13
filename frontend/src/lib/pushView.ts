import { includesCard, type Card, type Picking, type Stage, type Table } from "../routes/(start)/tables.ts";
import { handWaits } from "#lib/openChair.ts";

export type PushStage = Extract<Stage, "choosing" | "discarding">;

// The step this viewer takes in the stage before a Ramsch: only the seat on turn acts, and not while a chair is open.
export function pushStage(table: Table): PushStage | null {
    const stage = table.hand?.pushing;
    if (!stage || (stage.stage !== "choosing" && stage.stage !== "discarding") || handWaits(table.hand)) return null;
    const mine = table.chairs.some((chair) => chair.is_mine && chair.seat === stage.turn_seat);
    return mine ? stage.stage : null;
}

// A card the picking hand names as not allowed stays dim and cannot be picked.
export function mayPick(picking: Picking, card: Card): boolean {
    return picking.allowed === undefined || includesCard(picking.allowed, card);
}
