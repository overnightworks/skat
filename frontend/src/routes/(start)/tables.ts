import {
    AUTH_START_PATH,
    type POSITION_TOKENS,
    type RANK_TOKENS,
    RETURN_PATH_QUERY_NAME,
    SIGNED_IN_AGAIN_QUERY_NAME,
    type SUIT_TOKENS,
    TABLE_EVENTS_SUFFIX,
    TABLE_PAGE_PREFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
} from "#lib/wire.ts";
import { words } from "#lib/words.ts";

const SIGNED_OUT_STATUS = 401;
const NOT_FOUND_STATUS = 404;
const CONFLICT_STATUS = 409;
// A refusal this soon after the page was reached through an automatic sign-in shows the sign-in page instead
// of navigating again: a session the sign-in just made and the server refuses at once would otherwise loop forever.
const RESIGN_IN_WINDOW_MILLISECONDS = 30_000;

export type Suit = (typeof SUIT_TOKENS)[number];
export type Rank = (typeof RANK_TOKENS)[number];
export type Position = (typeof POSITION_TOKENS)[number];
export type Card = { suit: Suit; rank: Rank };
export type ChairHand = { position: Position; card_count: number };
export type Hand = { dealer_seat: number; own_cards: Card[]; skat_count: number };
export type Chair = {
    seat: number;
    occupant_name: string | null;
    is_mine: boolean;
    is_away: boolean;
    hand: ChairHand | null;
};
export type Table = { id: string; version: number; chairs: Chair[]; watchers: number; hand: Hand | null };
// A chair that was taken: `holder` is who sits there now.
export type Outcome =
    { kind: "table"; table: Table } | { kind: "taken"; holder: string } | { kind: "missing" } | { kind: "failed" };

function isTakenChair(body: unknown): body is { reason: "seat-taken"; holder_name: string } {
    return typeof body === "object" && body !== null && "reason" in body && body.reason === "seat-taken";
}

// A session that ended while the page was open goes through the sign-in again; any other failure
// is shown to the person as it is, and nothing is retried behind their back.
async function ask(path: string, init?: RequestInit): Promise<Outcome> {
    let answer: Response;
    try {
        answer = await fetch(path, init);
    } catch {
        return { kind: "failed" };
    }
    if (answer.status === SIGNED_OUT_STATUS) {
        location.reload();
        return { kind: "failed" };
    }
    if (answer.status === NOT_FOUND_STATUS) return { kind: "missing" };
    try {
        const body: unknown = await answer.json();
        if (answer.ok) return { kind: "table", table: body as Table };
        // Any other refusal means the page showed a stale table: its stream is about to correct it.
        if (answer.status === CONFLICT_STATUS && isTakenChair(body)) return { kind: "taken", holder: body.holder_name };
        return { kind: "failed" };
    } catch {
        return { kind: "failed" };
    }
}

// The command id is the retry key: asking again with the same one returns the table the first ask opened.
export function createTable(commandId: string): Promise<Outcome> {
    return ask(TABLES_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command_id: commandId }),
    });
}

function post(id: string, suffix: string, body: object): Promise<Outcome> {
    return ask(`${TABLES_PATH}/${encodeURIComponent(id)}${suffix}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
}

export function sitDown(id: string, seat: number, commandId: string): Promise<Outcome> {
    return post(id, TABLE_SIT_SUFFIX, { command_id: commandId, seat });
}

export function standUp(id: string, commandId: string): Promise<Outcome> {
    return post(id, TABLE_STAND_SUFFIX, { command_id: commandId });
}

export function readTable(id: string): Promise<Outcome> {
    takeSignedInAgainMarker();
    return ask(`${TABLES_PATH}/${encodeURIComponent(id)}`);
}

// The page that the sign-in returns to carries a marker in its address, so nothing is kept on the device.
// The reload of a table address is answered with the sign-in page while the session stays ended.
function signInAgain(id: string, reachedBySigningIn: boolean): void {
    if (reachedBySigningIn && performance.now() < RESIGN_IN_WINDOW_MILLISECONDS) {
        location.reload();
        return;
    }
    const returnPath = `${tablePath(id)}?${SIGNED_IN_AGAIN_QUERY_NAME}=1`;
    location.assign(`${AUTH_START_PATH}?${RETURN_PATH_QUERY_NAME}=${encodeURIComponent(returnPath)}`);
}

let reachedBySigningIn = false;

// The marker is taken at the page's first table request, whatever the answer, and then leaves the address
// bar, so a reload, a bookmark or a shared link never carries it. Later calls find it gone and keep the result.
function takeSignedInAgainMarker(): void {
    const address = new URL(location.href);
    if (!address.searchParams.has(SIGNED_IN_AGAIN_QUERY_NAME)) return;
    address.searchParams.delete(SIGNED_IN_AGAIN_QUERY_NAME);
    history.replaceState(history.state, "", address);
    reachedBySigningIn = true;
}

// A stream that ends is a refused session or a dropped connection; the table's own session check tells
// them apart. Only a 401 signs in again: a drop, or any other answer, leaves the stream to reconnect.
async function sessionIsRefused(id: string): Promise<boolean> {
    try {
        return (await fetch(`${TABLES_PATH}/${encodeURIComponent(id)}`)).status === SIGNED_OUT_STATUS;
    } catch {
        // The connection is down: the dimmed page and the stream's own reconnect carry on.
        return false;
    }
}

// The server sends the full view first and a fresh one after every change; a lost connection
// reconnects by itself and starts again from a full view, so a view always replaces the last.
// The returned function closes the stream.
export function watchTable(
    id: string,
    onTable: (table: Table) => void,
    onConnection: (connected: boolean) => void,
): () => void {
    const reachedNow = reachedBySigningIn;
    const source = new EventSource(`${TABLES_PATH}/${encodeURIComponent(id)}${TABLE_EVENTS_SUFFIX}`);
    source.onmessage = (event: MessageEvent<string>) => {
        onConnection(true);
        onTable(JSON.parse(event.data) as Table);
    };
    // One check at a time, and none counts once the page navigates or stops watching: a second 401 would
    // otherwise reload under the loop guard and cancel the sign-in navigation that the first one started.
    let checking = false;
    let finished = false;
    source.onerror = () => {
        onConnection(false);
        if (checking || finished) return;
        checking = true;
        void sessionIsRefused(id).then((refused) => {
            checking = false;
            if (!refused || finished) return;
            finished = true;
            source.close();
            signInAgain(id, reachedNow);
        });
    };
    return () => {
        finished = true;
        source.close();
    };
}

export function tablePath(id: string): string {
    return `${TABLE_PAGE_PREFIX}${id}`;
}

// The seats in drawing order: the viewer's own chair comes last, which is the one at the bottom.
export function drawingOrder(chairs: Chair[]): Chair[] {
    const afterMine = chairs.findIndex((chair) => chair.is_mine) + 1;
    return [...chairs.slice(afterMine), ...chairs.slice(0, afterMine)];
}

const POSITION_WORDS: Record<Position, string> = {
    forehand: words.forehand,
    middlehand: words.middlehand,
    rearhand: words.rearhand,
};

export function positionWord(position: Position): string {
    return POSITION_WORDS[position];
}

export async function copyTableLink(id: string): Promise<boolean> {
    try {
        await navigator.clipboard.writeText(`${location.origin}${tablePath(id)}`);
        return true;
    } catch {
        return false;
    }
}
