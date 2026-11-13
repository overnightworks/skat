<script lang="ts">
    import type { StandingsView } from "#lib/series.ts";
    import { words } from "#lib/words.ts";

    // The end of the series: the winner on top, the same for every viewer, and it shows no card.
    const { view }: { view: StandingsView } = $props();
</script>

<div class="result standing" role="status">
    <h3>
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M7 4h10v5a5 5 0 0 1-10 0zM7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3M12 14v4M8 20h8" />
        </svg>
        <span>{view.heading}</span>
    </h3>
    <div class="sub">{view.sub}</div>
    <ol class="ranks">
        {#each view.rows as row, index (index)}
            <li class="rank" class:win={row.winner} class:gone={row.gone}>
                <span class="place">{row.place}</span>
                <span class="dot" aria-hidden="true">{row.initial}</span>
                <span class="txt">
                    <b
                        >{row.name}{#if row.gone}<em>{words["table.seriesGone"]}</em>{/if}</b
                    >
                    <small>{row.record}</small>
                </span>
                <span class="sum">{row.total}</span>
            </li>
        {/each}
    </ol>
</div>
