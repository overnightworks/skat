<script lang="ts">
    import type { RamschView } from "#lib/result.ts";
    import { words } from "#lib/words.ts";

    let { view }: { view: RamschView } = $props();
</script>

<div class="result ramsch snug" class:lost={view.lost} role="status">
    <h3>
        {#if view.mark !== null}
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="3"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                {#if view.mark === "tick"}
                    <path d="M5 12.5l4.5 4.5L19 7" />
                {:else}
                    <path d="M6 6l12 12M18 6L6 18" />
                {/if}
            </svg>
        {/if}
        <span>{view.word}</span>
    </h3>
    <div class="sub">
        <span class="game">
            <span class="suit" aria-hidden="true">
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <path d="M12 4v10M7 10l5 5 5-5M5 20h14" />
                </svg>
            </span>
            <span>{words["game.ramsch"]}</span>
        </span>
    </div>
    <div class="eq"><span>{view.eyes}</span></div>
    {#if view.chips.length > 0}
        <div class="ladder" role="list">
            {#each view.chips as chip (chip)}
                <span role="listitem" class="held">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                    <span>{chip}</span>
                </span>
            {/each}
        </div>
    {/if}
    <div class="value-row">
        <div class="value" class:loss={view.loss}>{view.score}</div>
    </div>
    <div class="list">
        {#each view.counts as count (count.seat)}
            <span>
                {#if count.strong}
                    <b>{`${count.name} ${count.points}`}</b>
                {:else}
                    {`${count.name} ${count.points}`}
                {/if}
            </span>
        {/each}
    </div>
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
