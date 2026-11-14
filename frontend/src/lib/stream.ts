// The page's one reader of a server-sent stream. It owns every reconnect: each failed source is closed at once,
// so the browser's own retry stays off, and the reader opens the next one itself. A stream that closes before it
// has stayed open for a heartbeat backs off like a failed open, however many messages it delivered. The browser
// hides why a stream failed, so the reader asks the stream's own address once after each failure: a refusal it
// learns that way is named to the page, and the ones that cannot pass on their own end the stream.

import { retryDelayMilliseconds } from "#lib/backoff.ts";
import { STREAM_HEARTBEAT_SECONDS } from "#lib/wire.ts";

// Why the server refused a stream: the session ended, no table has the id, or the account holds as many streams as
// it may. The first two end the stream; the third is retried, since a slot comes free.
export type StreamRefusal = "signedOut" | "notFound" | "tooMany";

const REFUSALS = new Map<number, StreamRefusal>([
    [401, "signedOut"],
    [404, "notFound"],
    [429, "tooMany"],
]);
const FINAL_REFUSALS: ReadonlySet<StreamRefusal> = new Set(["signedOut", "notFound"]);
const MILLISECONDS_PER_SECOND = 1_000;
// A stream is healthy once it has stayed open this long after its first message: the server sends a heartbeat
// within it, so a stream that survives it is not one that closes right after what it says first.
const HEALTHY_MILLISECONDS = STREAM_HEARTBEAT_SECONDS * MILLISECONDS_PER_SECOND;

export type StreamHandler = (data: string, end: () => void) => void;

export type StreamOptions = {
    // Handlers by event name; the stream's unnamed messages arrive under `message`.
    events: Record<string, StreamHandler>;
    onConnection: (connected: boolean) => void;
    // Called with the reason each time a failed stream is found refused; a signed-out or missing refusal is the
    // last call, and nothing reconnects after it.
    onRefused: (refusal: StreamRefusal) => void;
};

// The stream's own answer to a plain request: its status is all that is read, and the stream it may have opened is
// let go at once.
async function refusalOf(url: string): Promise<StreamRefusal | null> {
    const probe = new AbortController();
    try {
        const answer = await fetch(url, { signal: probe.signal });
        return REFUSALS.get(answer.status) ?? null;
    } catch {
        // The connection is down: the stream's own retry carries on.
        return null;
    } finally {
        probe.abort();
    }
}

// The returned function closes the stream for good: no reconnect, no check, and no visibility handling after it.
export function openStream(url: string, options: StreamOptions): () => void {
    let source: EventSource | null = null;
    let closed = false;
    let checking = false;
    let failedOpens = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;

    function end(): void {
        closed = true;
        clearTimeout(retry);
        if (source !== null) source.close();
        source = null;
        document.removeEventListener("visibilitychange", onVisibilityChange);
    }

    function open(): void {
        clearTimeout(retry);
        const opened = new EventSource(url);
        source = opened;
        let firstMessageAt: number | null = null;
        for (const [name, handle] of Object.entries(options.events)) {
            opened.addEventListener(name, (event) => {
                // The browser fires its own `open` event, with no data, when the connection is made; it proves nothing.
                if (!("data" in event)) return;
                firstMessageAt ??= Date.now();
                options.onConnection(true);
                handle((event as MessageEvent<string>).data, end);
            });
        }
        opened.onerror = () => {
            if (firstMessageAt !== null && Date.now() - firstMessageAt >= HEALTHY_MILLISECONDS) failedOpens = 0;
            fail(opened);
        };
    }

    function fail(failed: EventSource): void {
        if (closed) return;
        failed.close();
        source = null;
        options.onConnection(false);
        // A check in flight schedules the retry when it answers.
        if (checking) return;
        void checkThenRetry();
    }

    async function checkThenRetry(): Promise<void> {
        checking = true;
        const refusal = await refusalOf(url);
        checking = false;
        if (closed) return;
        if (refusal !== null) {
            const final = FINAL_REFUSALS.has(refusal);
            if (final) end();
            options.onRefused(refusal);
            if (final) return;
        }
        // A tab that became visible already opened a stream while this check ran.
        if (source !== null) return;
        retry = setTimeout(open, retryDelayMilliseconds(failedOpens));
        failedOpens += 1;
    }

    function onVisibilityChange(): void {
        if (document.visibilityState === "visible" && source === null) open();
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    open();
    return end;
}
