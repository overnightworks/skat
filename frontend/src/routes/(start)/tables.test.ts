import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
    AUTH_START_PATH,
    SIGNED_IN_AGAIN_QUERY_NAME,
    TABLE_CARD_SUFFIX,
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
    TABLE_READY_SUFFIX,
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
} from "#lib/wire.ts";
import {
    bidValueWhileDeclaring,
    announcedWord,
    cardName,
    copyTableLink,
    createTable,
    declarerStage,
    drawingOrder,
    gameLabel,
    gameWord,
    isSuitGame,
    markReady,
    playCard,
    positionWord,
    readTable,
    sitDown,
    standUp,
    tablePath,
    takeDeclaringStep,
    togglePicked,
    type Auction,
    type Card,
    takeAuctionStep,
    type Chair,
    type Declaring,
    type Game,
    type Position,
    type Stage,
    type Table,
} from "./tables.ts";
import { words } from "#lib/words.ts";

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

const auctionWith = (declared: Auction["declared"]): Auction => ({
    turn_seat: null,
    facing_seat: null,
    awaiting: null,
    standing: null,
    values: [],
    words: [],
    declared,
});

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
        void readTableAfresh(TABLE_ID);

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
    const table = { id: TABLE_ID, version: 1, chairs: [], watchers: 0, hand: null, passed_in: null };

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

    it("sends the command id and the chair when sitting down", async () => {
        answerWith(Response.json(table));

        expect(await sitDown(TABLE_ID, 2, "command-1")).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_SIT_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-1", seat: 2 });
    });

    it("sends only the command id when standing up", async () => {
        answerWith(Response.json(table));

        expect(await standUp(TABLE_ID, "command-2")).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_STAND_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-2" });
    });

    it("sends the command id and the result's ordinal when ready", async () => {
        answerWith(Response.json(table));

        expect(await markReady(TABLE_ID, "command-3", 4)).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_READY_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-3", ordinal: 4 });
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

describe("what the declaring stage asks of this viewer", () => {
    const seats = (mine: number): Chair[] =>
        [1, 2, 3].map((seat) => ({
            seat,
            occupant_name: `player ${String(seat)}`,
            is_mine: seat === mine,
            is_away: false,
            ready: false,
            total: null,
            hand: null,
        }));
    const bidWon = { seat: 2, value: 20 };
    const tableWith = (declaring: Declaring | null, mine: number): Table => ({
        id: TABLE_ID,
        version: 1,
        chairs: seats(mine),
        watchers: 0,
        result: null,
        passed_in: null,
        hand: { dealer_seat: 1, own_cards: [], skat_count: 2, auction: auctionWith(bidWon), declaring, playing: null },
    });
    const tableAt = (stage: Stage, mine: number): Table =>
        tableWith({ declarer_seat: 2, stage, declaration: null, open_cards: [] }, mine);

    it.each<Stage>(["choosing", "discarding", "picked"])("asks the declarer to act at %s", (stage) => {
        expect(declarerStage(tableAt(stage, 2))).toBe(stage);
    });

    it("asks the declarer nothing once the game is declared", () => {
        expect(declarerStage(tableAt("declared", 2))).toBeNull();
    });

    it("asks nothing of a chair that did not win the auction", () => {
        expect(declarerStage(tableAt("choosing", 3))).toBeNull();
    });

    it("asks nothing of a person with no chair", () => {
        expect(declarerStage(tableAt("choosing", 0))).toBeNull();
    });

    it("asks nothing before the auction is over", () => {
        expect(declarerStage(tableWith(null, 2))).toBeNull();
    });

    it("asks nothing with no hand on the table", () => {
        expect(declarerStage({ ...tableAt("choosing", 2), hand: null })).toBeNull();
    });
});

describe("the auction's value while declaring", () => {
    const table = (declaring: Declaring | null, declared: Auction["declared"]): Table => ({
        id: TABLE_ID,
        version: 1,
        chairs: [],
        watchers: 0,
        result: null,
        passed_in: null,
        hand: {
            dealer_seat: 1,
            own_cards: [],
            skat_count: 2,
            auction: auctionWith(declared),
            declaring,
            playing: null,
        },
    });

    it.each<Stage>(["choosing", "discarding", "picked"])("is shown at %s", (stage) => {
        expect(
            bidValueWhileDeclaring(
                table({ declarer_seat: 2, stage, declaration: null, open_cards: [] }, { seat: 2, value: 20 }),
            ),
        ).toBe(20);
    });

    it.each([
        [
            "once the game is declared",
            {
                declarer_seat: 2,
                stage: "declared" as const,
                declaration: { game: "null" as const, hand: false, ouvert: false, announcement: "none" as const },
                open_cards: [],
            },
            { seat: 2, value: 20 },
        ],
        ["before the auction is over", null, null],
        [
            "with no value won",
            { declarer_seat: 2, stage: "choosing" as const, declaration: null, open_cards: [] },
            null,
        ],
    ])("is not shown %s", (_name, declaring, declared) => {
        expect(bidValueWhileDeclaring(table(declaring, declared))).toBeNull();
    });

    it("is not shown with no hand on the table", () => {
        expect(bidValueWhileDeclaring({ ...table(null, null), hand: null })).toBeNull();
    });
});

describe("picking two cards from the twelve", () => {
    const seven: Card = { suit: "karo", rank: "seven" };
    const eight: Card = { suit: "karo", rank: "eight" };
    const nine: Card = { suit: "karo", rank: "nine" };

    it("picks a card that was not picked", () => {
        expect(togglePicked([seven], eight)).toEqual([seven, eight]);
    });

    it("puts a picked card back", () => {
        expect(togglePicked([seven, eight], seven)).toEqual([eight]);
    });

    it("does not pick a third card while two are picked", () => {
        expect(togglePicked([seven, eight], nine)).toEqual([seven, eight]);
    });
});

describe("the table's seats and link", () => {
    const chair = (seat: number, isMine = false): Chair => ({
        seat,
        occupant_name: null,
        is_mine: isMine,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("draws the viewer's own chair last", () => {
        expect(drawingOrder([chair(0), chair(1, true), chair(2)]).map((each) => each.seat)).toEqual([2, 0, 1]);
    });

    it("keeps the order when no chair is the viewer's", () => {
        expect(drawingOrder([chair(0), chair(1)]).map((each) => each.seat)).toEqual([0, 1]);
    });

    it.each([
        ["forehand", words.forehand],
        ["middlehand", words.middlehand],
        ["rearhand", words.rearhand],
    ] as [Position, string][])("names the position %s with its word", (position, word) => {
        expect(positionWord(position)).toBe(word);
    });

    it.each([
        ["karo", words.gameKaro],
        ["herz", words.gameHerz],
        ["pik", words.gamePik],
        ["kreuz", words.gameKreuz],
        ["grand", words.gameGrand],
        ["null", words.gameNull],
    ] as [Game, string][])("names the game %s with its word", (game, word) => {
        expect(gameWord(game)).toBe(word);
    });

    it.each([
        ["a plain game", "grand", false, false, "none", words.gameGrand, null],
        ["a Hand game", "grand", true, false, "none", `${words.gameGrand} ${words.hand}`, null],
        [
            "an ouvert game, which includes Hand",
            "grand",
            true,
            true,
            "schwarz",
            `${words.gameGrand} ${words.ouvert}`,
            null,
        ],
        ["Null ouvert after the take", "null", false, true, "none", `${words.gameNull} ${words.ouvert}`, null],
        ["Null ouvert Hand", "null", true, true, "none", `${words.gameNull} ${words.ouvert} ${words.hand}`, null],
        [
            "a Hand game with Schneider announced",
            "herz",
            true,
            false,
            "schneider",
            `${words.gameHerz} ${words.hand}`,
            words.announcedSchneider,
        ],
        [
            "a Hand game with Schwarz announced",
            "grand",
            true,
            false,
            "schwarz",
            `${words.gameGrand} ${words.hand}`,
            words.announcedSchwarz,
        ],
    ] as const)("labels %s", (_name, game, hand, ouvert, announcement, name, announced) => {
        expect(gameLabel({ game, hand, ouvert, announcement })).toEqual({ name, announcement: announced });
    });

    it.each([
        ["none", null],
        ["schneider", words.announcedSchneider],
        ["schwarz", words.announcedSchwarz],
    ] as const)("words the announcement %s", (announcement, word) => {
        expect(announcedWord(announcement)).toBe(word);
    });

    it.each([
        ["karo", true],
        ["herz", true],
        ["pik", true],
        ["kreuz", true],
        ["grand", false],
        ["null", false],
    ] as [Game, boolean][])("tells whether the game %s is a suit game", (game, suited) => {
        expect(isSuitGame(game)).toBe(suited);
    });

    it("names a card by its suit's game word and its rank word", () => {
        expect(cardName({ suit: "herz", rank: "ace" })).toBe(`${words.gameHerz} ${words.rankAce}`);
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
