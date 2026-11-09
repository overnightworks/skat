<script lang="ts">
    import type { ResultView } from "#lib/result.ts";
    import { ALL_POINTS } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";

    let { view }: { view: ResultView } = $props();
</script>

<div class="result" class:lost={!view.good} role="status">
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
    <div class="sub">
        <span class="game">
            {#if view.suit !== null}
                <span class={`suit ${view.suit}`} aria-hidden="true">
                    <svg viewBox="0 0 100 100"><use href={`#suit-${view.suit}`} /></svg>
                </span>
            {/if}
            <span>{view.gameLine}</span>
        </span>
        {#if view.miss !== null}
            <span class="stamp">{words.overbid}</span>
        {/if}
    </div>
    {#if view.score !== null}
        <div class="value" class:minus={!view.good}>{view.score}</div>
    {/if}
    {#if view.miss !== null}
        <div class="miss">{view.miss}</div>
    {/if}
    <div class="points" role="group" aria-label={words.trickPoints}>
        <span class="sides">
            <span class="declarer">{`${view.sides.declarer} ${String(view.points.declarer)}`}</span>
            <span class="opponents">{`${view.sides.opponents} ${String(view.points.opponents)}`}</span>
        </span>
        <span class="track">
            <svg viewBox={`0 0 ${String(ALL_POINTS)} 1`} preserveAspectRatio="none" aria-hidden="true">
                <rect class="declarer" width={view.points.declarer} height="1" />
                <rect
                    class="opponents"
                    x={ALL_POINTS - view.points.opponents}
                    width={view.points.opponents}
                    height="1"
                />
            </svg>
            <i class="win-line"></i>
        </span>
    </div>
    <div class="coasters">
        {#each view.rows as row (row.seat)}
            <div class="reck" class:win={row.winner} data-seat={row.seat}>
                <span class="dot" aria-hidden="true">{row.initial}</span>
                <span class="nm">{row.name ?? words.seatFree}</span>
                <span class="dl" class:minus={row.gain <= 0}>{row.gainText}</span>
            </div>
        {/each}
    </div>
</div>
