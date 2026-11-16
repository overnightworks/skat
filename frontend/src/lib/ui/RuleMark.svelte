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
    {:else if id === "giveUpPartner"}
        <g stroke-width="1.8">
            <circle cx="9" cy="8" r="3.5" />
            <path
                d="M2.5 19.5c.7-3.4 3.3-5.2 6.5-5.2s5.8 1.8 6.5 5.2M15.8 4.7a3.5 3.5 0 0 1 0 6.6M18 14.6c2 .7 3.2 2.4 3.5 4.9"
            />
        </g>
    {:else if id === "giveUp" || id === "giveUpAnyTime"}
        <g stroke-width="1.8">
            <path d="M5 21V3.5" />
            <path d="M5 4.5c4-2 7 2 11.5 0v8.5c-4.5 2-7.5-2-11.5 0z" fill="currentColor" />
        </g>
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
