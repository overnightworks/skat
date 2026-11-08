import type { Card, Rank, Suit } from "../routes/(start)/tables.ts";

const SUIT_ORDER: readonly Suit[] = ["kreuz", "pik", "herz", "karo"];
const RANK_ORDER_IN_SUIT: readonly Rank[] = ["ace", "ten", "king", "queen", "nine", "eight", "seven"];

function displayPosition({ suit, rank }: Card): number {
    const suitPosition = SUIT_ORDER.indexOf(suit);
    if (rank === "jack") return suitPosition;
    return SUIT_ORDER.length + suitPosition * RANK_ORDER_IN_SUIT.length + RANK_ORDER_IN_SUIT.indexOf(rank);
}

// One fixed order, since no game is chosen yet: it is how the picture shows a hand, not a rule of play.
export function inDisplayOrder(cards: readonly Card[]): Card[] {
    return [...cards].sort((first, second) => displayPosition(first) - displayPosition(second));
}
