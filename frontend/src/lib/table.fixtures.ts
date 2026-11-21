import type { Auction } from "../routes/(start)/tables.ts";

// The id the page tests give their table; a table id is 32 lowercase hexadecimal characters.
export const TABLE_ID = "a".repeat(32);

// An auction that is over and tells nothing, with what a test is about.
export function auctionWith(changes: Partial<Auction> = {}): Auction {
    return {
        turn_seat: null,
        facing_seat: null,
        awaiting: null,
        standing: null,
        values: [],
        words: [],
        steps: [],
        declared: null,
        plan: null,
        hand_values: [],
        ...changes,
    };
}
