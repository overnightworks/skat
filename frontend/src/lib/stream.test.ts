import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { openStream, type StreamOptions } from "./stream.ts";
import { STREAM_HEARTBEAT_SECONDS } from "#lib/wire.ts";

const STREAM_PATH = "/api/things/a/events";
const SESSION_PATH = "/api/things/a";
const SIGNED_OUT = 401;
const LOST_CONNECTION = 500;
const HEARTBEAT_MILLISECONDS = STREAM_HEARTBEAT_SECONDS * 1000;

class FakeEventSource {
    static opened: FakeEventSource[] = [];
    static openedAt: number[] = [];
    onerror: (() => void) | null = null;
    readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();
    close = vi.fn();
    constructor(readonly url: string) {
        FakeEventSource.opened.push(this);
        FakeEventSource.openedAt.push(Date.now());
    }
    addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
        this.listeners.set(type, listener);
    }
    send(type: string, data: string) {
        this.listeners.get(type)?.({ data } as MessageEvent<string>);
    }
    fail() {
        this.onerror?.();
    }
}

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

function latest(): FakeEventSource {
    const source = FakeEventSource.opened.at(-1);
    if (source === undefined) throw new Error("no stream was opened");
    return source;
}

// The browser's error for a stream that failed; the check's answer arrives on the next microtasks.
async function failLatest() {
    latest().fail();
    await vi.advanceTimersByTimeAsync(0);
}

function optionsWith(overrides: Partial<StreamOptions> = {}): StreamOptions {
    return {
        events: {},
        sessionPath: SESSION_PATH,
        onConnection: vi.fn(),
        onRefused: vi.fn(),
        ...overrides,
    };
}

describe("openStream", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        // Full jitter reads as the whole delay, so the gaps between opens are exact.
        vi.spyOn(Math, "random").mockReturnValue(1);
        FakeEventSource.opened = [];
        FakeEventSource.openedAt = [];
        visibility.visibilityState = "visible";
        visibility.listeners.clear();
        vi.stubGlobal("EventSource", FakeEventSource);
        vi.stubGlobal("document", visibility);
        vi.stubGlobal(
            "fetch",
            vi.fn(() => Promise.resolve(new Response(null, { status: LOST_CONNECTION }))),
        );
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it("opens the stream at once and hands each named event to its handler after the connection is marked", () => {
        const handled: string[] = [];
        const onConnection = vi.fn();
        openStream(
            STREAM_PATH,
            optionsWith({
                events: {
                    message: (data) => handled.push(`message ${data}`),
                    mine: (data) => handled.push(`mine ${data}`),
                },
                onConnection,
            }),
        );

        latest().send("message", "a");
        latest().send("mine", "b");

        expect(FakeEventSource.opened.map((source) => source.url)).toEqual([STREAM_PATH]);
        expect(handled).toEqual(["message a", "mine b"]);
        expect(onConnection.mock.calls).toEqual([[true], [true]]);
    });

    it("retries a failed open after a delay that doubles from one second and stops growing at thirty", async () => {
        const onConnection = vi.fn();
        openStream(STREAM_PATH, optionsWith({ onConnection }));

        for (let failure = 0; failure < 7; failure += 1) {
            await failLatest();
            await vi.runOnlyPendingTimersAsync();
        }

        const gaps = FakeEventSource.openedAt.slice(1).map((at, index) => at - (FakeEventSource.openedAt[index] ?? 0));
        expect(gaps).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000]);
        expect(onConnection).toHaveBeenLastCalledWith(false);
    });

    function gapsBetweenOpens(): number[] {
        return FakeEventSource.openedAt.slice(1).map((at, index) => at - (FakeEventSource.openedAt[index] ?? 0));
    }

    it("backs off a stream that closes right after its first message like a failed open, up to the ceiling", async () => {
        openStream(STREAM_PATH, optionsWith({ events: { message: vi.fn() } }));

        for (let failure = 0; failure < 7; failure += 1) {
            latest().send("message", "view");
            await failLatest();
            await vi.runOnlyPendingTimersAsync();
        }

        expect(gapsBetweenOpens()).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000]);
    });

    it("backs off a stream that dropped just short of one heartbeat after its first message", async () => {
        openStream(STREAM_PATH, optionsWith({ events: { message: vi.fn() } }));

        const almostOneHeartbeat = HEARTBEAT_MILLISECONDS - 1;
        for (let failure = 0; failure < 2; failure += 1) {
            latest().send("message", "view");
            await vi.advanceTimersByTimeAsync(almostOneHeartbeat);
            await failLatest();
            await vi.runOnlyPendingTimersAsync();
        }

        expect(gapsBetweenOpens()).toEqual([almostOneHeartbeat + 1000, almostOneHeartbeat + 2000]);
    });

    it("reconnects from the first delay when a stream that stayed open past a heartbeat drops, whatever came before", async () => {
        openStream(STREAM_PATH, optionsWith({ events: { message: vi.fn() } }));
        for (let failure = 0; failure < 3; failure += 1) {
            latest().send("message", "view");
            await failLatest();
            await vi.runOnlyPendingTimersAsync();
        }
        latest().send("message", "view");
        await vi.advanceTimersByTimeAsync(HEARTBEAT_MILLISECONDS);
        await failLatest();
        await vi.runOnlyPendingTimersAsync();

        expect(gapsBetweenOpens().slice(3)).toEqual([HEARTBEAT_MILLISECONDS + 1000]);
    });

    it("does not count a stream that stayed open without a message as healthy", async () => {
        openStream(STREAM_PATH, optionsWith({ events: { message: vi.fn() } }));
        await failLatest();
        await vi.runOnlyPendingTimersAsync();
        await vi.advanceTimersByTimeAsync(HEARTBEAT_MILLISECONDS);
        await failLatest();
        await vi.runOnlyPendingTimersAsync();

        expect(gapsBetweenOpens()).toEqual([1000, HEARTBEAT_MILLISECONDS + 2000]);
    });

    it("marks the connection lost at every drop, also of a stream that delivered messages", async () => {
        const onConnection = vi.fn();
        openStream(STREAM_PATH, optionsWith({ events: { message: vi.fn() }, onConnection }));

        latest().send("message", "view");
        await failLatest();

        expect(onConnection.mock.calls).toEqual([[true], [false]]);
    });

    it("counts a check that cannot reach the server as a lost connection and retries", async () => {
        vi.mocked(fetch).mockRejectedValueOnce(new TypeError("offline"));
        openStream(STREAM_PATH, optionsWith());

        await failLatest();
        await vi.advanceTimersByTimeAsync(1000);

        expect(FakeEventSource.opened).toHaveLength(2);
    });

    it("ends the stream on a 401 with the sign-in hand-over and never opens again", async () => {
        vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: SIGNED_OUT }));
        const onRefused = vi.fn();
        const onConnection = vi.fn();
        openStream(STREAM_PATH, optionsWith({ onRefused, onConnection }));

        await failLatest();
        await vi.advanceTimersByTimeAsync(60_000);

        expect(FakeEventSource.opened).toHaveLength(1);
        expect(onRefused).toHaveBeenCalledOnce();
        expect(onConnection).toHaveBeenLastCalledWith(false);
    });

    it("reconnects at once when the tab becomes visible again and not before", async () => {
        openStream(STREAM_PATH, optionsWith());
        turnTo("hidden");
        await failLatest();
        turnTo("hidden");

        expect(FakeEventSource.opened).toHaveLength(1);

        turnTo("visible");

        expect(FakeEventSource.opened).toHaveLength(2);
        await vi.advanceTimersByTimeAsync(60_000);
        expect(FakeEventSource.opened).toHaveLength(2);
    });

    it("leaves an open stream alone when the tab becomes visible", () => {
        openStream(STREAM_PATH, optionsWith());

        turnTo("visible");

        expect(FakeEventSource.opened).toHaveLength(1);
    });

    it("does not open a second stream when a check answers after the tab already reconnected", async () => {
        let answerCheck: (answer: Response) => void = () => {};
        vi.mocked(fetch).mockReturnValueOnce(new Promise<Response>((resolve) => (answerCheck = resolve)));
        openStream(STREAM_PATH, optionsWith());
        latest().fail();
        turnTo("visible");

        answerCheck(new Response(null, { status: LOST_CONNECTION }));
        await vi.advanceTimersByTimeAsync(60_000);

        expect(FakeEventSource.opened).toHaveLength(2);
    });

    it("stops everything when closed: no reconnect, no check and no tab listener", async () => {
        const stop = openStream(STREAM_PATH, optionsWith());
        await failLatest();

        stop();
        await vi.advanceTimersByTimeAsync(60_000);
        turnTo("visible");
        latest().fail();
        await vi.advanceTimersByTimeAsync(0);

        expect(FakeEventSource.opened).toHaveLength(1);
        expect(fetch).toHaveBeenCalledOnce();
        expect(visibility.listeners.size).toBe(0);
    });

    it("closes the open source when closed", () => {
        const stop = openStream(STREAM_PATH, optionsWith());

        stop();

        expect(latest().close).toHaveBeenCalledOnce();
    });

    it("drops a check that answers after the stream was closed", async () => {
        let answerCheck: (answer: Response) => void = () => {};
        vi.mocked(fetch).mockReturnValueOnce(new Promise<Response>((resolve) => (answerCheck = resolve)));
        const stop = openStream(STREAM_PATH, optionsWith());
        latest().fail();
        stop();

        answerCheck(new Response(null, { status: LOST_CONNECTION }));
        await vi.advanceTimersByTimeAsync(60_000);

        expect(FakeEventSource.opened).toHaveLength(1);
    });

    it("lets a handler end the stream from inside its message, with no check after the close", async () => {
        openStream(
            STREAM_PATH,
            optionsWith({
                events: {
                    message: (_data, end) => {
                        end();
                    },
                },
            }),
        );

        latest().send("message", "ended");
        await failLatest();

        expect(latest().close).toHaveBeenCalledOnce();
        expect(fetch).not.toHaveBeenCalled();
    });
});
