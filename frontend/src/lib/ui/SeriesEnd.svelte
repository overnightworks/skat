<script lang="ts">
    import {
        changeableSettingsOf,
        nextSeriesLine,
        seriesEndAnswerBy,
        takenBackLine,
        type StandingsView,
    } from "#lib/series.ts";
    import AnswerClock from "#lib/ui/AnswerClock.svelte";
    import NextSeriesLine from "#lib/ui/NextSeriesLine.svelte";
    import NextSeriesSheet from "#lib/ui/NextSeriesSheet.svelte";
    import Standings from "#lib/ui/Standings.svelte";
    import { changeNextSettings, seriesNumberOf } from "../../routes/(start)/seriesCommands.ts";
    import type { NextSettings, OptionsRequest, Outcome, Table } from "../../routes/(start)/tables.ts";

    // The series' end: the standings with the next series' settings under them, which a seated member opens to change
    // in a sheet whose save `seat` sends for the series it was opened at, and on a pill of its own below them the minute
    // a silent seat has left before the table ends.
    const {
        id,
        table,
        view,
        seat,
    }: { id: string; table: Table; view: StandingsView; seat: (command: Promise<Outcome>) => Promise<Outcome> } =
        $props();
    const nextLine = $derived(nextSeriesLine(table));
    const answerBy = $derived(seriesEndAnswerBy(table));
    const changeable = $derived(changeableSettingsOf(table));
    // The settings the open sheet started from and the series whose end it was opened at; null while it is closed. It
    // stays closed once that series is dealt, so the next series' end never opens it again.
    let changing = $state<{ series: number; initial: NextSettings } | null>(null);

    function open(initial: NextSettings): void {
        changing = { series: seriesNumberOf(table), initial };
    }
</script>

<Standings {view}>
    {#if nextLine !== null}
        <NextSeriesLine
            line={nextLine}
            onchange={changeable === null
                ? undefined
                : () => {
                      open(changeable);
                  }}
        />
    {/if}
</Standings>
{#if answerBy !== null}
    <div class="plaque ask timer"><AnswerClock until={answerBy} ends /></div>
{/if}
{#if changing !== null && changing.series === seriesNumberOf(table) && changeable !== null}
    {@const series = changing.series}
    <NextSeriesSheet
        initial={changing.initial}
        takenBack={takenBackLine(table)}
        save={async (commandId: string, length: number, options: OptionsRequest | undefined) => {
            const saved = await seat(changeNextSettings(id, commandId, series, length, options));
            if (saved.kind === "table") changing = null;
            return saved;
        }}
        oncancel={() => {
            changing = null;
        }}
    />
{/if}
