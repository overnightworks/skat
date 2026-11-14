<script lang="ts">
    import type { Attachment } from "svelte/attachments";

    import { MOTION_SETS } from "#lib/motionSets.ts";
    import type { ResultView } from "#lib/result.ts";
    import { motionInForce } from "#lib/settings.svelte.ts";
    import Confetti from "#lib/ui/Confetti.svelte";
    import PointsBar from "#lib/ui/PointsBar.svelte";
    import { words } from "#lib/words.ts";

    import type { Suit } from "../../routes/(start)/tables.ts";

    // A card that counts is one that appeared while the page watched; each won gain on it counts up to its value.
    let { view, counts = false }: { view: ResultView; counts?: boolean } = $props();

    // A won result that appeared while the page watched throws the confetti of the motion set in force, if it has any.
    const motion = $derived(motionInForce());
    const pieces = $derived(counts && view.good && motion !== undefined ? MOTION_SETS[motion].confettiPieces : 0);

    // The stylesheet's count reads its target from the element, set as a property so no style attribute carries it.
    function countTo(gain: number): Attachment<HTMLElement> {
        return (element) => {
            element.style.setProperty("--to", String(gain));
        };
    }
</script>

{#snippet suitMark(suit: Suit)}
    <span class={`suit ${suit}`} aria-hidden="true">
        <svg viewBox="0 0 100 100"><use href={`#suit-${suit}`} /></svg>
    </span>
{/snippet}

<div class="result" class:fresh={counts} class:lost={!view.good} class:snug={view.snug} role="status">
    <h3>
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="3"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            {#if view.good}
                <path d="M5 12.5l4.5 4.5L19 7" />
            {:else}
                <path d="M6 6l12 12M18 6L6 18" />
            {/if}
        </svg>
        <span>{view.word}</span>
    </h3>
    {#if view.missed !== null}
        <div class="miss missed">{view.missed}</div>
    {/if}
    <div class="sub">
        <span class="game">
            {#if view.suit !== null}
                {@render suitMark(view.suit)}
            {/if}
            <span>{view.gameLine}</span>
        </span>
        {#if view.stamp !== null}
            <span class="stamp">
                {#if view.stamp.face !== null}
                    <span class="by" aria-hidden="true">{view.stamp.face}</span>
                {/if}
                {view.stamp.word}
            </span>
        {/if}
    </div>
    {#if view.chips.length > 0}
        <div class="ladder" role="list">
            {#each view.chips as chip (chip.word)}
                <span role="listitem" class={chip.ticked ? "held" : "held mit"}>
                    {#if chip.ticked}
                        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                    {/if}
                    <span>{chip.word}</span>
                </span>
            {/each}
        </div>
    {/if}
    {#if view.equation !== null}
        <div class="eq">
            {#if view.equation.multiplier !== null}
                <span>{view.equation.multiplier}</span>
                <i>×</i>
            {/if}
            {#if view.suit !== null}
                {@render suitMark(view.suit)}
            {:else}
                <span>{view.gameWord}</span>
            {/if}
            {#if view.equation.base !== null}
                <span>{view.equation.base}</span>
            {/if}
            {#if view.equation.product !== null}
                <i>=</i>
                <b>{view.equation.product}</b>
            {/if}
        </div>
    {/if}
    {#if view.raise !== null}
        <div class="miss">{view.raise}</div>
    {/if}
    {#if view.doublings.length > 0}
        <div class="ladder" role="list">
            {#each view.doublings as doubling (doubling)}
                <span role="listitem" class="held">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                    <span>{doubling}</span>
                </span>
            {/each}
        </div>
    {/if}
    <div class="value-row">
        {#if view.doubled}
            <span class="x2">×2</span>
        {/if}
        <div class="value" class:minus={view.doubled}>{view.score}</div>
    </div>
    <div class="list">
        <b>{view.list.side}</b>
        {#each view.list.steps as step (step)}
            <span>{step}</span>
        {/each}
        {#if view.list.share !== null}
            <span>{view.list.share}</span>
        {/if}
    </div>
    {#if view.points !== null}
        <PointsBar sides={view.sides} points={view.points} />
    {/if}
    <div class="coasters">
        {#each view.rows as row (row.seat)}
            {@const counting = counts && row.gain > 0}
            <div class="reck" class:win={row.won} data-seat={row.seat}>
                <span class="dot" aria-hidden="true">{row.initial}</span>
                <span class="nm">{row.name ?? words["result.seatFree"]}</span>
                <span
                    class="dl"
                    class:minus={row.gain <= 0}
                    class:count={counting}
                    {@attach counting ? countTo(row.gain) : undefined}>{row.gainText}</span
                >
            </div>
        {/each}
    </div>
</div>
{#if pieces > 0}
    <Confetti count={pieces} />
{/if}
