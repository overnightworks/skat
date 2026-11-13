import type { Chair, RamschResult, Result, Table } from "../routes/(start)/tables.ts";

const DECLARER_SEAT = 2;
export const NOBODY = 0;

export function chairs(mine: number, changes: Record<number, Partial<Chair>> = {}): Chair[] {
    return [1, 2, 3].map((seat) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === mine,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
        former_holder_name: null,
        ...changes[seat],
    }));
}

// Kreuz mit 2, won by the declarer at seat 2: 3 × 12 = 36 plus the list's 50 (ISkO 2.1, 4.1).
export const WON_GAME: Result = {
    kind: "declared",
    ordinal: 3,
    declarer_seat: DECLARER_SEAT,
    game: "kreuz",
    hand: false,
    ouvert: false,
    announcement: "none",
    matadors: { mit: true, count: 2 },
    base_value: 12,
    levels: ["spiel"],
    multiplier: 3,
    list_bonus: 50,
    announcement_missed: false,
    won: true,
    doubled: false,
    overbid: false,
    bid: 18,
    game_value: 36,
    settled_value: 36,
    score: 36,
    declarer_points: 78,
    opponents_points: 42,
    gains: [
        { seat: 1, gain: 0, won: false },
        { seat: 2, gain: 86, won: true },
        { seat: 3, gain: 0, won: false },
    ],
    bock_factor: 1,
    kontra: null,
};

// The same game lost: the value doubles to −72, the list takes 50 and each opponent gets 40.
export const LOST_GAME: Partial<Result> = {
    won: false,
    doubled: true,
    list_bonus: -50,
    score: -72,
    gains: [
        { seat: 1, gain: 40, won: true },
        { seat: 2, gain: -122, won: false },
        { seat: 3, gain: 40, won: true },
    ],
};

// Null counts no matadors, levels or multiplier.
export const NULL_GAME: Partial<Result> = {
    game: "null",
    matadors: null,
    levels: [],
    multiplier: null,
    base_value: null,
};

function result(changes: Partial<Result> = {}): Result {
    return { ...WON_GAME, ...changes };
}

export function table(
    mine: number,
    changes: Partial<Result> | null,
    chairChanges: Record<number, Partial<Chair>> = {},
): Table {
    return {
        id: "a".repeat(32),
        version: 9,
        chairs: chairs(mine, chairChanges),
        watchers: 0,
        hand: null,
        result: changes === null ? null : result(changes),
        passed_in: null,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
    };
}

// A Ramsch's end as the server counted it: the seats' eyes and what each adds, the factors on the losers' score.
export function ramschResult(
    eyes: [number, number, number],
    scores: [number, number, number],
    changes: Partial<RamschResult>,
) {
    return {
        kind: "ramsch",
        ordinal: 4,
        seats: eyes.map((points, index) => ({ seat: index + 1, points, score: scores[index] as number })),
        durchmarsch_seat: null,
        jungfrau: false,
        bock_factor: 1,
        pushes: 0,
        push_factor: 1,
        divided_by_ten: false,
        ...changes,
    } satisfies RamschResult;
}

// The four blessed scenes of the Ramsch's card, seen from Felix at seat 3.
export const LOST_WITH_PUSHES = ramschResult([20, 14, 86], [0, 0, -344], { pushes: 2, push_factor: 4 });
export const OTHER_LOSES = ramschResult([14, 86, 20], [0, -86, 0], {});
export const JUNGFRAU = ramschResult([0, 86, 34], [0, -172, 0], { jungfrau: true });
export const DURCHMARSCH = ramschResult([120, 0, 0], [120, 0, 0], { durchmarsch_seat: 1 });
