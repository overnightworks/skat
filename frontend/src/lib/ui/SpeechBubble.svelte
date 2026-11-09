<script lang="ts">
    import type { Bubble } from "#lib/auctionMarks.ts";

    const { bubble, initial }: { bubble: Bubble; initial: string } = $props();
</script>

<span class="bubble" class:quiet={bubble.kind === "hold"}>
    <span class="dot" aria-hidden="true">{initial}</span>
    {#if bubble.kind === "hold"}
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
    {/if}
    <span class="said">{bubble.value}</span>
</span>
