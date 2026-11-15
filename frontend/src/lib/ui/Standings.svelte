<script lang="ts">
    import type { Snippet } from "svelte";
    import { AiMark } from "overnightworks-design";
    import type { StandingsView } from "#lib/series.ts";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";
    import { words } from "#lib/words.ts";

    // The end of the series: the winner on top, the same for every viewer, and it shows no card. Each dot wears the
    // colour of the seat its account last held; an agent's shows the sparkle and its name the AI mark. The closed
    // table's page sets what it adds below the ranks as the children, and the panel then wears its own class.
    const {
        view,
        closed = false,
        children,
    }: { view: Pick<StandingsView, "heading" | "sub" | "rows">; closed?: boolean; children?: Snippet } = $props();
</script>

<div class="result standing" class:closedseries={closed} role="status">
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
                <span class={["dot", `seat-${String(row.seat)}`, row.agent && "agent"]} aria-hidden="true">
                    {#if row.agent}<AgentSparkle />{:else}{row.initial}{/if}
                </span>
                <span class="txt">
                    <b
                        >{row.name}{#if row.agent}<AiMark />{/if}{#if row.gone}<em>{words["table.seriesGone"]}</em
                            >{/if}</b
                    >
                    <small>{row.record}</small>
                </span>
                <span class="sum">{row.total}</span>
            </li>
        {/each}
    </ol>
    {@render children?.()}
</div>
