import { nextSettingsRevisionOf, seriesOver } from "#lib/series.ts";
import { TABLE_NEW_SERIES_SUFFIX, TABLE_NEXT_SETTINGS_SUFFIX, TABLE_READY_SUFFIX } from "#lib/wire.ts";
import { post, type OptionsRequest, type Outcome, type Table } from "./tables.ts";

// A table opened without a series has none and counts as the first series, as the server counts it.
export function seriesNumberOf(table: Pick<Table, "series">): number {
    return table.series?.number ?? 1;
}

// „Weiter“ names the result and the series it saw, so a tap on a result or series that has since been replaced is refused.
export function markReady(id: string, commandId: string, ordinal: number, series: number): Promise<Outcome> {
    return post(id, TABLE_READY_SUFFIX, { command_id: commandId, ordinal, series });
}

// „Neue Serie“ names the series it saw as „Weiter“ does, so a tap on a series that has since been replaced is refused,
// and the revision of the next series' settings it saw, so a tap on settings that have since been saved over is too.
export function startNewSeries(id: string, commandId: string, series: number, settings: number): Promise<Outcome> {
    return post(id, TABLE_NEW_SERIES_SUFFIX, { command_id: commandId, series, settings });
}

// After the series' last game the same tap is „Neue Serie“, which names the series it saw as „Weiter“ does.
export function weiter(id: string, table: Table): Promise<Outcome> {
    return seriesOver(table)
        ? startNewSeries(id, crypto.randomUUID(), seriesNumberOf(table), nextSettingsRevisionOf(table))
        : markReady(
              id,
              crypto.randomUUID(),
              (table.result as NonNullable<Table["result"]>).ordinal,
              seriesNumberOf(table),
          );
}

// Saving the next series' settings names the series it saw and the revision of the settings its sheet started from, so a
// save over settings another seat has saved since is refused; the stream brings them to every page at the table, and the
// save takes back every seat's „Neue Serie“. Another length or other rules is another command.
export function changeNextSettings(
    id: string,
    commandId: string,
    series: number,
    settings: number,
    length: number,
    options?: OptionsRequest,
): Promise<Outcome> {
    return post(id, TABLE_NEXT_SETTINGS_SUFFIX, {
        command_id: commandId,
        series,
        settings,
        series_length: length,
        options,
    });
}
