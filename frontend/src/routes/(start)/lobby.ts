// The start page's list of the tables a member sits at: the stream it reads and what each card says.

import { withMinus } from "#lib/result.ts";
import { openStream } from "#lib/stream.ts";
import { ACCOUNT_PATH, LOBBY_EVENTS_PATH, type WAITING_CASE_TOKENS } from "#lib/wire.ts";
import { words } from "#lib/words.ts";

const MILLISECONDS_PER_SECOND = 1_000;
const SECONDS_PER_MINUTE = 60;
const MILLISECONDS_PER_DAY = 86_400_000;
// A name that ends in one of these takes an apostrophe where another takes an s.
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
type Mine = { tables: LobbyTable[] };

export type ChipKind = "turn" | "result" | "seriesOver" | "ends";
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
};
export type Card = {
    id: string;
    title: string;
    progress: string | null;
    seats: SeatCard[];
    chips: Chip[];
};

// The stream sends the whole list first and again after every change, so each list replaces the last. The shared
// reader reconnects by itself; the returned function closes the stream.
export function watchLobby(
    onMine: (tables: LobbyTable[]) => void,
    onConnection: (connected: boolean) => void,
): () => void {
    return openStream(LOBBY_EVENTS_PATH, {
        events: {
            mine: (data) => {
                onMine((JSON.parse(data) as Mine).tables);
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

function possessiveOf(name: string): string {
    return SIBILANT_ENDINGS.test(name) ? `${name}'` : `${name}s`;
}

export function titleOf(name: string | null): string {
    return name === null ? words["lobby.titleNameless"] : words["lobby.title"]({ owner: possessiveOf(name) });
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

function progressOf(table: LobbyTable): string | null {
    if (table.game_count === null) return null;
    if (table.game_number === null) return words["lobby.length"](table.game_count);
    return words["lobby.progress"]({ game: String(table.game_number), count: table.game_count });
}

// The stream never marks the own chair away; it is away where its hold runs or where nobody is at a dealt table.
function isAway(chair: LobbyChair, table: LobbyTable): boolean {
    if (chair.is_away) return true;
    return chair.is_mine && ((chair.hold_seconds_left ?? null) !== null || table.ends_at !== null);
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
            : words["lobby.otherSeatFreeIn"](minutes, { ...gaps, owner: possessiveOf(chair.occupant_name) }),
    };
}

function seatOf(chair: LobbyChair, table: LobbyTable, heldMilliseconds: number): SeatCard {
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
    return {
        id: table.id,
        title: titleOf(table.title_name),
        progress: progressOf(table),
        seats: table.chairs.map((chair) => seatOf(chair, table, heldMilliseconds)),
        chips: chipsOf(table, nowMilliseconds),
    };
}
