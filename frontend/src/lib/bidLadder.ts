import { VALID_BIDS } from "#lib/wire.ts";
import type { Auction, AuctionAction } from "../routes/(start)/tables.ts";

const LOWEST_BID = VALID_BIDS[0];
const PASSIVE_RUNGS = 3;

export type BidLadder =
    | { kind: "passOnly" }
    | {
          kind: "climb";
          held: number | null;
          lit: number;
          rungs: readonly number[];
          // A bidder's rungs are buttons; a responder's only show what lies ahead.
          rungsBid: boolean;
          main: { action: Exclude<AuctionAction, "pass">; value?: number };
      };

function ownLastHold(auction: Auction, viewerSeat: number): number | null {
    const word = auction.words.find(({ seat, action }) => seat === viewerSeat && action === "hold");
    return word?.value ?? null;
}

function bidderLadder(auction: Auction): BidLadder {
    const [lit, ...rungs] = auction.values;
    if (lit === undefined) return { kind: "passOnly" };
    return { kind: "climb", held: auction.standing, lit, rungs, rungsBid: true, main: { action: "bid", value: lit } };
}

function responderLadder(auction: Auction, viewerSeat: number): BidLadder {
    // The server names a standing bid whenever it awaits an answer.
    const standing = auction.standing as number;
    return {
        kind: "climb",
        held: ownLastHold(auction, viewerSeat),
        lit: standing,
        rungs: VALID_BIDS.filter((value) => value > standing).slice(0, PASSIVE_RUNGS),
        rungsBid: false,
        main: { action: "hold" },
    };
}

// Which controls the viewer gets on their own turn, or null when it is not their turn.
export function bidLadder(auction: Auction, viewerSeat: number | undefined): BidLadder | null {
    if (auction.awaiting === null || viewerSeat === undefined || auction.turn_seat !== viewerSeat) return null;
    switch (auction.awaiting) {
        case "bid":
            return bidderLadder(auction);
        case "answer":
            return responderLadder(auction, viewerSeat);
        case "play":
            return { kind: "climb", held: null, lit: LOWEST_BID, rungs: [], rungsBid: false, main: { action: "play" } };
    }
}
