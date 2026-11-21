import { handWaits } from "#lib/openChair.ts";
import { VALID_BIDS } from "#lib/wire.ts";
import type { AuctionAction, Awaiting, Game, PlanChoice, PlanMode, Table } from "../routes/(start)/tables.ts";

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

// The bar of a seated player who has not passed, on his turn and off it, or null: without a running auction, while
// the hand waits for a sitter, and for a viewer without a chair.
export function bidBar(table: Table): BidBar | null {
    const auction = table.hand?.auction;
    const viewerSeat = table.chairs.find((chair) => chair.is_mine)?.seat;
    if (auction === undefined || auction.awaiting === null || viewerSeat === undefined) return null;
    if (handWaits(table.hand)) return null;
    if (auction.words.some((word) => word.seat === viewerSeat && word.action === "pass")) return null;
    const { plan, standing, hand_values: reached } = auction;
    const gameAt = (value: number): Game | null => reached.find((each) => each.value === value)?.game ?? null;
    const gone = (value: number): boolean => standing !== null && value < standing;
    const limit =
        plan?.kind === "limit" && plan.value !== null && plan.mode !== null
            ? { value: plan.value, game: gameAt(plan.value), mode: plan.mode }
            : null;
    const handTop = Math.max(...reached.map((each) => each.value));
    const firstOverHand = VALID_BIDS.find((value) => value > handTop);
    const onTurn = auction.turn_seat === viewerSeat;
    return {
        onTurn,
        step: onTurn ? stepOf(auction.awaiting, auction.values) : null,
        chips: reached.map(({ game, value }) => ({ game, value, lit: limit?.value === value, gone: gone(value) })),
        limit,
        passAhead: plan?.kind === "pass",
        asked: onTurn && auction.awaiting !== "play" ? limit : null,
        scale: VALID_BIDS.map((value) => ({
            value,
            game: gameAt(value),
            gone: gone(value),
            standing: value === standing,
            overHand: value > handTop,
            holdHint: value === firstOverHand,
            mine: limit?.value === value,
        })),
    };
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
