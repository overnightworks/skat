import type { AgentControlRefusal } from "overnightworks-design";
import { TABLE_AGENT_CALL_SUFFIX, TABLE_AGENT_SEND_AWAY_SUFFIX, TABLE_AGENTS_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import { CONFLICT_STATUS, fetchOrNull, fetchSigningInAgain, NOT_FOUND_STATUS } from "./tables.ts";

// One row of the control that calls agents. `key` is Skat's opaque key; an `inviting` row says in whole seconds on the
// server's clock how long its invitation stays open, and a `here` row is an agent seated at the table.
export type AgentRow =
    | { key: string; name: string; state: "available"; ends_in_seconds: null }
    | { key: string; name: string; state: "inviting"; ends_in_seconds: number }
    | { key: string; name: string; state: "here"; ends_in_seconds: null };
export type AgentsControl = { shown: boolean; rows: AgentRow[] };
type AgentsAnswer = { kind: "control"; control: AgentsControl } | { kind: "missing" } | { kind: "failed" };
type CallAnswer = AgentsAnswer | { kind: "refused"; reason: AgentControlRefusal };

const REFUSAL_REASONS: ReadonlySet<unknown> = new Set<AgentControlRefusal>([
    "not-allowed",
    "owner-absent",
    "place-full",
    "agent-unavailable",
    "try-again",
]);
// The next read of an `inviting` row is at least this long after the last, so a clock that runs ahead asks once more
// and never in a tight loop; a read that failed is asked again after the retry wait while a row is `inviting`.
const MINIMUM_REREAD_SECONDS = 1;
const FAILED_REREAD_MILLISECONDS = 5000;

function agentsPath(id: string): string {
    return `${TABLES_PATH}/${encodeURIComponent(id)}${TABLE_AGENTS_SUFFIX}`;
}

async function answerOfAgents(answer: Response | null): Promise<AgentsAnswer> {
    if (answer === null) return { kind: "failed" };
    if (answer.status === NOT_FOUND_STATUS) return { kind: "missing" };
    if (!answer.ok) return { kind: "failed" };
    try {
        return { kind: "control", control: (await answer.json()) as AgentsControl };
    } catch {
        // A body that could not be read or decoded is a failed answer, so the follower asks again.
        return { kind: "failed" };
    }
}

// A read never signs in again, a refused one is a failed answer: the page's stream owns that sign-in, and a read that
// races it would reload into the sign-in page instead of going through the issuer.
export async function readAgents(id: string): Promise<AgentsAnswer> {
    return answerOfAgents(await fetchOrNull(agentsPath(id)));
}

async function actOnAgent(id: string, key: string, suffix: string, init: RequestInit): Promise<CallAnswer> {
    const answer = await fetchSigningInAgain(`${agentsPath(id)}/${encodeURIComponent(key)}${suffix}`, init);
    if (answer?.status !== CONFLICT_STATUS) return answerOfAgents(answer);
    try {
        const body: unknown = await answer.json();
        const reason = typeof body === "object" && body !== null && "reason" in body ? body.reason : null;
        return REFUSAL_REASONS.has(reason)
            ? { kind: "refused", reason: reason as AgentControlRefusal }
            : { kind: "failed" };
    } catch {
        return { kind: "failed" };
    }
}

// The tap is the call: no command id, because the same call again changes nothing twice.
export function callAgent(id: string, key: string): Promise<CallAnswer> {
    return actOnAgent(id, key, TABLE_AGENT_CALL_SUFFIX, { method: "POST" });
}

// The command id is the retry key of the send-away: each tap brings its own, and nothing is retried.
export function sendAgentAway(id: string, key: string, commandId: string): Promise<CallAnswer> {
    return actOnAgent(id, key, TABLE_AGENT_SEND_AWAY_SUFFIX, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command_id: commandId }),
    });
}

// Seconds until the nearest `inviting` row's invitation ends on the server, never less than one; null with none.
export function rereadAfterSeconds(control: AgentsControl): number | null {
    const waits = control.rows.flatMap((row) => (row.state === "inviting" ? [row.ends_in_seconds] : []));
    return waits.length === 0 ? null : Math.max(MINIMUM_REREAD_SECONDS, Math.min(...waits));
}

export type AgentsFollower = {
    read: () => Promise<void>;
    call: (key: string) => Promise<void>;
    sendAway: (key: string) => Promise<void>;
    stop: () => void;
};

// Reads the control and follows it: while a row is `inviting`, it reads again after that row's own seconds, until no
// row is. The server's clock decides when an invitation ends; the page's clock only times the next read.
export function followAgents(
    id: string,
    onControl: (control: AgentsControl) => void,
    onRefusal: (reason: AgentControlRefusal | null) => void,
): AgentsFollower {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let inviting = false;
    let requests: Promise<unknown> = Promise.resolve();

    // One request at a time, its answer shown before the next request goes out: the server answers in the order the
    // page asked, so an older answer never replaces a newer one or restarts the timer of a row that has ended.
    function inOrder<T>(request: () => Promise<T>): Promise<T> {
        const answered = requests.then(request);
        requests = answered.catch(() => undefined);
        return answered;
    }

    function schedule(milliseconds: number | null): void {
        clearTimeout(timer);
        inviting = milliseconds !== null;
        if (milliseconds !== null) timer = setTimeout(() => void read(), milliseconds);
    }

    function show(answer: AgentsAnswer): void {
        if (answer.kind === "control") {
            onControl(answer.control);
            const seconds = rereadAfterSeconds(answer.control);
            schedule(seconds === null ? null : seconds * 1000);
        } else if (answer.kind === "failed" && inviting) {
            schedule(FAILED_REREAD_MILLISECONDS);
        }
    }

    function read(): Promise<void> {
        return inOrder(async () => {
            const answer = await readAgents(id);
            if (!stopped) show(answer);
        });
    }

    // A tap on a row: the refusal is cleared, the request goes in its turn, and a refused one is followed by a read.
    async function act(request: () => Promise<CallAnswer>): Promise<void> {
        onRefusal(null);
        const refused = await inOrder(async () => {
            const answer = await request();
            if (stopped) return false;
            if (answer.kind === "control" || answer.kind === "missing") {
                show(answer);
                return false;
            }
            onRefusal(answer.kind === "refused" ? answer.reason : "try-again");
            return true;
        });
        if (refused) await read();
    }

    return {
        read,
        call: (key) => act(() => callAgent(id, key)),
        sendAway: (key) => act(() => sendAgentAway(id, key, crypto.randomUUID())),
        stop: () => {
            stopped = true;
            clearTimeout(timer);
        },
    };
}
