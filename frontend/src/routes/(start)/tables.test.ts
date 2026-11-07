import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_START_PATH, SIGNED_IN_AGAIN_QUERY_NAME, TABLES_PATH } from "#lib/wire.ts";
import { watchTable } from "./tables.ts";

class FakeEventSource {
    static last: FakeEventSource;
    onmessage: ((event: MessageEvent<string>) => void) | null = null;
    onerror: (() => void) | null = null;
    close = vi.fn();
    constructor(readonly url: string) {
        FakeEventSource.last = this;
    }
}

const TABLE_ID = "a".repeat(32);

describe("watchTable after a stream error", () => {
    const assign = vi.fn();
    const reload = vi.fn();
    let answers: ((status: number) => void)[];

    function location(search: string) {
        vi.stubGlobal("location", { assign, reload, search });
    }

    beforeEach(() => {
        assign.mockClear();
        reload.mockClear();
        answers = [];
        vi.stubGlobal("EventSource", FakeEventSource);
        vi.stubGlobal(
            "fetch",
            vi.fn(
                () =>
                    new Promise<Response>((resolve) =>
                        answers.push((status) => {
                            resolve(new Response(null, { status }));
                        }),
                    ),
            ),
        );
        vi.stubGlobal("performance", { now: () => 1_000 });
        location("");
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    function answer(index: number, status: number) {
        const respond = answers[index];
        if (respond === undefined) throw new Error(`no check ${String(index)} was asked`);
        respond(status);
    }

    function fail() {
        FakeEventSource.last.onerror?.();
    }

    async function settle() {
        await new Promise((resolve) => setTimeout(resolve, 0));
    }

    it("signs in once when two errors overlap and both checks answer 401", async () => {
        watchTable(TABLE_ID, vi.fn(), vi.fn());
        fail();
        fail();
        expect(answers).toHaveLength(1);

        answer(0, 401);
        await settle();

        expect(assign).toHaveBeenCalledTimes(1);
        expect(String(assign.mock.calls[0]?.[0])).toContain(AUTH_START_PATH);
        expect(reload).not.toHaveBeenCalled();
    });

    it("checks again after a check that found only a lost connection", async () => {
        watchTable(TABLE_ID, vi.fn(), vi.fn());
        fail();
        answer(0, 500);
        await settle();
        fail();
        answer(1, 401);
        await settle();

        expect(assign).toHaveBeenCalledTimes(1);
    });

    it("treats a failed check as a lost connection", async () => {
        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
        watchTable(TABLE_ID, vi.fn(), vi.fn());
        fail();
        await settle();

        expect(assign).not.toHaveBeenCalled();
        expect(reload).not.toHaveBeenCalled();
    });

    it("ignores a check that answers after the page stopped watching", async () => {
        const stop = watchTable(TABLE_ID, vi.fn(), vi.fn());
        fail();
        stop();
        answer(0, 401);
        await settle();

        expect(assign).not.toHaveBeenCalled();
        expect(FakeEventSource.last.close).toHaveBeenCalled();
    });

    it("ignores errors that come after the sign-in navigation started", async () => {
        watchTable(TABLE_ID, vi.fn(), vi.fn());
        fail();
        answer(0, 401);
        await settle();
        fail();

        expect(answers).toHaveLength(1);
    });

    it("reloads instead of navigating when the page was reached by signing in a moment ago", async () => {
        location(`?${SIGNED_IN_AGAIN_QUERY_NAME}=1`);
        watchTable(TABLE_ID, vi.fn(), vi.fn());
        fail();
        answer(0, 401);
        await settle();

        expect(reload).toHaveBeenCalledTimes(1);
        expect(assign).not.toHaveBeenCalled();
    });

    it("signs in again when the page reached by signing in has been open past the window", async () => {
        location(`?${SIGNED_IN_AGAIN_QUERY_NAME}=1`);
        vi.stubGlobal("performance", { now: () => 3_600_000 });
        watchTable(TABLE_ID, vi.fn(), vi.fn());
        fail();
        answer(0, 401);
        await settle();

        expect(assign).toHaveBeenCalledTimes(1);
    });

    it("hands messages to the page and marks the connection", () => {
        const onTable = vi.fn();
        const onConnection = vi.fn();
        watchTable(TABLE_ID, onTable, onConnection);
        FakeEventSource.last.onmessage?.({ data: JSON.stringify({ id: TABLE_ID }) } as MessageEvent<string>);

        expect(FakeEventSource.last.url).toContain(TABLES_PATH);
        expect(onTable).toHaveBeenCalledWith({ id: TABLE_ID });
        expect(onConnection).toHaveBeenCalledWith(true);
    });
});
