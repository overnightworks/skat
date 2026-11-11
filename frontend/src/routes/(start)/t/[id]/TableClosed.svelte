<script lang="ts">
    import { isFramedInCallMode } from "#lib/callFrame.ts";
    import { closedWords } from "#lib/closed.ts";
    import CardBack from "#lib/ui/CardBack.svelte";
    import { CHAIRS_PER_TABLE } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";
    import NewTableButton from "../../NewTableButton.svelte";
    import type { Ended } from "../../tables.ts";

    // The face of a table that ended, or, with no `ended`, of a link whose table is gone.
    const CHAIR_SEATS = Array.from({ length: CHAIRS_PER_TABLE }, (_, seat) => seat);

    let { ended }: { ended: Ended | null } = $props();
</script>

{#if ended === null}
    <div class="back-spot" aria-hidden="true">
        <CardBack />
    </div>
{:else}
    <div class="felt" aria-hidden="true"></div>
    <ul class="chairs emptied" aria-hidden="true">
        {#each CHAIR_SEATS as seat (seat)}
            <li class="chair"><span class="tile empty"></span></li>
        {/each}
    </ul>
{/if}
<section class="closed" class:missing={ended === null} role="status">
    <span class="glyph" aria-hidden="true">
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
        >
            {#if ended === null}
                <path d="M9.2 9.2a2.9 2.9 0 1 1 4 2.7c-.7.3-1.2.9-1.2 1.6v.8" />
                <circle cx="12" cy="18" r="1" fill="currentColor" stroke="none" />
            {:else}
                <circle cx="12" cy="12" r="8.5" />
                <path d="M12 7.5V12l3 2" />
            {/if}
        </svg>
    </span>
    <h1>{ended === null ? words["closed.notFound"] : closedWords(ended)}</h1>
    {#if !isFramedInCallMode()}
        <NewTableButton />
    {/if}
</section>
