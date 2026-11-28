<script lang="ts">
    import { AiMark } from "overnightworks-design";
    import type { GameRow } from "#lib/series.ts";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";

    // What one game's row says: its number, who it names in the colour of their seat, the game, its value and its gain.
    const { row }: { row: GameRow } = $props();
</script>

<span class="nr">{row.number}</span>
<span class={["dot", `seat-${String(row.subjectSeat)}`, row.agent && "agent"]} aria-hidden="true">
    {#if row.agent}<AgentSparkle />{:else}{row.initial}{/if}
</span>
<span class="txt">
    <b>
        {row.name}{#if row.agent}<AiMark />{/if}
    </b>
    {#if row.line !== null}<small>{row.line}</small>{/if}
</span>
<span class="val">{row.value}</span>
<span class="gain" class:minus={row.lost}>{row.gain}</span>
