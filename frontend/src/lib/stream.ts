// The page's one reader of a server-sent stream. It owns every reconnect: each failed source is closed at once,
// so the browser's own retry stays off, and the reader opens the next one itself. A stream that closes before it
// has stayed open for a heartbeat backs off like a failed open, however many messages it delivered.

import { retryDelayMilliseconds } from "#lib/backoff.ts";
import { STREAM_HEARTBEAT_SECONDS } from "#lib/wire.ts";

const SIGNED_OUT_STATUS = 401;
const MILLISECONDS_PER_SECOND = 1_000;
// A stream is healthy once it has stayed open this long after its first message: the server sends a heartbeat
// within it, so a stream that survives it is not one that closes right after what it says first.
const HEALTHY_MILLISECONDS = STREAM_HEARTBEAT_SECONDS * MILLISECONDS_PER_SECOND;

export type StreamHandler = (data: string, end: () => void) => void;

export type StreamOptions = {
    // Handlers by event name; the stream's unnamed messages arrive under `message`.
    events: Record<string, StreamHandler>;
    // Asked after a failed or ended stream: a 401 there means the session ended, so nothing reconnects.
    sessionPath: string;
    onConnection: (connected: boolean) => void;
    onRefused: () => void;
};

async function sessionIsRefused(sessionPath: string): Promise<boolean> {
    try {
        return (await fetch(sessionPath)).status === SIGNED_OUT_STATUS;
    } catch {
        // The connection is down: the stream's own retry carries on.
        return false;
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
        const refused = await sessionIsRefused(options.sessionPath);
        checking = false;
        if (closed) return;
        if (refused) {
            end();
            options.onRefused();
            return;
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
