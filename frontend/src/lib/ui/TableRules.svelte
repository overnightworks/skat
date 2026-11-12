<script lang="ts">
    import { bockChip } from "#lib/tableRules.ts";

    import type { Bock } from "../../routes/(start)/tables.ts";

    let { bock }: { bock: Bock | null } = $props();

    const chip = $derived(bockChip(bock));
</script>

{#if chip !== null}
    <div class="rulepill">
        <span class="chip">
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                <rect x="4" y="4" width="16" height="16" rx="4" />
                <circle cx="9" cy="9" r="1.2" fill="currentColor" stroke="none" />
                <circle cx="15" cy="15" r="1.2" fill="currentColor" stroke="none" />
                <circle cx="15" cy="9" r="1.2" fill="currentColor" stroke="none" />
                <circle cx="9" cy="15" r="1.2" fill="currentColor" stroke="none" />
            </svg>
            {chip.word}
            {#if chip.count !== null}
                <b class="n" aria-label={chip.count.label}>{chip.count.number}</b>
            {/if}
        </span>
    </div>
{/if}
