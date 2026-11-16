import { TABLE_LIST_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import {
    fetchSigningInAgain,
    type Announcement,
    type Game,
    type Level,
    type OccupantKind,
    type Word,
} from "./tables.ts";

// A finished game of the series' list as the server projects it, the same for every viewer.
export type SeriesEntry =
    | {
          kind: "declared";
          number: number;
          declarer_name: string | null;
          declarer_seat: number;
          declarer_kind: OccupantKind | null;
          game: Game;
          hand: boolean;
          ouvert: boolean;
          announcement: Announcement;
          levels: Level[];
          settled_value: number;
          score: number;
          declarer_points: number;
          kontra_word: Word | null;
          bock_factor: number;
      }
    | {
          kind: "ramsch";
          number: number;
          seats: { name: string | null; kind: OccupantKind | null; score: number }[];
          durchmarsch: boolean;
          jungfrau: boolean;
          bock_factor: number;
          pushes: number;
          push_factor: number;
      };

// The games in the order played; null when the list cannot be read.
export async function readSeriesList(id: string): Promise<SeriesEntry[] | null> {
    const answer = await fetchSigningInAgain(`${TABLES_PATH}/${encodeURIComponent(id)}${TABLE_LIST_SUFFIX}`);
    if (answer?.ok !== true) return null;
    try {
        return ((await answer.json()) as { entries: SeriesEntry[] }).entries;
    } catch {
        return null;
    }
}
