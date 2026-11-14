import type { Card, Chair, GameSheet, Series, SeriesEntry, Table } from "../routes/(start)/tables.ts";

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
        nudge: null,
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
        opened_by_me: false,
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
    declarer_points: 95,
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
    declarer_points: 54,
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

const KARO_ACE: Card = { suit: "karo", rank: "ace" };
const KREUZ_JACK: Card = { suit: "kreuz", rank: "jack" };
const PIK_SEVEN: Card = { suit: "pik", rank: "seven" };
const HERZ_TEN: Card = { suit: "herz", rank: "ten" };

// A suit game of seat 2 whose first trick seat 2 took and whose second the opponents took, then given up by seat 2 in the
// third, of which two cards were played.
export const GIVEN_UP_SHEET: GameSheet = {
    number: 4,
    seat_names: ["Anna", "Ben", "Cleo"],
    count: {
        kind: "declared",
        declarer_seat: 2,
        declarer_points: 21,
        opponents_points: 99,
        ending: "given-up",
        ended_by_seat: 2,
    },
    cards: {
        hands: [
            {
                seat: 1,
                cards: [
                    { card: PIK_SEVEN, state: "played" },
                    { card: KREUZ_JACK, state: "unplayed" },
                ],
            },
            {
                seat: 2,
                cards: [
                    { card: HERZ_TEN, state: "put-away" },
                    { card: KARO_ACE, state: "played" },
                ],
            },
            { seat: 3, cards: [{ card: { suit: "karo", rank: "seven" }, state: "played" }] },
        ],
        skat: [HERZ_TEN, PIK_SEVEN],
        laid_skat: [],
        put_away: [{ seat: 2, card: HERZ_TEN }],
        tricks: [
            {
                number: 1,
                cards: [
                    { seat: 2, card: KARO_ACE },
                    { seat: 3, card: { suit: "karo", rank: "seven" } },
                    { seat: 1, card: PIK_SEVEN },
                ],
                taker_seat: 2,
                points: 11,
            },
            {
                number: 2,
                cards: [
                    { seat: 2, card: KARO_ACE },
                    { seat: 3, card: KREUZ_JACK },
                    { seat: 1, card: HERZ_TEN },
                ],
                taker_seat: 3,
                points: 12,
            },
            {
                number: 3,
                cards: [
                    { seat: 3, card: KREUZ_JACK },
                    { seat: 1, card: HERZ_TEN },
                ],
                taker_seat: null,
                points: null,
            },
        ],
        skat_takers: [],
    },
};

// A Ramsch in which seat 3 lost with the most points and the skat went to seat 1.
export const RAMSCH_SHEET: GameSheet = {
    number: 5,
    seat_names: ["Anna", null, "Cleo"],
    count: { kind: "ramsch", seat_points: [12, 20, 88], durchmarsch_seat: null },
    cards: {
        hands: [
            { seat: 1, cards: [{ card: PIK_SEVEN, state: "played" }] },
            { seat: 2, cards: [{ card: KARO_ACE, state: "played" }] },
            { seat: 3, cards: [{ card: KREUZ_JACK, state: "played" }] },
        ],
        skat: [HERZ_TEN],
        laid_skat: [],
        put_away: [{ seat: 3, card: HERZ_TEN }],
        tricks: [
            {
                number: 1,
                cards: [
                    { seat: 1, card: PIK_SEVEN },
                    { seat: 2, card: KARO_ACE },
                    { seat: 3, card: KREUZ_JACK },
                ],
                taker_seat: 3,
                points: 13,
            },
        ],
        skat_takers: [1],
    },
};

// A Schieberamsch in which seat 3 took the skat and put back the cards that went to seat 1 with the last trick.
export const SCHIEBERAMSCH_SHEET: GameSheet = {
    ...RAMSCH_SHEET,
    cards: { ...(RAMSCH_SHEET.cards as NonNullable<GameSheet["cards"]>), skat: [PIK_SEVEN], laid_skat: [HERZ_TEN] },
};

// A game finished before games kept their cards.
export const OLD_SHEET: GameSheet = { ...GIVEN_UP_SHEET, cards: null };
