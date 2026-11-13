import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { seriesAt } from "#lib/series.fixtures.ts";
import {
    AUTH_START_PATH,
    CALL_MODE,
    MODE_QUERY_NAME,
    SIGNED_IN_AGAIN_QUERY_NAME,
    RULE_SETS_PATH,
    SWITCH_ON_OPTIONS,
    TABLE_ABORT_AGREE_SUFFIX,
    TABLE_ABORT_REFUSE_SUFFIX,
    TABLE_CARD_SUFFIX,
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_LIST_SUFFIX,
    TABLE_NEW_SERIES_SUFFIX,
    TABLE_PUSHING_GRAND_HAND_SUFFIX,
    TABLE_PUSHING_PUSH_SUFFIX,
    TABLE_PUSHING_PUT_BACK_SUFFIX,
    TABLE_PUSHING_TAKE_SUFFIX,
    TABLE_READY_SUFFIX,
    TABLE_SERIES_END_AGREE_SUFFIX,
    TABLE_SERIES_END_REFUSE_SUFFIX,
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
    TABLE_SIT_SUFFIX,
    TABLE_CLOSE_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
} from "#lib/wire.ts";
import {
    answerAbort,
    answerGiveUp,
    answerSeriesEnd,
    createTable,
    giveUp,
    markReady,
    type OptionsRequest,
    playCard,
    readRuleSets,
    readSeriesList,
    readTable,
    seriesNumberOf,
    startNewSeries,
    sitDown,
    standUp,
    closeTable,
    takeDeclaringStep,
    takePushingStep,
    takeAuctionStep,
} from "./tables.ts";

class FakeEventSource {
    static last: FakeEventSource;
    onerror: (() => void) | null = null;
    private readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();
    close = vi.fn();
    constructor(readonly url: string) {
        FakeEventSource.last = this;
    }
    addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
        this.listeners.set(type, listener);
    }
    // A message as the browser hands it to the stream's unnamed listener.
    message(data: string) {
        this.listeners.get("message")?.({ data } as MessageEvent<string>);
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
        // The stream reader listens for the tab's visibility; these tests never change it.
        vi.stubGlobal("document", { addEventListener: vi.fn(), removeEventListener: vi.fn() });
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

    async function refuseAfterTheFirstRead() {
        const reading = readTableAfresh(TABLE_ID);
        answer(0, 200);
        await reading;
        watchTable(TABLE_ID, vi.fn(), vi.fn(), vi.fn());
        fail();
        answer(1, 401);
        await settle();
    }

    it("signs in once when two errors overlap and both checks answer 401", async () => {
        watchTable(TABLE_ID, vi.fn(), vi.fn(), vi.fn());
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
        watchTable(TABLE_ID, vi.fn(), vi.fn(), vi.fn());
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
        const stop = watchTable(TABLE_ID, vi.fn(), vi.fn(), vi.fn());
        fail();
        await settle();

        expect(assign).not.toHaveBeenCalled();
        expect(reload).not.toHaveBeenCalled();
        stop();
    });

    it("closes the stream on an ended view, hands it on once and ignores a later error", async () => {
        const onTable = vi.fn();
        const onConnection = vi.fn();
        watchTable(TABLE_ID, onTable, vi.fn(), onConnection);
        const ended = {
            id: TABLE_ID,
            ended: { reason: "empty", empty_seconds: 1800, unplayed_days: null, closed_by_name: null },
        };

        FakeEventSource.last.message(JSON.stringify(ended));
        fail();
        await settle();

        expect(FakeEventSource.last.close).toHaveBeenCalledOnce();
        expect(onTable).toHaveBeenCalledExactlyOnceWith(ended);
        expect(onConnection).not.toHaveBeenCalledWith(false);
        expect(answers).toHaveLength(0);
    });

    it("ignores a check that answers after the page stopped watching", async () => {
        const stop = watchTable(TABLE_ID, vi.fn(), vi.fn(), vi.fn());
        fail();
        stop();
        answer(0, 401);
        await settle();

        expect(assign).not.toHaveBeenCalled();
        expect(FakeEventSource.last.close).toHaveBeenCalled();
    });

    it("ignores errors that come after the sign-in navigation started", async () => {
        watchTable(TABLE_ID, vi.fn(), vi.fn(), vi.fn());
        fail();
        answer(0, 401);
        await settle();
        fail();

        expect(answers).toHaveLength(1);
    });

    it("reloads instead of navigating when the page was reached by signing in a moment ago", async () => {
        location(`?${SIGNED_IN_AGAIN_QUERY_NAME}=1`);
        await refuseAfterTheFirstRead();

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
        void readTableAfresh(TABLE_ID);

        expect(replaceState).not.toHaveBeenCalled();
    });

    it("signs in again when the page reached by signing in has been open past the window", async () => {
        location(`?${SIGNED_IN_AGAIN_QUERY_NAME}=1`);
        vi.stubGlobal("performance", { now: () => 3_600_000 });
        await refuseAfterTheFirstRead();

        expect(assign).toHaveBeenCalledTimes(1);
    });

    describe("in a frame", () => {
        const CALL_SEARCH = `?${MODE_QUERY_NAME}=${CALL_MODE}`;

        function frame(framed: boolean) {
            const top = {};
            vi.stubGlobal("window", { self: framed ? {} : top, top });
        }

        async function refuse() {
            watchTable(TABLE_ID, vi.fn(), vi.fn(), vi.fn());
            fail();
            answer(0, 401);
            await settle();
        }

        it("reloads and never navigates when a framed call-mode page is refused", async () => {
            frame(true);
            location(`${CALL_SEARCH}&${SIGNED_IN_AGAIN_QUERY_NAME}=1`);
            vi.stubGlobal("performance", { now: () => 3_600_000 });
            await refuseAfterTheFirstRead();

            expect(reload).toHaveBeenCalledTimes(1);
            expect(assign).not.toHaveBeenCalled();
        });

        it.each([
            ["a framed page without the call mode", true, ""],
            ["a top-level call-mode page", false, CALL_SEARCH],
        ])("signs in through the issuer for %s", async (_name, framed, search) => {
            frame(framed);
            location(search);
            await refuse();

            expect(assign).toHaveBeenCalledTimes(1);
            expect(reload).not.toHaveBeenCalled();
        });
    });

    it("hands messages to the page and marks the connection", () => {
        const onTable = vi.fn();
        const onConnection = vi.fn();
        watchTable(TABLE_ID, onTable, vi.fn(), onConnection);
        FakeEventSource.last.message(JSON.stringify({ id: TABLE_ID, ended: null }));

        expect(FakeEventSource.last.url).toContain(TABLES_PATH);
        expect(onTable).toHaveBeenCalledWith({ id: TABLE_ID, ended: null });
        expect(FakeEventSource.last.close).not.toHaveBeenCalled();
        expect(onConnection).toHaveBeenCalledWith(true);
    });
});

describe("asking for a table", () => {
    const reload = vi.fn();
    const table = {
        id: TABLE_ID,
        version: 1,
        chairs: [],
        watchers: 0,
        hand: null,
        passed_in: null,
        series: null,
        aborted: null,
        options: null,
        ended: null,
    };

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

    it("sends the command id and the series length when creating a table", async () => {
        answerWith(Response.json(table));
        await createTable("command-1", 30);

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(TABLES_PATH);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-1", series_length: 30 });
    });

    it("sends the options only when they are given", async () => {
        answerWith(Response.json(table));
        await createTable("command-1", 30, { show_running_points: true });

        const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(JSON.parse((init as { body: string }).body)).toEqual({
            command_id: "command-1",
            series_length: 30,
            options: { show_running_points: true },
        });
    });

    it("sends the request object as given when creating a table", async () => {
        answerWith(Response.json(table));
        const options: OptionsRequest = {
            kontra: { sayer: "any-opponent", reach: "kontra-re", deadline: "own-card" },
            bock: { triggers: ["sixty-sixty", "schneider"], overlap: "multiply" },
        };

        await createTable("command-1", 30, options);

        const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(JSON.parse((init as { body: string }).body)).toEqual({
            command_id: "command-1",
            series_length: 30,
            options,
        });
    });

    it("answers the sets of the person as the server lists them", async () => {
        const sets = [{ id: "set-1", name: "Felix", options: SWITCH_ON_OPTIONS }];
        answerWith(Response.json({ sets }));

        expect(await readRuleSets()).toEqual({ kind: "sets", sets });
        expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe(RULE_SETS_PATH);
    });

    it.each([
        ["a refusal", () => Response.json({}, { status: 500 })],
        ["an answer that is not JSON", () => new Response("<html>", { status: 200 })],
        ["an answer without a list", () => Response.json({})],
        ["no answer", () => new TypeError("offline")],
    ])("answers %s as failed, never as an empty list", async (_name, answer) => {
        answerWith(answer());

        expect(await readRuleSets()).toEqual({ kind: "failed" });
    });

    it("sends the command id and the chair when sitting down", async () => {
        answerWith(Response.json(table));

        expect(await sitDown(TABLE_ID, 2, "command-1")).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_SIT_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-1", seat: 2 });
    });

    it("sends only the command id when closing the table", async () => {
        answerWith(Response.json(table));

        expect(await closeTable(TABLE_ID, "command-3")).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_CLOSE_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-3" });
    });

    it("sends only the command id when standing up", async () => {
        answerWith(Response.json(table));

        expect(await standUp(TABLE_ID, "command-2")).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_STAND_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-2" });
    });

    it.each([
        { series: seriesAt({ number: 3 }), expected: 3 },
        { series: null, expected: 1 },
    ])("names series $expected for a table whose series is $series", ({ series, expected }) => {
        expect(seriesNumberOf({ series })).toBe(expected);
    });

    it("sends the command id, the result's ordinal and the series' number when ready", async () => {
        answerWith(Response.json(table));

        expect(await markReady(TABLE_ID, "command-3", 4, 2)).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_READY_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-3", ordinal: 4, series: 2 });
    });

    it.each([
        { step: { action: "take" } as const, suffix: TABLE_DECLARING_TAKE_SUFFIX, body: {} },
        {
            step: {
                action: "put_back",
                cards: [
                    { suit: "karo", rank: "seven" },
                    { suit: "herz", rank: "ace" },
                ],
            } as const,
            suffix: TABLE_DECLARING_PUT_BACK_SUFFIX,
            body: {
                cards: [
                    { suit: "karo", rank: "seven" },
                    { suit: "herz", rank: "ace" },
                ],
            },
        },
        {
            step: { action: "declare", game: "null", hand: false, ouvert: false, announcement: "none" } as const,
            suffix: TABLE_DECLARING_DECLARE_SUFFIX,
            body: { game: "null", hand: false, ouvert: false, announcement: "none" },
        },
        {
            step: { action: "declare", game: "herz", hand: true, ouvert: false, announcement: "schneider" } as const,
            suffix: TABLE_DECLARING_DECLARE_SUFFIX,
            body: { game: "herz", hand: true, ouvert: false, announcement: "schneider" },
        },
        {
            step: { action: "declare", game: "null", hand: false, ouvert: true, announcement: "none" } as const,
            suffix: TABLE_DECLARING_DECLARE_SUFFIX,
            body: { game: "null", hand: false, ouvert: true, announcement: "none" },
        },
    ])(
        "sends the shown version and a command id with the step $step.action to its own path",
        async ({ step, suffix, body }) => {
            answerWith(Response.json(table));

            expect(await takeDeclaringStep(TABLE_ID, 7, "command-3", step)).toEqual({ kind: "table", table });

            const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
            expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${suffix}`);
            expect(JSON.parse((init as { body: string }).body)).toEqual({
                command_id: "command-3",
                version: 7,
                ...body,
            });
        },
    );

    it.each([
        { step: { action: "take" } as const, suffix: TABLE_PUSHING_TAKE_SUFFIX, body: {} },
        {
            step: {
                action: "put_back",
                cards: [
                    { suit: "karo", rank: "seven" },
                    { suit: "herz", rank: "ace" },
                ],
            } as const,
            suffix: TABLE_PUSHING_PUT_BACK_SUFFIX,
            body: {
                cards: [
                    { suit: "karo", rank: "seven" },
                    { suit: "herz", rank: "ace" },
                ],
            },
        },
        { step: { action: "push" } as const, suffix: TABLE_PUSHING_PUSH_SUFFIX, body: {} },
        { step: { action: "grand_hand" } as const, suffix: TABLE_PUSHING_GRAND_HAND_SUFFIX, body: {} },
    ])(
        "sends the shown version and a command id with the pushing step $step.action to its own path",
        async ({ step, suffix, body }) => {
            answerWith(Response.json(table));

            expect(await takePushingStep(TABLE_ID, 7, "command-3", step)).toEqual({ kind: "table", table });

            const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
            expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${suffix}`);
            expect(JSON.parse((init as { body: string }).body)).toEqual({
                command_id: "command-3",
                version: 7,
                ...body,
            });
        },
    );

    it.each([
        { action: "bid", value: 20, suffix: TABLE_AUCTION_BID_SUFFIX, body: { value: 20 } },
        { action: "hold", value: undefined, suffix: TABLE_AUCTION_HOLD_SUFFIX, body: {} },
        { action: "pass", value: undefined, suffix: TABLE_AUCTION_PASS_SUFFIX, body: {} },
        { action: "play", value: undefined, suffix: TABLE_AUCTION_PLAY_SUFFIX, body: {} },
    ] as const)(
        "sends the version shown with a $action step to its own path",
        async ({ action, value, suffix, body }) => {
            answerWith(Response.json(table));

            expect(await takeAuctionStep(TABLE_ID, "command-3", 7, action, value)).toEqual({ kind: "table", table });

            const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
            expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${suffix}`);
            expect(JSON.parse((init as { body: string }).body)).toEqual({
                command_id: "command-3",
                version: 7,
                ...body,
            });
        },
    );

    it("sends the version shown, a command id and only the card when playing a card", async () => {
        answerWith(Response.json(table));

        expect(await playCard(TABLE_ID, 7, "command-4", { suit: "pik", rank: "queen" })).toEqual({
            kind: "table",
            table,
        });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_CARD_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({
            command_id: "command-4",
            version: 7,
            suit: "pik",
            rank: "queen",
        });
    });

    it("sends the version shown and a command id to give up the game", async () => {
        answerWith(Response.json(table));

        expect(await giveUp(TABLE_ID, 7, "command-5")).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_GIVE_UP_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-5", version: 7 });
    });

    it.each([
        { answer: "agree" as const, suffix: TABLE_GIVE_UP_AGREE_SUFFIX },
        { answer: "decline" as const, suffix: TABLE_GIVE_UP_DECLINE_SUFFIX },
    ])("sends the version shown and a command id to $answer a give-up", async ({ answer, suffix }) => {
        answerWith(Response.json(table));

        expect(await answerGiveUp(TABLE_ID, 7, "command-5", answer)).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${suffix}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-5", version: 7 });
    });

    it.each([
        { answer: "agree" as const, suffix: TABLE_ABORT_AGREE_SUFFIX },
        { answer: "refuse" as const, suffix: TABLE_ABORT_REFUSE_SUFFIX },
    ])("sends a command id and no version to $answer aborting the hand", async ({ answer, suffix }) => {
        answerWith(Response.json(table));

        expect(await answerAbort(TABLE_ID, "command-6", answer)).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${suffix}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-6" });
    });

    it("sends the command id and the series' number when starting the next series", async () => {
        answerWith(Response.json(table));

        expect(await startNewSeries(TABLE_ID, "command-7", 2)).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_NEW_SERIES_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-7", series: 2 });
    });

    it.each([
        { answer: "agree", suffix: TABLE_SERIES_END_AGREE_SUFFIX },
        { answer: "refuse", suffix: TABLE_SERIES_END_REFUSE_SUFFIX },
    ] as const)("sends the command id alone to $suffix", async ({ answer, suffix }) => {
        answerWith(Response.json(table));

        expect(await answerSeriesEnd(TABLE_ID, "command-8", answer)).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${suffix}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-8" });
    });

    it("reads the series' list in the order played", async () => {
        answerWith(Response.json({ entries: [{ kind: "ramsch", number: 1 }] }));

        expect(await readSeriesList(TABLE_ID)).toEqual([{ kind: "ramsch", number: 1 }]);
        expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_LIST_SUFFIX}`);
    });

    it.each([
        ["a refusal", new Response(null, { status: 404 })],
        ["an answer that is no list", new Response("<html>", { status: 200 })],
        ["no answer", new Error("offline")],
    ])("reads no list from %s", async (_name, response) => {
        answerWith(response);

        expect(await readSeriesList(TABLE_ID)).toBeNull();
    });

    it("reports a taken chair with who holds it", async () => {
        answerWith(Response.json({ reason: "seat-taken", holder_name: "Anna" }, { status: 409 }));

        expect(await sitDown(TABLE_ID, 1, "command-1")).toEqual({
            kind: "taken",
            holder: "Anna",
        });
    });

    it.each([
        ["a command id that came back with another request", Response.json({ detail: "reused" }, { status: 409 })],
        ["a conflict without a body", new Response(null, { status: 409 })],
        ["a conflict with a null body", Response.json(null, { status: 409 })],
        ["a conflict with a bare text", Response.json("conflict", { status: 409 })],
        ["a stand-up refused because nobody sat", Response.json({ reason: "not-seated" }, { status: 409 })],
    ])("reports %s as failed", async (_name, response) => {
        answerWith(response);

        expect(await standUp(TABLE_ID, "command-1")).toEqual({ kind: "failed" });
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
