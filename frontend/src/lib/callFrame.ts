import { isCallMode } from "#lib/callSignIn.ts";
import { CALL_ORIGIN_PATH, TABLE_ID_PATTERN } from "#lib/wire.ts";

// A call-mode address inside a frame is the table of a video call; the call shares it and the frame stays on it.
export function isFramedInCallMode(): boolean {
    return isCallMode(new URL(location.href).search) && window.self !== window.top;
}

/** The channel's version; both messages carry it as `v`, and a message with another one is ignored whole. */
export const CALL_CHANNEL_VERSION = 1;

const TABLE_ID = new RegExp(`^${TABLE_ID_PATTERN}$`);
const HELLO_KEYS: ReadonlySet<string> = new Set(["attachment", "attempt", "type", "v"]);
const OK_STATUS = 200;

/** What the table tells the call once, to the call's configured origin. */
export interface ReadyMessage {
    readonly v: typeof CALL_CHANNEL_VERSION;
    readonly type: "ready";
    readonly table: string;
}

/** What the call answers `ready` with. */
export interface HelloMessage {
    readonly v: typeof CALL_CHANNEL_VERSION;
    readonly type: "hello";
    readonly attachment: number;
    readonly attempt: null;
}

export interface CallMessageEvent {
    readonly source: unknown;
    readonly origin: string;
    readonly data: unknown;
}

export interface CallHost {
    readonly parent: unknown;
    fetch(path: string): Promise<Pick<Response, "status" | "json">>;
    post(message: ReadyMessage, targetOrigin: string): void;
    /** Calls `handler` for every message the page receives until the returned function is called. */
    listen(handler: (event: CallMessageEvent) => void): () => void;
}

/** The call's host in a browser page: the parent window, the page's fetch and its message channel. */
export function browserCallHost(): CallHost {
    return {
        parent: window.parent,
        fetch: (path) => fetch(path),
        post: (message, targetOrigin) => {
            window.parent.postMessage(message, targetOrigin);
        },
        listen: (handler) => {
            window.addEventListener("message", handler);
            return () => {
                window.removeEventListener("message", handler);
            };
        },
    };
}

function isPlainObject(data: unknown): data is Record<string, unknown> {
    return typeof data === "object" && data !== null && Object.getPrototypeOf(data) === Object.prototype;
}

/** The exact key set is the size bound: it is counted before any value is read. */
export function isHello(data: unknown): data is HelloMessage {
    if (!isPlainObject(data)) return false;
    const keys = Object.keys(data);
    if (keys.length !== HELLO_KEYS.size) return false;
    if (keys.some((key) => !HELLO_KEYS.has(key))) return false;
    const { v, type, attachment, attempt } = data;
    return (
        v === CALL_CHANNEL_VERSION &&
        type === "hello" &&
        typeof attachment === "number" &&
        Number.isSafeInteger(attachment) &&
        attachment >= 1 &&
        attempt === null
    );
}

/** The call's origin from the signed-in route; anything but a 200 naming one counts as no origin. */
export async function readCallOrigin(fetchRoute: CallHost["fetch"]): Promise<string | null> {
    try {
        const answer = await fetchRoute(CALL_ORIGIN_PATH);
        if (answer.status !== OK_STATUS) return null;
        const body: unknown = await answer.json();
        const origin = isPlainObject(body) ? body.origin : null;
        return typeof origin === "string" ? origin : null;
    } catch {
        return null;
    }
}

/**
 * Posts one `ready` to the call's origin and takes the first valid `hello` after it: `onGreeted` runs once and the
 * listener goes, so no later message is read. The returned function removes the listener for a page that leaves first.
 */
export function greetCall(tableId: string, host: CallHost, onGreeted: () => void): () => void {
    let callOrigin: string | null = null;
    let stopListening: (() => void) | null = null;
    const stop = (): void => {
        stopListening?.();
        stopListening = null;
    };
    stopListening = host.listen((event) => {
        // The origin check also holds the phase:
        // until the ready is posted callOrigin is null, which no event origin equals.
        if (event.source !== host.parent || event.origin !== callOrigin || !isHello(event.data)) {
            return;
        }
        stop();
        onGreeted();
    });
    void readCallOrigin(host.fetch.bind(host)).then((origin) => {
        if (origin === null || stopListening === null || !TABLE_ID.test(tableId)) return;
        callOrigin = origin;
        host.post({ v: CALL_CHANNEL_VERSION, type: "ready", table: tableId }, origin);
    });
    return stop;
}
