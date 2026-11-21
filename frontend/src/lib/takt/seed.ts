import { seriesNumberOf } from "../../routes/(start)/seriesCommands.ts";
import type { Card, Table } from "../../routes/(start)/tables.ts";

/** One labelled stream of draws: a draw depends on the seed, the label and the draws before it in this fork alone. */
export interface Fork {
    /** A number from `low` up to `high`. */
    between(low: number, high: number): number;
    /** Minus one or one, each as likely as the other. */
    sign(): -1 | 1;
}

const HASH_START = 2166136261;
const HASH_PRIME = 16777619;
const DRAW_STEP = 0x6d2b79f5;
const DRAW_RANGE = 4294967296;

/**
 * The seed of the game a table plays: the table, its series and the game's number, which every seat and every watcher
 * reads alike, before and after a reload. It names nothing of the deal.
 */
export function seedOf(table: Pick<Table, "id" | "series">): string {
    return `${table.id}/${String(seriesNumberOf(table))}/${String(table.series?.game_number ?? 0)}`;
}

/**
 * The fork of a seed for one labelled purpose. No draw depends on how many were drawn elsewhere, so views that draw in
 * another order, or leave a draw out, still agree; a label names only what the drawing view shows.
 */
export function fork(seed: string, label: string): Fork {
    let state = HASH_START;
    for (const byte of new TextEncoder().encode(`${seed}/${label}`)) state = Math.imul(state ^ byte, HASH_PRIME);
    const next = (): number => {
        // The state stays within 32 bits by wrapping round, which no rounding does.
        state = (state + DRAW_STEP) >>> 0;
        let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
        mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
        return ((mixed ^ (mixed >>> 14)) >>> 0) / DRAW_RANGE;
    };
    return {
        between: (low, high) => low + (high - low) * next(),
        sign: () => (next() < 0.5 ? -1 : 1),
    };
}

/** The fork of a game's seed for one draw of one card, which every view that shows the card draws alike. */
export function cardFork(seed: string, card: Card, draw: string): Fork {
    return fork(seed, `card/${card.suit}-${card.rank}/${draw}`);
}
