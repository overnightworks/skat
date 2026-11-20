<script lang="ts">
    import { isFramedInCallMode } from "#lib/callFrame.ts";
    import { closedStandings, closedWords } from "#lib/closed.ts";
    import CardBack from "#lib/ui/CardBack.svelte";
    import Standings from "#lib/ui/Standings.svelte";
    import { CHAIRS_PER_TABLE } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";
    import NewTableButton from "../../NewTableButton.svelte";
    import type { Ended } from "../../tables.ts";
    import ClosedGames from "./ClosedGames.svelte";

    // The face of a table that ended, or, with no `ended`, of a link whose table is gone. A table that finished a game
    // shows its standings and games and names no reason; one that finished none says why it ended.
    const CHAIR_SEATS = Array.from({ length: CHAIRS_PER_TABLE }, (_, seat) => seat);

    let { ended }: { ended: Ended | null } = $props();

    // A closed table shows its closer's initial where the other faces draw their sign.
    const closer = $derived(ended?.reason === "closed" ? ended.closed_by_name : null);
    const standings = $derived(ended === null ? null : closedStandings(ended));
</script>

{#if ended === null}
    <div class="back-spot" aria-hidden="true">
        <CardBack />
    </div>
{:else}
    <div class="felt-paint" aria-hidden="true"></div>
    <div class="felt" aria-hidden="true"></div>
    <ul class="chairs emptied" aria-hidden="true">
        {#each CHAIR_SEATS as seat (seat)}
            <li class="chair"><span class="tile empty"></span></li>
        {/each}
    </ul>
{/if}
{#if standings !== null}
    <Standings view={standings} closed>
        <ClosedGames />
        {#if !isFramedInCallMode()}
            <NewTableButton />
        {/if}
    </Standings>
{:else}
    <section class="closed" class:missing={ended === null} role="status">
        <span class="glyph" class:by={closer !== null} aria-hidden="true">
            {#if closer !== null}
                {closer.slice(0, 1)}
            {:else}
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
            {/if}
        </span>
        <h1>{ended === null ? words["closed.notFound"] : closedWords(ended)}</h1>
        {#if !isFramedInCallMode()}
            <NewTableButton />
        {/if}
    </section>
{/if}
