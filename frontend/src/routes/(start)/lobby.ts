// The start page's lists of the tables a member sits at and of the open tables: the stream they come on and what each
// card says.

import { withMinus } from "#lib/result.ts";
import { openStream } from "#lib/stream.ts";
import { tableRules, type RuleChip } from "#lib/tableRules.ts";
import { ACCOUNT_PATH, LOBBY_EVENTS_PATH, type WAITING_CASE_TOKENS } from "#lib/wire.ts";
import { words } from "#lib/words.ts";
import type { Options } from "./tables.ts";

const MILLISECONDS_PER_SECOND = 1_000;
const SECONDS_PER_MINUTE = 60;
const MILLISECONDS_PER_DAY = 86_400_000;
// A name that ends in one of these takes the catalog's sibilant sentence where another takes the plain one.
const SIBILANT_ENDINGS = /[sßxz]$/i;

export type WaitingCase = (typeof WAITING_CASE_TOKENS)[number];
export type LobbyChair = {
    seat: number;
    occupant_name: string | null;
    occupant_kind: "person" | "agent" | null;
    is_mine: boolean;
    ready: boolean;
    total: number | null;
    is_away: boolean;
    is_turn: boolean;
    // Seconds until the place is free, on an away chair of a table where no hand was dealt.
    hold_seconds_left?: number | null;
};
export type LobbyTable = {
    id: string;
    // A private table is listed to its chair holders alone.
    private: boolean;
    title_name: string | null;
    game_number: number | null;
    game_count: number | null;
    dealt: boolean;
    awaits_you: boolean;
    waits_on: WaitingCase | null;
    result_waits: boolean;
    series_over: boolean;
    ends_at: string | null;
    chairs: LobbyChair[];
};
// A chair of an open table, whose entry names no card, no total and no account.
export type OpenChair = {
    seat: number;
    occupant_name: string | null;
    occupant_kind: "person" | "agent" | null;
    is_away: boolean;
    hold_seconds_left: number | null;
};
// An open table the member holds no chair at, with the chair a running hand waits at and the end of a paused one.
export type OpenTable = {
    id: string;
    title_name: string | null;
    game_number: number | null;
    game_count: number | null;
    options: Options;
    watchers: number;
    free_chairs: number;
    dealt: boolean;
    waiting_seat: number | null;
    ends_at: string | null;
    chairs: OpenChair[];
};
type Mine = { tables: LobbyTable[] };
type Open = { tables: OpenTable[] };

export type ChipKind = "turn" | "result" | "seriesOver" | "ends" | "gameWaits" | "paused";
export type Chip = { kind: ChipKind; text: string; accent: boolean };
export type SeatCard = {
    seat: number;
    free: boolean;
    name: string;
    initial: string;
    agent: boolean;
    turn: boolean;
    away: boolean;
    total: string | null;
    hold: { note: string; title: string } | null;
    // What a screen reader says for the control that seats the person; null where the chair is no control.
    sitLabel: string | null;
};
export type Card = {
    id: string;
    title: string;
    private: boolean;
    // What a screen reader says for the card's link.
    openLabel: string;
    progress: string | null;
    // How many accounts without a chair look on, and the rules the table plays: an open table shows both.
    watchers: number | null;
    rules: RuleChip[];
    seats: SeatCard[];
    chips: Chip[];
};

// The stream sends each whole list first and again after every change, so each list replaces the last. The shared
// reader reconnects by itself; the returned function closes the stream.
export function watchLobby(
    onMine: (tables: LobbyTable[]) => void,
    onOpen: (tables: OpenTable[]) => void,
    onConnection: (connected: boolean) => void,
): () => void {
    return openStream(LOBBY_EVENTS_PATH, {
        events: {
            mine: (data) => {
                onMine((JSON.parse(data) as Mine).tables);
            },
            open: (data) => {
                onOpen((JSON.parse(data) as Open).tables);
            },
        },
        sessionPath: ACCOUNT_PATH,
        onConnection,
        onRefused: () => {
            // The gate leads a page without a session to the sign-in.
            location.reload();
        },
    });
}

function isSibilant(name: string): boolean {
    return SIBILANT_ENDINGS.test(name);
}

export function titleOf(name: string | null): string {
    if (name === null) return words["lobby.titleNameless"];
    return isSibilant(name) ? words["lobby.titleSibilant"]({ name }) : words["lobby.title"]({ name });
}

// Whole days rounded down; below a day, and once the end has passed, the table ends today.
export function daysLeftWords(endsAt: string, nowMilliseconds: number): string {
    const days = Math.floor((Date.parse(endsAt) - nowMilliseconds) / MILLISECONDS_PER_DAY);
    return days < 1 ? words["lobby.endsToday"] : words["lobby.endsInDays"](days, { days: String(days) });
}

// Whole minutes rounded up, so the last minute reads „1 Min“; null once the hold has run out.
export function minutesLeft(secondsLeft: number, heldMilliseconds: number): number | null {
    const left = secondsLeft * MILLISECONDS_PER_SECOND - heldMilliseconds;
    return left <= 0 ? null : Math.ceil(left / (SECONDS_PER_MINUTE * MILLISECONDS_PER_SECOND));
}

// The stream counts the game as 0 before the first deal.
function progressOf(table: Pick<LobbyTable, "game_number" | "game_count">): string | null {
    if (table.game_number === null || table.game_count === null) return null;
    if (table.game_number === 0) return words["lobby.length"](table.game_count);
    return words["lobby.progress"]({ game: String(table.game_number), count: table.game_count });
}

// The stream never marks the own chair away; it is away where its hold runs or where nobody is at a dealt table.
function isAway(chair: LobbyChair, table: Pick<LobbyTable, "ends_at">): boolean {
    if (chair.is_away) return true;
    return chair.is_mine && ((chair.hold_seconds_left ?? null) !== null || table.ends_at !== null);
}

function otherSeatFreeIn(name: string, minutes: number): string {
    const gaps = { name, minutes: String(minutes) };
    return isSibilant(name)
        ? words["lobby.otherSeatFreeInSibilant"](minutes, gaps)
        : words["lobby.otherSeatFreeIn"](minutes, gaps);
}

function holdOf(chair: LobbyChair, heldMilliseconds: number): SeatCard["hold"] {
    const seconds = chair.hold_seconds_left;
    if (chair.occupant_name === null || seconds === undefined || seconds === null) return null;
    const minutes = minutesLeft(seconds, heldMilliseconds);
    if (minutes === null) return null;
    const gaps = { minutes: String(minutes) };
    return {
        note: words["lobby.minutesLeft"](minutes, gaps),
        title: chair.is_mine
            ? words["lobby.ownSeatFreeIn"](minutes, gaps)
            : otherSeatFreeIn(chair.occupant_name, minutes),
    };
}

function seatOf(
    chair: LobbyChair,
    table: Pick<LobbyTable, "ends_at">,
    heldMilliseconds: number,
    sitLabel: string | null,
): SeatCard {
    const name = chair.occupant_name;
    return {
        seat: chair.seat,
        free: name === null,
        name: chair.is_mine ? words["lobby.sideYou"] : (name ?? words["lobby.seatFree"]),
        initial: name === null ? "" : name.slice(0, 1),
        agent: chair.occupant_kind === "agent",
        turn: chair.is_turn,
        away: isAway(chair, table),
        total: chair.total === null ? null : withMinus(chair.total),
        hold: holdOf(chair, heldMilliseconds),
        sitLabel: name === null ? sitLabel : null,
    };
}

// What waits is keyed on the own chair's readiness, not on `awaits_you` alone: a result stays on the card after
// the own „Weiter“, neutral. A question about an early end has no chip, and a passed-in pause none.
function chipsOf(table: LobbyTable, nowMilliseconds: number): Chip[] {
    const chips: Chip[] = [];
    const accent = !table.chairs.some((chair) => chair.is_mine && chair.ready);
    if (table.waits_on === "turn" || table.waits_on === "give_up") {
        chips.push({ kind: "turn", text: words["lobby.chipYourTurn"], accent: true });
    } else if (table.series_over && table.result_waits) {
        chips.push({ kind: "seriesOver", text: words["lobby.chipSeriesOver"], accent });
    } else if (table.result_waits) {
        chips.push({ kind: "result", text: words["lobby.chipResultWaits"], accent });
    }
    if (table.ends_at !== null) {
        chips.push({ kind: "ends", text: daysLeftWords(table.ends_at, nowMilliseconds), accent: false });
    }
    return chips;
}

// `heldMilliseconds` is how long the page has held this list, so a hold counts down between two lists.
export function cardOf(table: LobbyTable, nowMilliseconds: number, heldMilliseconds: number): Card {
    const title = titleOf(table.title_name);
    return {
        id: table.id,
        title,
        private: table.private,
        openLabel: words["lobby.openTable"]({ title }),
        progress: progressOf(table),
        watchers: null,
        rules: [],
        seats: table.chairs.map((chair) => seatOf(chair, table, heldMilliseconds, null)),
        chips: chipsOf(table, nowMilliseconds),
    };
}

// A chair of an open table is seen from outside: nobody's own, no total, no turn.
function outsideChairOf(chair: OpenChair): LobbyChair {
    return { ...chair, is_mine: false, ready: false, total: null, is_turn: false };
}

// A running hand that waits for a sitter is the accent; a paused table, where a hand was dealt and nobody is present,
// is plain, and names no end.
function openChipsOf(table: OpenTable): Chip[] {
    const chips: Chip[] = [];
    if (table.waiting_seat !== null)
        chips.push({ kind: "gameWaits", text: words["lobby.chipGameWaits"], accent: true });
    if (table.ends_at !== null) chips.push({ kind: "paused", text: words["lobby.chipPaused"], accent: false });
    return chips;
}

// The entry of an open table: every free chair is the control that seats the person, and the rest of it is display.
export function openCardOf(table: OpenTable, heldMilliseconds: number): Card {
    const title = titleOf(table.title_name);
    const sitLabel = words["lobby.sitAt"]({ title });
    return {
        id: table.id,
        title,
        private: false,
        openLabel: words["lobby.openTable"]({ title }),
        progress: progressOf(table),
        watchers: table.watchers,
        rules: tableRules(table.options, null).chips,
        seats: table.chairs.map((chair) => seatOf(outsideChairOf(chair), table, heldMilliseconds, sitLabel)),
        chips: openChipsOf(table),
    };
}
