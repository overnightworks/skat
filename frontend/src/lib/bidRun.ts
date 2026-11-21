import type { BidSaid } from "./cues.ts";
import type { ToldWord } from "./takt/bids.ts";
import { seedOf } from "./takt/seed.ts";
import type { Auction, AuctionWord, Table } from "../routes/(start)/tables.ts";

/**
 * The words one update brought to an auction, which the table tells one after another: the seed of their game, each
 * word with its number in the auction, and the table as it stands after each word but the last, whose table is the one
 * the update brought.
 */
export interface BidRun {
    readonly seed: string;
    readonly words: readonly ToldWord[];
    readonly tables: readonly Table[];
}

// The auction of the table before a run once `steps` were said: each chair's latest word and the bid that stands. The
// turn and the duel stay as they were, since only the table the update brought tells whom the auction awaits then.
function auctionAfter(auction: Auction, steps: AuctionWord[]): Auction {
    const bid = steps.filter((word) => word.action === "bid").at(-1);
    return {
        ...auction,
        steps,
        words: [...new Map(steps.map((word) => [word.seat, word])).values()],
        standing: bid?.value ?? auction.standing,
    };
}

/**
 * The run of the words `said` between two tables of one hand, or null: one word is no run, and neither are words this
 * page cannot count on from the ones it has seen.
 */
export function bidRunBetween(previous: Table, next: Table, said: readonly BidSaid[]): BidRun | null {
    const before = previous.hand;
    const after = next.hand;
    if (said.length < 2 || before === null || after === null) return null;
    if (after.dealer_seat !== before.dealer_seat) return null;
    const seen = before.auction.steps.length;
    const words = after.auction.steps.flatMap((word, step): ToldWord[] =>
        step < seen || word.action === "play" ? [] : [{ step, action: word.action }],
    );
    if (words.length !== said.length) return null;
    return {
        seed: seedOf(next),
        words,
        tables: words.slice(0, -1).map(({ step }) => ({
            ...previous,
            version: next.version,
            hand: { ...before, auction: auctionAfter(before.auction, after.auction.steps.slice(0, step + 1)) },
        })),
    };
}
