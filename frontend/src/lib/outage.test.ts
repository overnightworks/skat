import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startOutage, UNREACHABLE_AFTER_MILLISECONDS, type OutageState } from "./outage.ts";
import { VERSION_FILE_PATH } from "./wire.ts";

const BAD_GATEWAY = 502;
const ANSWERED = 200;

const visibility = {
    visibilityState: "visible" as "visible" | "hidden",
    listeners: new Set<() => void>(),
    addEventListener(_type: string, listener: () => void) {
        this.listeners.add(listener);
    },
    removeEventListener(_type: string, listener: () => void) {
        this.listeners.delete(listener);
    },
};

function turnTo(state: "visible" | "hidden") {
    visibility.visibilityState = state;
    for (const listener of visibility.listeners) listener();
}

// What the edge answers to each probe in turn; the last answer stands for every later probe.
function edgeAnswers(...statuses: (number | "refused")[]) {
    const probes: { at: number; path: string; options: RequestInit | undefined }[] = [];
    const fetchProbe = vi.fn((path: string, options?: RequestInit) => {
        probes.push({ at: Date.now(), path, options });
        const status = statuses[Math.min(probes.length, statuses.length) - 1];
        if (status === "refused" || status === undefined) return Promise.reject(new TypeError("network error"));
        return Promise.resolve(new Response(null, { status }));
    });
    vi.stubGlobal("fetch", fetchProbe);
    return probes;
}

function outage() {
    const states: OutageState[] = [];
    const retry = vi.fn(() => Promise.resolve());
    const end = startOutage({ retry, onState: (state) => states.push(state) });
    return { states, retry, end };
}

describe("startOutage", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        // Full jitter reads as the whole delay, so the gaps between probes are exact.
        vi.spyOn(Math, "random").mockReturnValue(1);
        visibility.visibilityState = "visible";
        visibility.listeners.clear();
        vi.stubGlobal("document", visibility);
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it("probes the version file without the cache at the shared backoff while the edge is away", async () => {
        const probes = edgeAnswers(BAD_GATEWAY);
        const started = Date.now();
        outage();

        await vi.advanceTimersByTimeAsync(1_000 + 2_000 + 4_000 + 8_000 + 16_000 + 30_000 + 30_000);

        expect(probes.map((probe) => probe.at - started)).toEqual([
            1_000, 3_000, 7_000, 15_000, 31_000, 61_000, 91_000,
        ]);
        expect(probes.every((probe) => probe.path === VERSION_FILE_PATH)).toBe(true);
        expect(probes.every((probe) => probe.options?.cache === "no-store")).toBe(true);
    });

    it("keeps waiting for a refused connection as for a 502 and never retries", async () => {
        edgeAnswers("refused", BAD_GATEWAY);
        const { retry, states } = outage();

        await vi.advanceTimersByTimeAsync(10_000);

        expect(retry).not.toHaveBeenCalled();
        expect(states).toEqual([]);
    });

    it("says unreachable once a minute has passed and not before", async () => {
        edgeAnswers(BAD_GATEWAY);
        const { states } = outage();

        await vi.advanceTimersByTimeAsync(UNREACHABLE_AFTER_MILLISECONDS - 1);
        expect(states).toEqual([]);
        await vi.advanceTimersByTimeAsync(1);

        expect(states).toEqual(["unreachable"]);
    });

    it("loads the route again once when the edge answers and then waits to see whether it loaded", async () => {
        const probes = edgeAnswers(BAD_GATEWAY, ANSWERED);
        const { retry, states } = outage();

        await vi.advanceTimersByTimeAsync(1_000 + 2_000);

        expect(retry).toHaveBeenCalledTimes(1);
        expect(probes).toHaveLength(2);
        expect(states).toEqual([]);
    });

    it("ends in the plain state and probes no more when the edge answers again though the route still fails", async () => {
        const probes = edgeAnswers(ANSWERED);
        const { retry, states } = outage();

        await vi.advanceTimersByTimeAsync(1_000 + 2_000);
        await vi.advanceTimersByTimeAsync(UNREACHABLE_AFTER_MILLISECONDS * 2);

        expect(states).toEqual(["failed"]);
        expect(retry).toHaveBeenCalledTimes(1);
        expect(probes).toHaveLength(2);
        expect(visibility.listeners.size).toBe(0);
    });

    it("loads the route again when the edge went away during the first load and answers a second time", async () => {
        edgeAnswers(ANSWERED, "refused", ANSWERED);
        const { retry, states } = outage();

        await vi.advanceTimersByTimeAsync(1_000 + 2_000 + 4_000);

        expect(retry).toHaveBeenCalledTimes(2);
        expect(states).toEqual([]);
    });

    it("probes at once when the tab becomes visible, and not when it is hidden", async () => {
        const probes = edgeAnswers(BAD_GATEWAY);
        outage();

        turnTo("hidden");
        await vi.advanceTimersByTimeAsync(0);
        expect(probes).toHaveLength(0);
        turnTo("visible");
        await vi.advanceTimersByTimeAsync(0);

        expect(probes).toHaveLength(1);
    });

    it("asks once when the tab becomes visible while a probe is in flight", async () => {
        const probes = edgeAnswers(BAD_GATEWAY);
        outage();

        turnTo("visible");
        turnTo("visible");
        await vi.advanceTimersByTimeAsync(0);

        expect(probes).toHaveLength(1);
    });

    it("spends the wait that was pending on the visible probe and waits again afterwards", async () => {
        const probes = edgeAnswers(BAD_GATEWAY);
        const started = Date.now();
        outage();

        await vi.advanceTimersByTimeAsync(500);
        turnTo("visible");
        await vi.advanceTimersByTimeAsync(2_000);

        expect(probes.map((probe) => probe.at - started)).toEqual([500, 2_500]);
    });

    it("stops everything when it ends: no probe, no unreachable, no listener", async () => {
        const probes = edgeAnswers(BAD_GATEWAY);
        const { states, end } = outage();

        end();
        await vi.advanceTimersByTimeAsync(UNREACHABLE_AFTER_MILLISECONDS * 2);

        expect(probes).toHaveLength(0);
        expect(states).toEqual([]);
        expect(visibility.listeners.size).toBe(0);
    });

    it("does nothing more when it ends while a probe is in flight", async () => {
        let answer: (response: Response) => void = () => undefined;
        vi.stubGlobal(
            "fetch",
            vi.fn(() => new Promise<Response>((resolve) => (answer = resolve))),
        );
        const { retry, end } = outage();

        await vi.advanceTimersByTimeAsync(1_000);
        end();
        answer(new Response(null, { status: ANSWERED }));
        await vi.advanceTimersByTimeAsync(UNREACHABLE_AFTER_MILLISECONDS);

        expect(retry).not.toHaveBeenCalled();
    });

    it("does nothing more when the route loaded and took the page away while it was loading", async () => {
        const probes = edgeAnswers(ANSWERED);
        const states: OutageState[] = [];
        let loaded: () => void = () => undefined;
        const end = startOutage({
            retry: () => new Promise<void>((resolve) => (loaded = resolve)),
            onState: (state) => states.push(state),
        });

        await vi.advanceTimersByTimeAsync(1_000);
        end();
        loaded();
        await vi.advanceTimersByTimeAsync(UNREACHABLE_AFTER_MILLISECONDS);

        expect(probes).toHaveLength(1);
        expect(states).toEqual([]);
    });
});
