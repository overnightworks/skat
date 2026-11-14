<script module lang="ts">
    import type { Suit } from "../../routes/(start)/tables.ts";

    const SUITS: readonly Suit[] = ["kreuz", "pik", "herz", "karo"];

    export interface Piece {
        readonly suit: Suit;
        /** Where the piece lands and where it starts, in percent of the table's width and height. */
        readonly x: number;
        readonly y: number;
        readonly fromX: number;
        readonly fromY: number;
        readonly size: number;
        readonly turn: number;
        readonly drift: number;
        readonly delay: number;
    }

    // The burst starts at the own chair, at the bottom middle of the table.
    const ORIGIN_X = 50;
    const ORIGIN_Y = 96;
    const FIRST_SEED = 7;
    const SEED_MULTIPLIER = 16807;
    const SEED_MODULUS = 2147483647;

    /** The same burst on every render: the pieces come from a seeded sequence, a suit each in turn. */
    export function piecesOf(count: number): Piece[] {
        let seed = FIRST_SEED;
        const next = (): number => {
            seed = (seed * SEED_MULTIPLIER) % SEED_MODULUS;
            return seed / SEED_MODULUS;
        };
        return Array.from({ length: count }, (_, index) => {
            const x = 6 + next() * 88;
            const y = 8 + next() * 60;
            return {
                suit: SUITS[index % SUITS.length] as Suit,
                x,
                y,
                fromX: ORIGIN_X - x,
                fromY: ORIGIN_Y - y,
                size: 12 + Math.round(next() * 6),
                turn: Math.round(next() * 80 - 40),
                drift: Math.round(next() * 40 - 20),
                delay: Math.round(next() * 35) / 100,
            };
        });
    }
</script>

<script lang="ts">
    import type { Attachment } from "svelte/attachments";

    const { count }: { count: number } = $props();

    // The stylesheet reads each piece's place and pace from its element, set as properties so no style attribute carries them.
    function placed(piece: Piece): Attachment<HTMLElement> {
        return (element) => {
            const properties: Record<string, number> = {
                "--x": piece.x,
                "--y": piece.y,
                "--from-x": piece.fromX,
                "--from-y": piece.fromY,
                "--size": piece.size,
                "--turn": piece.turn,
                "--drift": piece.drift,
                "--delay": piece.delay,
            };
            for (const [name, value] of Object.entries(properties)) element.style.setProperty(name, String(value));
        };
    }
</script>

<div class="confetti" aria-hidden="true">
    {#each piecesOf(count) as piece, index (index)}
        <i class={piece.suit} {@attach placed(piece)}>
            <svg viewBox="0 0 100 100"><use href={`#suit-${piece.suit}`} /></svg>
        </i>
    {/each}
</div>
