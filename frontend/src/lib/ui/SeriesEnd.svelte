<script lang="ts">
    import { nextSeriesLine, nextSettingsChangeable, seriesEndAnswerBy, type StandingsView } from "#lib/series.ts";
    import AnswerClock from "#lib/ui/AnswerClock.svelte";
    import NextSeriesLine from "#lib/ui/NextSeriesLine.svelte";
    import Standings from "#lib/ui/Standings.svelte";
    import type { Table } from "../../routes/(start)/tables.ts";

    // The series' end: the standings with the next series' settings under them, which a seated member opens to change
    // with `onchange`, and on a pill of its own below them the minute a silent seat has left before the table ends.
    const { table, view, onchange }: { table: Table; view: StandingsView; onchange: () => void } = $props();
    const nextLine = $derived(nextSeriesLine(table));
    const answerBy = $derived(seriesEndAnswerBy(table));
</script>

<Standings {view}>
    {#if nextLine !== null}
        <NextSeriesLine line={nextLine} onchange={nextSettingsChangeable(table) ? onchange : undefined} />
    {/if}
</Standings>
{#if answerBy !== null}
    <div class="plaque ask timer"><AnswerClock until={answerBy} ends /></div>
{/if}
