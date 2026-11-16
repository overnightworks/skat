import { POSITION_TOKENS } from "#lib/wire.ts";
import type { Chair, ChairHand } from "../routes/(start)/tables.ts";

// The turn goes forehand, middlehand, rearhand and round again; while a hand runs every chair holds a position.
export function seatsInTurnFrom(chairs: readonly Chair[], leaderSeat: number): number[] {
    const turnOf = new Map(
        chairs.map((chair) => [chair.seat, POSITION_TOKENS.indexOf((chair.hand as ChairHand).position)]),
    );
    const lead = turnOf.get(leaderSeat) as number;
    const turnsAfterLead = (seat: number): number =>
        ((turnOf.get(seat) as number) - lead + POSITION_TOKENS.length) % POSITION_TOKENS.length;
    return chairs.map((chair) => chair.seat).sort((first, second) => turnsAfterLead(first) - turnsAfterLead(second));
}
