<script lang="ts">
    import type { Seal } from "#lib/closingHand.ts";

    // The seal on the card that took a hand's deciding trick: gold with a check when the declarer won, red with a cross
    // when he lost. It says nothing alone: the result that follows it, or carries it, says the outcome in words.
    const { seal }: { seal: Seal } = $props();
</script>

<span class={["seal", seal]} aria-hidden="true">
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="3.2"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <path d={seal === "won" ? "M5 12.5l4.5 4.5L19 7.5" : "M7 7l10 10M17 7L7 17"} />
    </svg>
</span>
