<script lang="ts">
    import type { DecidingPlaque } from "#lib/auctionMarks.ts";

    const { deciding }: { deciding: DecidingPlaque } = $props();
</script>

<div class="plaque deciding">
    {#if deciding.kind === "won"}
        <span>{deciding.text}</span>
    {:else}
        <span>{deciding.bid}</span>
        <span class="gives">
            {deciding.line}
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        </span>
    {/if}
</div>
