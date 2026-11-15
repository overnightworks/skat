import { isSuitGame, type Card, type Game, type Rank, type Suit } from "../routes/(start)/tables.ts";

const SUIT_ORDER: readonly Suit[] = ["kreuz", "pik", "herz", "karo"];
const RANK_ORDER_IN_SUIT: readonly Rank[] = ["ace", "ten", "king", "queen", "nine", "eight", "seven"];
const RANK_ORDER_IN_NULL: readonly Rank[] = ["ace", "king", "queen", "jack", "ten", "nine", "eight", "seven"];

// A suit game shows its trump suit before the other suits, which keep their order.
function suitsFor(game: Game | null): readonly Suit[] {
    if (game === null || !isSuitGame(game)) return SUIT_ORDER;
    return [game, ...SUIT_ORDER.filter((suit) => suit !== game)];
}

function displayPosition({ suit, rank }: Card, game: Game | null): number {
    const suits = suitsFor(game);
    if (game === "null") return suits.indexOf(suit) * RANK_ORDER_IN_NULL.length + RANK_ORDER_IN_NULL.indexOf(rank);
    if (rank === "jack") return SUIT_ORDER.indexOf(suit);
    return SUIT_ORDER.length + suits.indexOf(suit) * RANK_ORDER_IN_SUIT.length + RANK_ORDER_IN_SUIT.indexOf(rank);
}

// How the picture shows a hand, not a rule of play: the table's game when it is known, null before.
export function inDisplayOrder(cards: readonly Card[], game: Game | null): Card[] {
    return [...cards].sort((first, second) => displayPosition(first, game) - displayPosition(second, game));
}
