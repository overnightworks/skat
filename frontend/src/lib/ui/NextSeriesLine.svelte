<script lang="ts">
    import type { NextSeriesLine } from "#lib/series.ts";
    import RuleMark from "#lib/ui/RuleMark.svelte";
    import { words } from "#lib/words.ts";

    // The settings the next series begins with, under the standings of the series that ended.
    const { line }: { line: NextSeriesLine } = $props();
</script>

<div class="nextline">
    <span class="lbl">{words["table.nextSeries"]}</span>
    <span class="chips">
        <span class="chip len">
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.2"
                stroke-linecap="round"
                aria-hidden="true"
            >
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
            </svg>
            {line.length}
        </span>
        {#each line.chips as chip (chip.id)}
            <span class="chip" class:official={chip.id === "official"}><RuleMark id={chip.id} />{chip.word}</span>
        {/each}
    </span>
</div>
