import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_START_PATH, SIGNED_IN_AGAIN_QUERY_NAME, TABLES_PATH } from "#lib/wire.ts";
import { copyTableLink, createTable, drawingOrder, readTable, tablePath, type Chair } from "./tables.ts";

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
    // The marker is taken once per document, so each test loads the module afresh.
    let watchTable: typeof import("./tables.ts").watchTable;
    let readTableAfresh: typeof import("./tables.ts").readTable;
    const assign = vi.fn();
    const reload = vi.fn();
    let answers: ((status: number) => void)[];

    const replaceState = vi.fn();

    function location(search: string) {
        vi.stubGlobal("location", { assign, reload, href: `https://skat.test/t/${TABLE_ID}${search}` });
    }

    beforeEach(async () => {
        vi.resetModules();
        ({ watchTable, readTable: readTableAfresh } = await import("./tables.ts"));
        assign.mockClear();
        reload.mockClear();
        replaceState.mockClear();
        vi.stubGlobal("history", { state: null, replaceState });
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
        const reading = readTableAfresh(TABLE_ID);
        answer(0, 200);
        await reading;
        watchTable(TABLE_ID, vi.fn(), vi.fn());
        fail();
        answer(1, 401);
        await settle();

        expect(reload).toHaveBeenCalledTimes(1);
        expect(assign).not.toHaveBeenCalled();
    });

    it.each([
        ["a server error", 500],
        ["an ended session", 401],
        ["a table that does not exist", 404],
    ])("removes the marker from the address bar when the first read meets %s", async (_name, status) => {
        location(`?${SIGNED_IN_AGAIN_QUERY_NAME}=1&other=2`);
        const reading = readTableAfresh(TABLE_ID);
        answer(0, status);
        await reading;

        expect(replaceState).toHaveBeenCalledTimes(1);
        expect(String(replaceState.mock.calls[0]?.[2])).toBe(`https://skat.test/t/${TABLE_ID}?other=2`);
    });

    it("leaves the address alone when it carries no marker", () => {
        watchTable(TABLE_ID, vi.fn(), vi.fn());

        expect(replaceState).not.toHaveBeenCalled();
    });

    it("signs in again when the page reached by signing in has been open past the window", async () => {
        location(`?${SIGNED_IN_AGAIN_QUERY_NAME}=1`);
        vi.stubGlobal("performance", { now: () => 3_600_000 });
        const reading = readTableAfresh(TABLE_ID);
        answer(0, 200);
        await reading;
        watchTable(TABLE_ID, vi.fn(), vi.fn());
        fail();
        answer(1, 401);
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

describe("asking for a table", () => {
    const reload = vi.fn();
    const table = { id: TABLE_ID, version: 1, chairs: [], watchers: 0 };

    beforeEach(() => {
        reload.mockClear();
        vi.stubGlobal("location", { reload, href: `https://skat.test/t/${TABLE_ID}` });
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    function answerWith(response: Response | Error) {
        vi.stubGlobal(
            "fetch",
            response instanceof Error ? vi.fn().mockRejectedValue(response) : vi.fn().mockResolvedValue(response),
        );
    }

    it("returns the table that was answered", async () => {
        answerWith(Response.json(table));

        expect(await readTable(TABLE_ID)).toEqual({ kind: "table", table });
    });

    it("sends the command id when creating a table", async () => {
        answerWith(Response.json(table));
        await createTable("command-1");

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(TABLES_PATH);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-1" });
    });

    it("reloads to sign in again when the session ended", async () => {
        answerWith(new Response(null, { status: 401 }));

        expect(await readTable(TABLE_ID)).toEqual({ kind: "failed" });
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it("reports a table that does not exist as missing", async () => {
        answerWith(new Response(null, { status: 404 }));

        expect(await readTable(TABLE_ID)).toEqual({ kind: "missing" });
    });

    it.each([
        ["a server error", new Response(null, { status: 500 })],
        ["a body that is not a table", new Response("not json")],
        ["a lost connection", new TypeError("offline")],
    ])("reports %s as failed", async (_name, response) => {
        answerWith(response);

        expect(await readTable(TABLE_ID)).toEqual({ kind: "failed" });
    });
});

describe("the table's seats and link", () => {
    const chair = (seat: number, isMine = false): Chair => ({ seat, occupant_name: null, is_mine: isMine });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("draws the viewer's own chair last", () => {
        expect(drawingOrder([chair(0), chair(1, true), chair(2)]).map((each) => each.seat)).toEqual([2, 0, 1]);
    });

    it("keeps the order when no chair is the viewer's", () => {
        expect(drawingOrder([chair(0), chair(1)]).map((each) => each.seat)).toEqual([0, 1]);
    });

    it("copies the table's link to the clipboard", async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        vi.stubGlobal("navigator", { clipboard: { writeText } });
        vi.stubGlobal("location", { origin: "https://skat.test" });

        expect(await copyTableLink(TABLE_ID)).toBe(true);
        expect(writeText).toHaveBeenCalledWith(`https://skat.test${tablePath(TABLE_ID)}`);
    });

    it("reports a refused clipboard as not copied", async () => {
        vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
        vi.stubGlobal("location", { origin: "https://skat.test" });

        expect(await copyTableLink(TABLE_ID)).toBe(false);
    });
});
