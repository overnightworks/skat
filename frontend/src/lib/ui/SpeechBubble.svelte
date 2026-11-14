<script lang="ts">
    import type { Bubble } from "#lib/auctionMarks.ts";

    // A bubble springs up when this page saw its bid said; the table already showing it stands still.
    const { bubble, initial, fresh }: { bubble: Bubble; initial: string; fresh: boolean } = $props();
</script>

<span class="bubble" class:quiet={bubble.kind === "hold"} class:fresh>
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
