<script lang="ts">
    import type { Card, Rank, Suit } from "../../routes/(start)/tables.ts";
    import { words } from "#lib/words.ts";

    type NumeralRank = Exclude<Rank, "ace" | "jack" | "queen" | "king">;

    const SUIT_FILL: Record<Suit, string> = { kreuz: "#17191c", pik: "#14873f", herz: "#d81f35", karo: "#ec9800" };
    // The letter of a Karo card is darker than its symbol, so it stays readable on the cream face.
    const SUIT_INK: Record<Suit, string> = { kreuz: "#17191c", pik: "#14873f", herz: "#d81f35", karo: "#d58300" };
    const COURT_GOLD = "#b8893a";

    const RANK_LETTERS: Record<Rank, string> = {
        seven: "7",
        eight: "8",
        nine: "9",
        ten: "10",
        jack: words["card.letterJack"],
        queen: words["card.letterQueen"],
        king: words["card.letterKing"],
        ace: words["card.letterAce"],
    };

    const LEFT = 34;
    const CENTRE = 50;
    const RIGHT = 66;
    const THREE_ROWS = [28, 70, 112];
    const FOUR_ROWS = [28, 56, 84, 112];
    const CARD_MIDDLE = 70;

    function onBothSides(rows: number[]): [number, number][] {
        return [...rows.map((y): [number, number] => [LEFT, y]), ...rows.map((y): [number, number] => [RIGHT, y])];
    }

    const PIPS: Record<NumeralRank, [number, number][]> = {
        seven: [...onBothSides(THREE_ROWS), [CENTRE, 49]],
        eight: [...onBothSides(THREE_ROWS), [CENTRE, 49], [CENTRE, 91]],
        nine: [...onBothSides(FOUR_ROWS), [CENTRE, CARD_MIDDLE]],
        ten: [...onBothSides(FOUR_ROWS), [CENTRE, 42], [CENTRE, 98]],
    };
    const PIP_RADIUS = 9;

    const { card }: { card: Card } = $props();

    const symbol = $derived(`#suit-${card.suit}`);
    const court = $derived(`#court-${card.rank}`);
    const fill = $derived(SUIT_FILL[card.suit]);
    const ink = $derived(SUIT_INK[card.suit]);
    const letter = $derived(RANK_LETTERS[card.rank]);
</script>

{#snippet corner()}
    <text class="index" class:ten={card.rank === "ten"} x="12" y="24" text-anchor="middle" fill={ink}>{letter}</text>
    <use href={symbol} x="5" y="28" width="14" height="14" {fill} />
{/snippet}

<svg class="card-face" viewBox="0 0 100 140" aria-hidden="true" data-suit={card.suit} data-rank={card.rank}>
    <rect
        x=".75"
        y=".75"
        width="98.5"
        height="138.5"
        rx="7"
        fill="url(#card-fill)"
        stroke="#cfc6b1"
        stroke-width="1.5"
    />
    {@render corner()}
    <g transform="rotate(180 50 70)">{@render corner()}</g>
    {#if card.rank === "ace"}
        <circle cx="50" cy={CARD_MIDDLE} r="31" fill="none" stroke={fill} stroke-opacity=".22" stroke-width="1.4" />
        <use href={symbol} x="27" y="47" width="46" height="46" {fill} />
    {:else if card.rank === "jack" || card.rank === "queen" || card.rank === "king"}
        <rect
            x="22"
            y="18"
            width="56"
            height="104"
            rx="5"
            fill="url(#court-fill)"
            stroke={COURT_GOLD}
            stroke-width="1.3"
        />
        <rect
            x="25.5"
            y="21.5"
            width="49"
            height="97"
            rx="3"
            fill="none"
            stroke={COURT_GOLD}
            stroke-opacity=".5"
            stroke-width=".8"
        />
        <use href={court} x="32" y="28" width="36" height="25" fill={COURT_GOLD} />
        <text class="court" x="50" y="91" text-anchor="middle" fill={ink}>{letter}</text>
        <use href={symbol} x="40.5" y="97" width="19" height="19" {fill} />
    {:else}
        {#each PIPS[card.rank] as [x, y], pip (pip)}
            <use
                href={symbol}
                x={x - PIP_RADIUS}
                y={y - PIP_RADIUS}
                width={PIP_RADIUS * 2}
                height={PIP_RADIUS * 2}
                {fill}
                transform={y > CARD_MIDDLE ? `rotate(180 ${String(x)} ${String(y)})` : undefined}
            />
        {/each}
    {/if}
</svg>
