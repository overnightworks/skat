import { isCallMode } from "#lib/callSignIn.ts";
import { CALL_ORIGIN_PATH, CHAIRS_PER_TABLE, TABLE_ID_PATTERN } from "#lib/wire.ts";

// A call-mode address inside a frame is the table of a video call; the call shares it and the frame stays on it.
export function isFramedInCallMode(): boolean {
    return isCallMode(new URL(location.href).search) && window.self !== window.top;
}

/** The channel's version; both messages carry it as `v`, and a message with another one is ignored whole. */
export const CALL_CHANNEL_VERSION = 1;

const TABLE_ID = new RegExp(`^${TABLE_ID_PATTERN}$`);
/** A person key: 64 lowercase hex digits. */
export const PERSON_KEY = /^[0-9a-f]{64}$/;
const HELLO_KEYS: ReadonlySet<string> = new Set(["attachment", "attempt", "type", "v"]);
const PLACED_KEYS: ReadonlySet<string> = new Set(["keys", "table", "type", "v"]);
/** The chairs of a table; a `placed` names no more keys than that. */
const MOST_PLACED_KEYS = CHAIRS_PER_TABLE;
export const OK_STATUS = 200;

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

/** A tile's box in CSS px from the frame viewport's top-left, as the browser measured it. */
export interface Box {
    readonly x: number;
    readonly y: number;
    readonly w: number;
    readonly h: number;
}

/** The four corner radii of a rect tile, each finite and at least 0. */
export interface Corners {
    readonly tl: number;
    readonly tr: number;
    readonly br: number;
    readonly bl: number;
}

interface SeatPlace {
    readonly key: string;
    readonly box: Box;
}

/** One occupied chair: its person key, its tile's box and its shape; the corners are there for `rect` alone. */
export type SeatEntry =
    (SeatPlace & { readonly shape: "round" }) | (SeatPlace & { readonly shape: "rect"; readonly radius: Corners });

/** What the table tells the call after each valid hello and whenever a box changes. */
export interface SeatsMessage {
    readonly v: typeof CALL_CHANNEL_VERSION;
    readonly type: "seats";
    readonly table: string;
    readonly seats: readonly SeatEntry[];
}

/** What the call answers `seats` with, and sends unasked when a placement changes: always the full state. */
export interface PlacedMessage {
    readonly v: typeof CALL_CHANNEL_VERSION;
    readonly type: "placed";
    readonly table: string;
    readonly keys: readonly string[];
}

export interface CallMessageEvent {
    readonly source: unknown;
    readonly origin: string;
    readonly data: unknown;
}

export interface CallHost {
    readonly parent: unknown;
    fetch(path: string): Promise<Pick<Response, "status" | "json">>;
    post(message: ReadyMessage | SeatsMessage, targetOrigin: string): void;
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

export function isPlainObject(data: unknown): data is Record<string, unknown> {
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

/** The exact key set is the size bound, as for hello; `keys` holds at most one distinct person key per chair. */
export function isPlaced(data: unknown, tableId: string): data is PlacedMessage {
    if (!isPlainObject(data)) return false;
    const names = Object.keys(data);
    if (names.length !== PLACED_KEYS.size || names.some((name) => !PLACED_KEYS.has(name))) return false;
    const { v, type, table, keys } = data;
    return (
        v === CALL_CHANNEL_VERSION &&
        type === "placed" &&
        table === tableId &&
        Array.isArray(keys) &&
        keys.length <= MOST_PLACED_KEYS &&
        keys.every((key) => typeof key === "string" && PERSON_KEY.test(key)) &&
        new Set(keys).size === keys.length
    );
}

/** The call app's fixed start link for a table: its first tap starts the table's call and later taps join it. */
export function callStartAddress(callOrigin: string, tableId: string): string {
    const address = new URL("/c/new", callOrigin);
    address.searchParams.set("app", "skat");
    address.searchParams.set("context", tableId);
    return address.href;
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

/** What the page does with the call's messages. */
export interface CallListener {
    /** Runs for every valid hello; `first` is true for the first one of the page and false for each later one. */
    onHello(first: boolean): void;
    /** Runs for every valid `placed` with its keys. */
    onPlaced(keys: readonly string[]): void;
}

export interface CallChannel {
    /** Posts to the call's origin; before the page's `ready` there is none and nothing goes. */
    post(message: SeatsMessage): void;
    /** Removes the listener of a page that leaves. */
    stop(): void;
}

/**
 * Posts one `ready` to the call's origin and then reads its messages for the life of the page: every valid `hello` and
 * `placed` goes to `listener`. The returned channel posts the page's `seats` to the same origin and removes the
 * listener of a page that leaves.
 */
export function greetCall(tableId: string, host: CallHost, listener: CallListener): CallChannel {
    let callOrigin: string | null = null;
    let greeted = false;
    const stopListening = host.listen((event) => {
        // The origin check also holds the phase:
        // until the ready is posted callOrigin is null, which no event origin equals.
        if (event.source !== host.parent || event.origin !== callOrigin) return;
        if (isHello(event.data)) {
            listener.onHello(!greeted);
            greeted = true;
        } else if (isPlaced(event.data, tableId)) {
            listener.onPlaced(event.data.keys);
        }
    });
    let listening = true;
    void readCallOrigin(host.fetch.bind(host)).then((origin) => {
        if (origin === null || !listening || !TABLE_ID.test(tableId)) return;
        callOrigin = origin;
        host.post({ v: CALL_CHANNEL_VERSION, type: "ready", table: tableId }, origin);
    });
    return {
        post: (message) => {
            if (callOrigin !== null) host.post(message, callOrigin);
        },
        stop: () => {
            listening = false;
            stopListening();
        },
    };
}
