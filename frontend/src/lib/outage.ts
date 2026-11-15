// The page that stands in for a route whose code could not load, while the edge in front of Skat answers nothing
// useful: it asks the version file whether the edge answers again, loads the route again when it does, and tells
// the page what to show meanwhile.

import { retryDelayMilliseconds } from "#lib/backoff.ts";
import { VERSION_FILE_PATH } from "#lib/wire.ts";

export const UNREACHABLE_AFTER_MILLISECONDS = 60_000;
const ANSWERED_STATUS = 200;

// The page starts as `reconnecting`. `failed` means the edge answers and the route still fails: a real error.
export type OutageState = "reconnecting" | "unreachable" | "failed";

export type OutageOptions = {
    // The address of the route that failed: the page that stands in for it can be built again by every load of it that
    // fails, and the address is what the next one finds the earlier retry by.
    address: string;
    // Loads the route again; it resolves when the navigation is done, with whether the route loaded.
    retry: () => Promise<boolean>;
    onState: (state: OutageState) => void;
};

// The addresses whose route was loaded again after the edge answered and has not loaded since: a failing load builds the
// stand-in page anew, and the new one must not start the same retry over.
const retriedAddresses = new Set<string>();

async function edgeAnswers(): Promise<boolean> {
    try {
        return (await fetch(VERSION_FILE_PATH, { cache: "no-store" })).status === ANSWERED_STATUS;
    } catch {
        // The connection is down: the edge is still away.
        return false;
    }
}

// The returned function ends it for good: no probe, no state and no visibility handling after it.
export function startOutage(options: OutageOptions): () => void {
    let ended = false;
    let asking = false;
    let waits = 0;
    let wait: ReturnType<typeof setTimeout> | undefined;
    const minute = setTimeout(() => {
        options.onState("unreachable");
    }, UNREACHABLE_AFTER_MILLISECONDS);

    function end(): void {
        ended = true;
        clearTimeout(wait);
        clearTimeout(minute);
        document.removeEventListener("visibilitychange", onVisibilityChange);
    }

    function waitThenAsk(): void {
        // A route that loaded took this page away and ended it.
        if (ended) return;
        wait = setTimeout(() => void ask(), retryDelayMilliseconds(waits));
        waits += 1;
    }

    async function ask(): Promise<void> {
        if (asking) return;
        asking = true;
        clearTimeout(wait);
        try {
            const answered = await edgeAnswers();
            if (ended) return;
            if (!answered) {
                retriedAddresses.delete(options.address);
            } else if (retriedAddresses.has(options.address)) {
                // The edge answered before and answers now, and the route still fails: nothing here heals it.
                end();
                options.onState("failed");
                return;
            } else {
                retriedAddresses.add(options.address);
                if (await options.retry()) retriedAddresses.delete(options.address);
            }
        } finally {
            asking = false;
        }
        waitThenAsk();
    }

    function onVisibilityChange(): void {
        if (document.visibilityState === "visible") void ask();
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    waitThenAsk();
    return end;
}
