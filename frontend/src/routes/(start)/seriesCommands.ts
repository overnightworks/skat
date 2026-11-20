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

// Saving the next series' settings names the series it saw; the stream brings them to every page at the table, and the
// save takes back every seat's „Neue Serie“. Another length or other rules is another command.
export function changeNextSettings(
    id: string,
    commandId: string,
    series: number,
    length: number,
    options?: OptionsRequest,
): Promise<Outcome> {
    return post(id, TABLE_NEXT_SETTINGS_SUFFIX, { command_id: commandId, series, series_length: length, options });
}
