<script lang="ts">
    import { pileOf } from "#lib/playView.ts";
    import { currentSettings } from "#lib/settings.svelte.ts";
    import { currentStage, lookAtLastTrick } from "#lib/stage.svelte.ts";
    import CardBack from "#lib/ui/CardBack.svelte";
    import { words } from "#lib/words.ts";
    import type { Playing } from "../../routes/(start)/tables.ts";

    // The tricks a seat has taken lie beside its chair, one back each; only the pile that holds the last trick wears the
    // brass rim, and only it can be tapped to look at that trick again.
    const { seat, playing }: { seat: number; playing: Playing | null } = $props();

    const pile = $derived(playing === null ? null : pileOf(seat, playing, currentStage(), currentSettings().lastTrick));
    const levels = $derived(Array.from({ length: pile?.tricks ?? 0 }, (_, level) => level));
</script>

{#if pile !== null && pile.tricks > 0}
    {#snippet backs()}
        {#each levels as index (index)}
            <span
                class="card"
                class:last={pile.rimmed && index === pile.tricks - 1}
                class:landing={pile.landing && index === pile.tricks - 1}
            >
                <CardBack />
            </span>
        {/each}
    {/snippet}
    {#if pile.rimmed}
        <button
            type="button"
            class="pile last"
            data-seat={seat}
            title={words["play.lastTrick"]}
            aria-label={words["play.lastTrick"]}
            onclick={() => {
                lookAtLastTrick(seat);
            }}
        >
            {@render backs()}
        </button>
    {:else}
        <span class="pile" data-seat={seat} aria-hidden="true">{@render backs()}</span>
    {/if}
{/if}
