<script lang="ts">
    import type { ChipId, RuleId } from "#lib/tableRules.ts";

    let { id }: { id: ChipId | RuleId } = $props();
</script>

<svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2.2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
>
    {#if id === "points"}
        <path d="M18 5H6l6 7-6 7h12" />
    {:else if id === "kontra"}
        <path d="M13 3L5 14h6l-1 7 8-11h-6z" />
    {:else if id === "ramsch"}
        <path d="M12 4v10M7 10l5 5 5-5M5 20h14" />
    {:else if id === "pushing"}
        <path d="M4 12h14M13 6l6 6-6 6" />
    {:else if id === "bock"}
        <g stroke-width="1.8">
            <rect x="4" y="4" width="16" height="16" rx="4" />
            <circle cx="9" cy="9" r="1.2" fill="currentColor" stroke="none" />
            <circle cx="15" cy="15" r="1.2" fill="currentColor" stroke="none" />
            <circle cx="15" cy="9" r="1.2" fill="currentColor" stroke="none" />
            <circle cx="9" cy="15" r="1.2" fill="currentColor" stroke="none" />
        </g>
    {:else}
        <path d="M5 12.5l4.5 4.5L19 7.5" />
    {/if}
</svg>
