import { afterEach, describe, expect, it, vi } from "vitest";
import {
    browserCallHost,
    greetCall,
    isFramedInCallMode,
    isHello,
    isPlaced,
    readCallOrigin,
    type CallChannel,
    type CallHost,
    type CallMessageEvent,
    type SeatsMessage,
} from "./callFrame.ts";
import { CALL_MODE, CALL_ORIGIN_PATH, MODE_QUERY_NAME } from "./wire.ts";

const TABLE_ADDRESS = "https://skat.test/t/0123456789abcdef0123456789abcdef";

function stubPage(search: string, framed: boolean): void {
    const own = {};
    vi.stubGlobal("location", { href: `${TABLE_ADDRESS}${search}` });
    vi.stubGlobal("window", { self: own, top: framed ? {} : own });
}

describe("isFramedInCallMode", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it.each([
        { search: `?${MODE_QUERY_NAME}=${CALL_MODE}`, framed: true, expected: true },
        { search: `?${MODE_QUERY_NAME}=${CALL_MODE}`, framed: false, expected: false },
        { search: "", framed: true, expected: false },
        { search: "", framed: false, expected: false },
    ])("is $expected for the address $search when framed is $framed", ({ search, framed, expected }) => {
        stubPage(search, framed);

        expect(isFramedInCallMode()).toBe(expected);
    });
});

const CALL_ORIGIN = "https://call.test";
const TABLE_ID = "0123456789abcdef0123456789abcdef";
const VALID_HELLO = { v: 1, type: "hello", attachment: 1, attempt: null };

describe("isHello", () => {
    it.each([
        { name: "the contract's own shape", data: VALID_HELLO, expected: true },
        { name: "a large attachment", data: { ...VALID_HELLO, attachment: Number.MAX_SAFE_INTEGER }, expected: true },
        { name: "a string", data: JSON.stringify(VALID_HELLO), expected: false },
        { name: "a number", data: 1, expected: false },
        { name: "null", data: null, expected: false },
        { name: "undefined", data: undefined, expected: false },
        { name: "an array", data: [1, "hello", 1, null], expected: false },
        {
            name: "an object without a prototype",
            data: Object.assign(Object.create(null) as object, VALID_HELLO),
            expected: false,
        },
        { name: "a missing v", data: { type: "hello", attachment: 1, attempt: null }, expected: false },
        { name: "a missing attempt", data: { v: 1, type: "hello", attachment: 1 }, expected: false },
        { name: "an extra key", data: { ...VALID_HELLO, extra: 1 }, expected: false },
        { name: "a misnamed key", data: { v: 1, type: "hello", attachment: 1, attempts: null }, expected: false },
        {
            name: "an extra field of a megabyte",
            data: { ...VALID_HELLO, extra: "x".repeat(1_000_000) },
            expected: false,
        },
        { name: "a string of a megabyte", data: "x".repeat(1_000_000), expected: false },
        {
            name: "an object of 10000 keys",
            data: Object.fromEntries(Array.from({ length: 10_000 }, (_, index) => [`key${String(index)}`, index])),
            expected: false,
        },
        { name: "v 2", data: { ...VALID_HELLO, v: 2 }, expected: false },
        { name: "v as a string", data: { ...VALID_HELLO, v: "1" }, expected: false },
        { name: "another type", data: { ...VALID_HELLO, type: "ready" }, expected: false },
        { name: "attachment as a string", data: { ...VALID_HELLO, attachment: "1" }, expected: false },
        { name: "attachment 1.5", data: { ...VALID_HELLO, attachment: 1.5 }, expected: false },
        { name: "attachment 0", data: { ...VALID_HELLO, attachment: 0 }, expected: false },
        { name: "attachment -1", data: { ...VALID_HELLO, attachment: -1 }, expected: false },
        { name: "attachment NaN", data: { ...VALID_HELLO, attachment: Number.NaN }, expected: false },
        { name: "attachment beyond the safe integers", data: { ...VALID_HELLO, attachment: 2 ** 53 }, expected: false },
        { name: "attempt as a number", data: { ...VALID_HELLO, attempt: 1 }, expected: false },
        { name: "attempt undefined", data: { ...VALID_HELLO, attempt: undefined }, expected: false },
    ])("is $expected for $name", ({ data, expected }) => {
        expect(isHello(data)).toBe(expected);
    });
});

function answering(status: number, body: unknown): () => Promise<Pick<Response, "status" | "json">> {
    return () => Promise.resolve({ status, json: () => Promise.resolve(body) });
}

function offline(): Promise<never> {
    return Promise.reject(new TypeError("offline"));
}

describe("readCallOrigin", () => {
    it("asks the route and gives the origin of a 200", async () => {
        const asked: string[] = [];

        const origin = await readCallOrigin((path) => {
            asked.push(path);
            return answering(200, { origin: CALL_ORIGIN })();
        });

        expect([origin, asked]).toEqual([CALL_ORIGIN, [CALL_ORIGIN_PATH]]);
    });

    it.each([
        { name: "a 200 with null", fetchRoute: answering(200, { origin: null }) },
        { name: "a 200 with a number", fetchRoute: answering(200, { origin: 7 }) },
        { name: "a 200 without an origin", fetchRoute: answering(200, {}) },
        { name: "a 200 with a body that is no object", fetchRoute: answering(200, null) },
        { name: "a 401", fetchRoute: answering(401, { origin: CALL_ORIGIN }) },
        { name: "a 500", fetchRoute: answering(500, { origin: CALL_ORIGIN }) },
        {
            name: "a 200 whose body is no JSON",
            fetchRoute: () => Promise.resolve({ status: 200, json: () => Promise.reject(new SyntaxError("no json")) }),
        },
        {
            name: "a rejected request",
            fetchRoute: offline,
        },
    ])("gives null for $name", async ({ fetchRoute }) => {
        expect(await readCallOrigin(fetchRoute)).toBeNull();
    });
});

const PARENT = { name: "parent" };
const SIBLING = { name: "sibling" };

interface FakeCall {
    host: CallHost;
    posts: { message: unknown; targetOrigin: string }[];
    listenerCount: () => number;
    deliver: (event: CallMessageEvent) => void;
}

function fakeCall(fetchRoute = answering(200, { origin: CALL_ORIGIN })): FakeCall {
    const handlers = new Set<(event: CallMessageEvent) => void>();
    const posts: FakeCall["posts"] = [];
    return {
        host: {
            parent: PARENT,
            fetch: fetchRoute,
            post: (message, targetOrigin) => posts.push({ message, targetOrigin }),
            listen: (handler) => {
                handlers.add(handler);
                return () => handlers.delete(handler);
            },
        },
        posts,
        listenerCount: () => handlers.size,
        deliver: (event) => {
            for (const handler of [...handlers]) handler(event);
        },
    };
}

const settled = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

function hello(overrides: Partial<CallMessageEvent> = {}): CallMessageEvent {
    return { source: PARENT, origin: CALL_ORIGIN, data: { ...VALID_HELLO }, ...overrides };
}

const KEY_A = "a".repeat(64);
const KEY_B = "b".repeat(64);
const KEY_C = "c".repeat(64);
const VALID_PLACED = { v: 1, type: "placed", table: TABLE_ID, keys: [KEY_A, KEY_B] };

function placed(overrides: Partial<CallMessageEvent> = {}): CallMessageEvent {
    return { source: PARENT, origin: CALL_ORIGIN, data: { ...VALID_PLACED }, ...overrides };
}

const SEATS_MESSAGE: SeatsMessage = {
    v: 1,
    type: "seats",
    table: TABLE_ID,
    seats: [{ key: KEY_A, box: { x: 1, y: 2, w: 3, h: 4 }, shape: "round" }],
};

describe("isPlaced", () => {
    it.each([
        { name: "the contract's own shape", data: VALID_PLACED, expected: true },
        { name: "no key", data: { ...VALID_PLACED, keys: [] }, expected: true },
        { name: "three keys", data: { ...VALID_PLACED, keys: [KEY_A, KEY_B, KEY_C] }, expected: true },
        { name: "four keys", data: { ...VALID_PLACED, keys: [KEY_A, KEY_B, KEY_C, "d".repeat(64)] }, expected: false },
        { name: "a repeated key", data: { ...VALID_PLACED, keys: [KEY_A, KEY_A] }, expected: false },
        { name: "a short key", data: { ...VALID_PLACED, keys: ["a".repeat(63)] }, expected: false },
        { name: "an uppercase key", data: { ...VALID_PLACED, keys: ["A".repeat(64)] }, expected: false },
        { name: "a key that is no string", data: { ...VALID_PLACED, keys: [1] }, expected: false },
        { name: "keys that are no array", data: { ...VALID_PLACED, keys: KEY_A }, expected: false },
        { name: "another table", data: { ...VALID_PLACED, table: "f".repeat(32) }, expected: false },
        { name: "v 2", data: { ...VALID_PLACED, v: 2 }, expected: false },
        { name: "another type", data: { ...VALID_PLACED, type: "hello" }, expected: false },
        { name: "an extra key", data: { ...VALID_PLACED, extra: 1 }, expected: false },
        { name: "a missing key", data: { v: 1, type: "placed", table: TABLE_ID }, expected: false },
        { name: "a string", data: JSON.stringify(VALID_PLACED), expected: false },
        { name: "null", data: null, expected: false },
        {
            name: "an object without a prototype",
            data: Object.assign(Object.create(null) as object, VALID_PLACED),
            expected: false,
        },
        {
            name: "a megabyte of keys",
            data: { ...VALID_PLACED, keys: new Array<string>(1_000_000).fill(KEY_A) },
            expected: false,
        },
    ])("is $expected for $name", ({ data, expected }) => {
        expect(isPlaced(data, TABLE_ID)).toBe(expected);
    });
});

async function greetedPage(
    call = fakeCall(),
    id = TABLE_ID,
): Promise<{ call: FakeCall; hellos: boolean[]; placements: string[][]; channel: CallChannel }> {
    const hellos: boolean[] = [];
    const placements: string[][] = [];
    const channel = greetCall(id, call.host, {
        onHello: (first) => hellos.push(first),
        onPlaced: (keys) => placements.push([...keys]),
    });
    await settled();
    return { call, hellos, placements, channel };
}

describe("greetCall", () => {
    it("posts exactly one ready with its three keys to the exact call origin", async () => {
        const { call } = await greetedPage();

        expect(call.posts).toEqual([{ message: { v: 1, type: "ready", table: TABLE_ID }, targetOrigin: CALL_ORIGIN }]);
    });

    it("posts one ready only, however many messages come", async () => {
        const { call } = await greetedPage();

        call.deliver(hello({ origin: "https://other.test" }));
        call.deliver(hello());
        call.deliver(hello());
        await settled();

        expect(call.posts).toHaveLength(1);
    });

    it.each([
        { name: "the route answers null", fetchRoute: answering(200, { origin: null }) },
        { name: "the route answers 401", fetchRoute: answering(401, {}) },
        {
            name: "the route fails",
            fetchRoute: offline,
        },
    ])("posts no ready and posts no seats when $name", async ({ fetchRoute }) => {
        const { call, hellos, channel } = await greetedPage(fakeCall(fetchRoute));

        call.deliver(hello());
        channel.post(SEATS_MESSAGE);

        expect([call.posts, hellos]).toEqual([[], []]);
    });

    it.each([
        { name: "a prefix", id: TABLE_ID.slice(0, 31) },
        { name: "a suffix", id: `${TABLE_ID}0` },
        { name: "a part", id: `x${TABLE_ID}y` },
        { name: "uppercase digits", id: TABLE_ID.toUpperCase() },
        { name: "an empty id", id: "" },
    ])("posts no ready and takes no hello for an id that is $name", async ({ id }) => {
        const { call, hellos } = await greetedPage(fakeCall(), id);

        call.deliver(hello());

        expect([call.posts, hellos]).toEqual([[], []]);
    });

    it("tells the first valid hello as the first and every later one as not the first, and keeps listening", async () => {
        const { call, hellos } = await greetedPage();

        call.deliver(hello());
        call.deliver(hello({ data: { ...VALID_HELLO, attachment: 2 } }));
        call.deliver(hello());

        expect([hellos, call.listenerCount()]).toEqual([[true, false, false], 1]);
    });

    it.each([
        { name: "from a sibling window alone", event: hello({ source: SIBLING }) },
        { name: "from no window", event: hello({ source: null }) },
        { name: "from another origin alone", event: hello({ origin: "https://other.test" }) },
        { name: "from the origin with a trailing slash", event: hello({ origin: `${CALL_ORIGIN}/` }) },
        { name: "from the origin in other case", event: hello({ origin: "https://CALL.test" }) },
        { name: "from the opaque origin", event: hello({ origin: "null" }) },
        { name: "with an extra key", event: hello({ data: { ...VALID_HELLO, extra: 1 } }) },
    ])("ignores a hello $name and still takes the valid one after it", async ({ event }) => {
        const { call, hellos } = await greetedPage();

        call.deliver(event);
        const heardOfTheBadOne = hellos.length;
        call.deliver(hello());

        expect([heardOfTheBadOne, hellos]).toEqual([0, [true]]);
    });

    it("ignores a hello that comes before the page's ready", async () => {
        const call = fakeCall();
        const hellos: boolean[] = [];
        greetCall(TABLE_ID, call.host, { onHello: (first) => hellos.push(first), onPlaced: () => undefined });

        call.deliver(hello());
        await settled();

        expect([call.posts.length, hellos]).toEqual([1, []]);
    });

    it("hands the keys of a valid placed on", async () => {
        const { call, placements } = await greetedPage();

        call.deliver(placed());
        call.deliver(placed({ data: { ...VALID_PLACED, keys: [] } }));

        expect(placements).toEqual([[KEY_A, KEY_B], []]);
    });

    it.each([
        { name: "from a sibling window", event: placed({ source: SIBLING }) },
        { name: "from another origin", event: placed({ origin: "https://other.test" }) },
        { name: "of another table", event: placed({ data: { ...VALID_PLACED, table: "f".repeat(32) } }) },
        { name: "with an extra key", event: placed({ data: { ...VALID_PLACED, extra: 1 } }) },
        { name: "with five keys", event: placed({ data: { ...VALID_PLACED, keys: [KEY_A, KEY_B, KEY_C, "d", "e"] } }) },
    ])("ignores a placed $name", async ({ event }) => {
        const { call, placements } = await greetedPage();

        call.deliver(event);

        expect(placements).toEqual([]);
    });

    it("hands no placed on before the page's ready", () => {
        const call = fakeCall();
        const placements: string[][] = [];
        greetCall(TABLE_ID, call.host, { onHello: () => undefined, onPlaced: (keys) => placements.push([...keys]) });

        call.deliver(placed());

        expect(placements).toEqual([]);
    });

    it("posts a seats message to the exact call origin and never to any other", async () => {
        const { call, channel } = await greetedPage();

        channel.post(SEATS_MESSAGE);

        expect(call.posts.slice(1)).toEqual([{ message: SEATS_MESSAGE, targetOrigin: CALL_ORIGIN }]);
    });

    it("removes its listener when the page goes, so no later message is read", async () => {
        const { call, channel, hellos, placements } = await greetedPage();

        channel.stop();
        call.deliver(hello());
        call.deliver(placed());

        expect([call.listenerCount(), hellos, placements]).toEqual([0, [], []]);
    });

    it("stops without effect twice", async () => {
        const { channel } = await greetedPage();
        channel.stop();

        expect(() => {
            channel.stop();
        }).not.toThrow();
    });

    it("posts no ready when the page goes before the route answers", async () => {
        const call = fakeCall();

        greetCall(TABLE_ID, call.host, { onHello: () => undefined, onPlaced: () => undefined }).stop();
        await settled();

        expect(call.posts).toEqual([]);
    });
});

describe("browserCallHost", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("posts to the parent window and listens on the page until the listener is removed", () => {
        const posted: unknown[][] = [];
        const listeners = new Set<unknown>();
        const parent = {
            postMessage: (...message: unknown[]) => posted.push(message),
        };
        vi.stubGlobal("window", {
            parent,
            addEventListener: (_name: string, handler: unknown) => listeners.add(handler),
            removeEventListener: (_name: string, handler: unknown) => listeners.delete(handler),
        });
        vi.stubGlobal("fetch", (path: string) => Promise.resolve({ status: 200, json: () => Promise.resolve(path) }));
        const host = browserCallHost();

        host.post({ v: 1, type: "ready", attachment: 1 } as never, "https://call.test");
        const stopListening = host.listen(() => undefined);
        const listening = listeners.size;
        stopListening();

        expect([host.parent, posted.length, listening, listeners.size]).toEqual([parent, 1, 1, 0]);
        return expect(host.fetch("/x").then((answer) => answer.status)).resolves.toBe(200);
    });
});
