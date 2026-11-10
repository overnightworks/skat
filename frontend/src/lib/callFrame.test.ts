import { afterEach, describe, expect, it, vi } from "vitest";
import {
    greetCall,
    isFramedInCallMode,
    isHello,
    readCallOrigin,
    type CallHost,
    type CallMessageEvent,
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

async function greetedPage(call = fakeCall()): Promise<{ call: FakeCall; greeted: () => number; stop: () => void }> {
    let greetings = 0;
    const stop = greetCall(TABLE_ID, call.host, () => (greetings += 1));
    await settled();
    return { call, greeted: () => greetings, stop };
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
    ])("posts no ready when $name", async ({ fetchRoute }) => {
        const { call, greeted } = await greetedPage(fakeCall(fetchRoute));

        call.deliver(hello());

        expect([call.posts, greeted()]).toEqual([[], 0]);
    });

    it.each([
        { name: "a prefix", id: TABLE_ID.slice(0, 31) },
        { name: "a suffix", id: `${TABLE_ID}0` },
        { name: "a part", id: `x${TABLE_ID}y` },
        { name: "uppercase digits", id: TABLE_ID.toUpperCase() },
        { name: "an empty id", id: "" },
    ])("posts no ready for an id that is $name", async ({ id }) => {
        const call = fakeCall();

        greetCall(id, call.host, () => undefined);
        await settled();

        expect(call.posts).toEqual([]);
    });

    it("calls onGreeted once for the first valid hello and removes its listener", async () => {
        const { call, greeted } = await greetedPage();

        call.deliver(hello());

        expect([greeted(), call.listenerCount()]).toEqual([1, 0]);
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
        const { call, greeted } = await greetedPage();

        call.deliver(event);
        const greetedByTheBadOne = greeted();
        call.deliver(hello());

        expect([greetedByTheBadOne, greeted()]).toEqual([0, 1]);
    });

    it("ignores a hello that comes before the page's ready", async () => {
        const call = fakeCall();
        let greetings = 0;
        greetCall(TABLE_ID, call.host, () => (greetings += 1));

        call.deliver(hello());
        await settled();

        expect([call.posts.length, greetings]).toEqual([1, 0]);
    });

    it.each([
        { name: "the same attachment", attachment: 1 },
        { name: "another attachment", attachment: 2 },
    ])("changes nothing for a second hello naming $name and reads no data of it", async ({ attachment }) => {
        const { call, greeted } = await greetedPage();
        call.deliver(hello());
        let reads = 0;
        const second = {
            source: PARENT,
            origin: CALL_ORIGIN,
            get data(): unknown {
                reads += 1;
                return { ...VALID_HELLO, attachment };
            },
        };

        call.deliver(second);

        expect([greeted(), reads, call.posts.length]).toEqual([1, 0, 1]);
    });

    it("removes its listener when the page goes before any greeting", async () => {
        const { call, stop, greeted } = await greetedPage();

        stop();
        call.deliver(hello());

        expect([call.listenerCount(), greeted()]).toEqual([0, 0]);
    });

    it("stops without effect after the greeting", async () => {
        const { call, stop, greeted } = await greetedPage();
        call.deliver(hello());

        expect(() => {
            stop();
        }).not.toThrow();
        expect([greeted(), call.listenerCount()]).toEqual([1, 0]);
    });

    it("posts no ready when the page goes before the route answers", async () => {
        const call = fakeCall();

        greetCall(TABLE_ID, call.host, () => undefined)();
        await settled();

        expect(call.posts).toEqual([]);
    });
});
