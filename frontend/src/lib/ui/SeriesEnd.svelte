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
    // stays closed once that series is dealt, so the next series' end never opens it again. `changed` says that another
    // seat saved settings while the sheet was open, which then starts anew from the saved ones.
    let changing = $state<{ series: number; initial: NextSettings; changed: boolean } | null>(null);

    // True from the save's sending until its answer: the revision the save itself makes arrives on the stream, and
    // reads as another seat's save only when the save was refused or sent by another.
    let saving = $state(false);

    function open(initial: NextSettings): void {
        changing = { series: seriesNumberOf(table), initial, changed: false };
    }

    $effect(() => {
        if (!saving && changing !== null && changeable !== null && changeable.revision !== changing.initial.revision) {
            changing = { series: changing.series, initial: changeable, changed: true };
        }
    });
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
    {@const { series, initial, changed } = changing}
    {#key initial.revision}
        <NextSeriesSheet
            {initial}
            settingsChanged={changed}
            {answerBy}
            takenBack={takenBackLine(table)}
            save={async (commandId: string, length: number, options: OptionsRequest | undefined) => {
                saving = true;
                try {
                    const saved = await seat(
                        changeNextSettings(id, commandId, series, initial.revision, length, options),
                    );
                    if (saved.kind === "table") changing = null;
                    return saved;
                } finally {
                    saving = false;
                }
            }}
            oncancel={() => {
                changing = null;
            }}
        />
    {/key}
{/if}
