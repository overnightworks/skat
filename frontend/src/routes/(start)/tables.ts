import { AUTH_START_PATH, TABLE_EVENTS_SUFFIX, TABLE_PAGE_PREFIX, TABLES_PATH } from "#lib/wire.ts";

const SIGNED_OUT_STATUS = 401;
const NOT_FOUND_STATUS = 404;
// A second refusal this soon after a sign-in navigation shows the sign-in page instead of navigating again:
// a session the sign-in just made and the server refuses at once would otherwise loop forever.
const RESIGN_IN_WINDOW_MILLISECONDS = 30_000;
const RESIGN_IN_STORAGE_KEY = "skat.resignInAt";
const RETURN_QUERY_NAME = "next";

export type Chair = { seat: number; occupant_name: string | null; is_mine: boolean };
export type Table = { id: string; version: number; chairs: Chair[]; watchers: number };
export type Outcome = { kind: "table"; table: Table } | { kind: "missing" } | { kind: "failed" };

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
    if (!answer.ok) return { kind: "failed" };
    try {
        return { kind: "table", table: (await answer.json()) as Table };
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

export function readTable(id: string): Promise<Outcome> {
    return ask(`${TABLES_PATH}/${encodeURIComponent(id)}`);
}

// The reload of a table address is answered with the sign-in page while the session stays ended.
function signInAgain(id: string): void {
    const lastNavigation = Number(sessionStorage.getItem(RESIGN_IN_STORAGE_KEY));
    if (Date.now() - lastNavigation < RESIGN_IN_WINDOW_MILLISECONDS) {
        location.reload();
        return;
    }
    sessionStorage.setItem(RESIGN_IN_STORAGE_KEY, String(Date.now()));
    location.assign(`${AUTH_START_PATH}?${RETURN_QUERY_NAME}=${encodeURIComponent(tablePath(id))}`);
}

// A stream that ends is a refused session or a dropped connection; the table's own session check tells
// them apart. Only a 401 signs in again: a drop, or any other answer, leaves the stream to reconnect.
// The stream closes first: a page that keeps reconnecting would meet a second refusal while the sign-in
// navigation is still on its way, and the loop guard would cancel that navigation.
async function signInAgainWhenRefused(id: string, source: EventSource): Promise<void> {
    try {
        const answer = await fetch(`${TABLES_PATH}/${encodeURIComponent(id)}`);
        if (answer.status === SIGNED_OUT_STATUS) {
            source.close();
            signInAgain(id);
        }
    } catch {
        // The connection is down: the dimmed page and the stream's own reconnect carry on.
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
    const source = new EventSource(`${TABLES_PATH}/${encodeURIComponent(id)}${TABLE_EVENTS_SUFFIX}`);
    source.onmessage = (event: MessageEvent<string>) => {
        onConnection(true);
        onTable(JSON.parse(event.data) as Table);
    };
    source.onerror = () => {
        onConnection(false);
        void signInAgainWhenRefused(id, source);
    };
    return () => {
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

export async function copyTableLink(id: string): Promise<boolean> {
    try {
        await navigator.clipboard.writeText(`${location.origin}${tablePath(id)}`);
        return true;
    } catch {
        return false;
    }
}
