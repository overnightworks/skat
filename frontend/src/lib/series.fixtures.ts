import type { Chair, Series, SeriesEntry, Table } from "../routes/(start)/tables.ts";

export const WATCHER = 0;

// Seats 1 to 3 hold players 1 to 3; `ready` lists the seats that tapped.
export function chairs(mine: number, ready: number[] = []): Chair[] {
    return [1, 2, 3].map((seat) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === mine,
        is_away: false,
        ready: ready.includes(seat),
        total: null,
        hand: null,
        former_holder_name: null,
        is_mine_to_return: false,
    }));
}

export function seriesAt(changes: Partial<Series> = {}): Series {
    return { number: 1, game_number: 8, game_count: 36, over: false, standings: null, end_proposal: null, ...changes };
}

// A table between two games: no hand runs, and the viewer sits at `mine` (0 is a watcher).
export function tableBetweenGames(mine: number, series: Series | null, ready: number[] = []): Table {
    return {
        id: "a".repeat(32),
        version: 7,
        chairs: chairs(mine, ready),
        watchers: 0,
        hand: null,
        result: null,
        passed_in: null,
        series,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
    };
}

export const DECLARED_ENTRY: Extract<SeriesEntry, { kind: "declared" }> = {
    kind: "declared",
    number: 4,
    declarer_name: "player 2",
    game: "grand",
    hand: true,
    ouvert: false,
    announcement: "none",
    levels: ["spiel", "hand", "schneider"],
    settled_value: 48,
    score: 98,
    kontra_word: null,
    bock_factor: 1,
};

export const LOST_ENTRY: SeriesEntry = {
    ...DECLARED_ENTRY,
    number: 6,
    game: "herz",
    hand: false,
    levels: ["spiel"],
    score: -86,
};

export const RAMSCH_ENTRY: SeriesEntry = {
    kind: "ramsch",
    number: 7,
    seats: [
        { name: "player 1", score: 0 },
        { name: "player 2", score: -40 },
        { name: null, score: 0 },
    ],
    durchmarsch: false,
    jungfrau: false,
    bock_factor: 1,
    pushes: 2,
    push_factor: 4,
};
