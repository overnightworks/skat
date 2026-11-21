<script lang="ts">
    import { awayOnTurn, type PassedInScene } from "#lib/auctionMarks.ts";
    import AuctionCounter from "#lib/ui/AuctionCounter.svelte";
    import WaitingLine from "#lib/ui/WaitingLine.svelte";
    import { words } from "#lib/words.ts";
    import type { Table } from "../../routes/(start)/tables.ts";

    // What stands over a table whose hand has no declarer yet: the counter of the auction while it runs, or the plaque
    // that waits for players, for a sitter or for an away chair, or tells the pass-in's verdict.
    const { table, passedIn, waits }: { table: Table; passedIn: PassedInScene | null; waits: boolean } = $props();
    const awayName = $derived(table.hand && awayOnTurn(table.hand.auction, table.chairs));
    const running = $derived(
        passedIn === null && table.aborted === null && !waits && !awayName ? table.hand?.auction : undefined,
    );
</script>

{#if running !== undefined}
    <AuctionCounter auction={running} chairs={table.chairs} />
{:else}
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
            <WaitingLine />
        {:else if table.hand === null}
            <span>{words["table.waitingForPlayers"]}</span>
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        {:else if awayName && !waits}
            <span>{words["table.waitingFor"]({ names: awayName })}</span>
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        {:else}
            <span>{words["table.bidding"]}</span>
            <WaitingLine />
        {/if}
    </div>
{/if}
