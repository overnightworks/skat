<script lang="ts">
    import type { Snippet } from "svelte";
    import { awayOnTurn, type PassedInScene } from "#lib/auctionMarks.ts";
    import { words } from "#lib/words.ts";
    import type { Table } from "../../routes/(start)/tables.ts";

    // The plaque of a table whose hand has no declarer yet: waiting for players, for an away chair, for a bid, or the
    // pass-in's verdict.
    const {
        table,
        passedIn,
        waits,
        waitingLine,
    }: { table: Table; passedIn: PassedInScene | null; waits: boolean; waitingLine: Snippet } = $props();
    const awayName = $derived(table.hand && awayOnTurn(table.hand.auction, table.chairs));
</script>

<div class="plaque" class:hand-over={passedIn !== null} class:deciding={waits || table.aborted !== null}>
    {#if passedIn !== null}
        <span class="verdict">{words["table.passedIn"]}</span>
        {#if passedIn.dealerLine !== null}
            <span class="gives">
                {passedIn.dealerLine}
                <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
            </span>
        {/if}
    {:else if table.aborted !== null}
        <span>{words["table.aborted"]}</span>
        {@render waitingLine()}
    {:else if table.hand === null}
        <span>{words["table.waitingForPlayers"]}</span>
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
    {:else if awayName && !waits}
        <span>{words["table.waitingFor"]({ names: awayName })}</span>
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
    {:else}
        <span>{words["table.bidding"]}</span>
        {#if waits}
            {@render waitingLine()}
        {/if}
    {/if}
</div>
