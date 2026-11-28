import { TABLE_LIST_SUFFIX, TABLES_PATH, type SeriesListAnswer } from "#lib/wire.ts";
import { fetchSigningInAgain } from "./tables.ts";

// A finished game of the series' list as the server projects it, the same for every viewer.
export type SeriesEntry = SeriesListAnswer["entries"][number];

// The games in the order played; null when the list cannot be read.
export async function readSeriesList(id: string): Promise<SeriesEntry[] | null> {
    const answer = await fetchSigningInAgain(`${TABLES_PATH}/${encodeURIComponent(id)}${TABLE_LIST_SUFFIX}`);
    if (answer?.ok !== true) return null;
    try {
        return ((await answer.json()) as SeriesListAnswer).entries;
    } catch {
        return null;
    }
}
