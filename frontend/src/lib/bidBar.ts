import { hasPassed } from "#lib/auctionMarks.ts";
import { handWaits } from "#lib/openChair.ts";
import { VALID_BIDS } from "#lib/wire.ts";
import type {
    Auction,
    AuctionAction,
    Awaiting,
    Game,
    PlanChoice,
    PlanKind,
    PlanMode,
    Table,
} from "../routes/(start)/tables.ts";

const LOWEST_BID = VALID_BIDS[0];

// What a blue key says now: `says` is the number it shows, which the hold lacks, whose word is „Ja“.
export type BidStep = { action: Exclude<AuctionAction, "pass">; value?: number; says?: number };
export type BidLimit = { value: number; game: Game | null; mode: PlanMode };
export type BidChip = { game: Game; value: number; lit: boolean; gone: boolean };
// A value of the whole scale: `gone` lies below the standing bid and `overHand` above everything his cards reach,
// where a pick takes a hold, which the first such value says.
export type ScaleValue = {
    value: number;
    game: Game | null;
    gone: boolean;
    standing: boolean;
    overHand: boolean;
    holdHint: boolean;
    mine: boolean;
};
export type BidBar = {
    onTurn: boolean;
    // Null off his turn and at the ladder's top, where only „Weg“ is left.
    step: BidStep | null;
    chips: BidChip[];
    limit: BidLimit | null;
    passAhead: boolean;
    // His ask limit while the table awaits him above it.
    asked: BidLimit | null;
    scale: ScaleValue[];
};

function stepOf(awaiting: Awaiting, [next]: number[]): BidStep | null {
    switch (awaiting) {
        case "bid":
            return next === undefined ? null : { action: "bid", value: next, says: next };
        case "answer":
            return { action: "hold" };
        case "play":
            return { action: "play", says: LOWEST_BID };
    }
}

type Part = { auction: Auction; awaiting: Awaiting; seat: number; passed: boolean };

// A seated viewer's part in a running auction, or null: without a running auction, while the hand waits for a sitter,
// and for a viewer without a chair.
function partIn(table: Table): Part | null {
    const auction = table.hand?.auction;
    const seat = table.chairs.find((chair) => chair.is_mine)?.seat;
    if (auction === undefined || auction.awaiting === null || seat === undefined) return null;
    if (handWaits(table.hand)) return null;
    return { auction, awaiting: auction.awaiting, seat, passed: hasPassed(auction, seat) };
}

function gameAt({ hand_values: reached }: Auction, value: number): Game | null {
    return reached.find((each) => each.value === value)?.game ?? null;
}

function limitOf(auction: Auction): BidLimit | null {
    const { plan } = auction;
    if (plan?.kind !== "limit" || plan.value === null || plan.mode === null) return null;
    return { value: plan.value, game: gameAt(auction, plan.value), mode: plan.mode };
}

// The bar of a seated player who has not passed, on his turn and off it.
export function bidBar(table: Table): BidBar | null {
    const part = partIn(table);
    if (part === null || part.passed) return null;
    const { auction, awaiting, seat } = part;
    const { plan, standing, hand_values: reached } = auction;
    const gone = (value: number): boolean => standing !== null && value < standing;
    const limit = limitOf(auction);
    const handTop = Math.max(...reached.map((each) => each.value));
    const firstOverHand = VALID_BIDS.find((value) => value > handTop);
    const onTurn = auction.turn_seat === seat;
    return {
        onTurn,
        step: onTurn ? stepOf(awaiting, auction.values) : null,
        chips: reached.map(({ game, value }) => ({ game, value, lit: limit?.value === value, gone: gone(value) })),
        limit,
        passAhead: plan?.kind === "pass",
        asked: onTurn && awaiting !== "play" ? limit : null,
        scale: VALID_BIDS.map((value) => ({
            value,
            game: gameAt(auction, value),
            gone: gone(value),
            standing: value === standing,
            overHand: value > handTop,
            holdHint: value === firstOverHand,
            mine: limit?.value === value,
        })),
    };
}

// His fixed limit once the table said „Weg“ for him above it, which stays in his sight while the auction runs.
export function passedLimit(table: Table): BidLimit | null {
    const part = partIn(table);
    if (!part?.passed) return null;
    const limit = limitOf(part.auction);
    return limit?.mode === "fixed" ? limit : null;
}

// A limit at `value` keeps the mode he chose before; his first limit asks.
export function limitAt(bar: BidBar, value: number): PlanChoice {
    return { kind: "limit", value, mode: bar.limit?.mode ?? "ask" };
}

// A tap on a chip sets its value as his limit, and a tap on the lit chip takes the limit back.
export function chipTap(bar: BidBar, value: number): PlanChoice {
    return bar.limit?.value === value ? null : limitAt(bar, value);
}

// „Weg“ off his turn says it ahead, and a second tap takes it back.
export function passAheadTap(bar: BidBar): PlanChoice {
    return bar.passAhead ? null : { kind: "pass" };
}

// The plan a tap takes back, which its line says for a moment; a tap that sets a plan takes none back.
export function takenBack(table: Table, choice: PlanChoice): PlanKind | null {
    return choice === null ? (table.hand?.auction.plan?.kind ?? null) : null;
}

// The value he picked on the scale, until the auction has passed it.
export function livePick(bar: BidBar, picked: number | null): number | null {
    return bar.scale.some((each) => each.value === picked && !each.gone) ? picked : null;
}

// What the blue key says with a value picked on the scale: a bidder says the picked value at once, which is the jump;
// a responder's answer and forehand's 18 stay as they are.
export function stepWith(bar: BidBar, pick: number | null): BidStep | null {
    const { step } = bar;
    if (pick === null || step?.action !== "bid" || step.value === undefined || pick < step.value) return step;
    return { action: "bid", value: pick, says: pick };
}
