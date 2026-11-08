<script lang="ts">
    import CardBack from "./CardBack.svelte";

    const SPREAD_DEGREES = 6;
    // In the card's own 100 x 140 units: the pivot lies below the card, so the cards open like a held hand.
    const PIVOT_X = 50;
    const PIVOT_Y = 161;

    let { count, dim }: { count: number; dim: boolean } = $props();

    const turns = $derived(Array.from({ length: count }, (_, index) => (index - (count - 1) / 2) * SPREAD_DEGREES));
</script>

<!-- Each card's turn depends on the count and the page's policy allows no inline style, so the fan is one SVG whose
     cards turn by attribute. -->
<svg class="fan" class:dim viewBox="0 0 100 140" aria-hidden="true">
    {#each turns as turn, index (index)}
        <g class="deal">
            <g transform="rotate({turn} {PIVOT_X} {PIVOT_Y})">
                <CardBack />
            </g>
        </g>
    {/each}
</svg>
