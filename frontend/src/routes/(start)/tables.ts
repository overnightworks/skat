import { TABLE_PAGE_PREFIX, TABLES_PATH } from "#lib/wire.ts";

const SIGNED_OUT_STATUS = 401;
const NOT_FOUND_STATUS = 404;

export type Chair = { seat: number; occupant_name: string | null; is_mine: boolean };
export type Table = { id: string; version: number; chairs: Chair[] };
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
