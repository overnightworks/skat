<script lang="ts">
    import type { ResultView } from "#lib/result.ts";
    import PointsBar from "#lib/ui/PointsBar.svelte";
    import { words } from "#lib/words.ts";

    import type { Suit } from "../../routes/(start)/tables.ts";

    let { view }: { view: ResultView } = $props();
</script>

{#snippet suitMark(suit: Suit)}
    <span class={`suit ${suit}`} aria-hidden="true">
        <svg viewBox="0 0 100 100"><use href={`#suit-${suit}`} /></svg>
    </span>
{/snippet}

<div class="result" class:lost={!view.good} class:snug={view.snug} role="status">
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
        {#if view.raise !== null}
            <span class="stamp">{words["result.overbid"]}</span>
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
            <div class="reck" class:win={row.won} data-seat={row.seat}>
                <span class="dot" aria-hidden="true">{row.initial}</span>
                <span class="nm">{row.name ?? words["result.seatFree"]}</span>
                <span class="dl" class:minus={row.gain <= 0}>{row.gainText}</span>
            </div>
        {/each}
    </div>
</div>
