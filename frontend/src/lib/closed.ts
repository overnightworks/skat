import { standingRow, type StandingsView } from "#lib/series.ts";
import { words } from "#lib/words.ts";
import type { Ended } from "../routes/(start)/tables.ts";

const SECONDS_PER_MINUTE = 60;

// Whole minutes rounded down from a minute on, so the wait never reads longer than the stored one; below that, seconds.
// The minutes go in as a named gap in plain digits, because the count's thousands separator would change a long wait's reading.
function emptyHeading(seconds: number): string {
    if (seconds < SECONDS_PER_MINUTE) return words["closed.emptySeconds"](seconds);
    const minutes = Math.floor(seconds / SECONDS_PER_MINUTE);
    return words["closed.emptyMinutes"](minutes, { minutes: String(minutes) });
}

// Each reason names its own heading; a reason added to the wire fails the type check until its words are here.
export function closedWords(ended: Ended): string {
    switch (ended.reason) {
        case "empty":
            return emptyHeading(ended.empty_seconds);
        case "unplayed":
            return words["closed.unplayedDays"](ended.unplayed_days);
        case "stopped":
            return words["closed.seriesEnded"];
        case "closed":
            return ended.closed_by_name === null
                ? words["closed.closed"]
                : words["closed.closedBy"]({ name: ended.closed_by_name });
    }
}

// An ended table that finished a game shows its last series' standings whatever the reason, and none that finished no game.
export function closedStandings(ended: Ended): Pick<StandingsView, "heading" | "sub" | "rows"> | null {
    if (ended.standings === null) return null;
    return {
        heading: words["closed.seriesEnded"],
        sub: words["table.seriesGames"](ended.game_count),
        rows: ended.standings.map((standing) => standingRow(standing, null)),
    };
}
