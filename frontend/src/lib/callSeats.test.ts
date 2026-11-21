import { describe, expect, it } from "vitest";
import {
    acceptedPlacements,
    holdOf,
    holesPath,
    occupancyOf,
    openSeats,
    postedSeats,
    readPersonKeys,
    seatsMessage,
    shownAsInView,
    type PostedSeat,
    type TileReading,
} from "./callSeats.ts";
import type { SeatEntry } from "./callFrame.ts";
import { TABLES_PATH, TABLE_PERSON_KEYS_SUFFIX } from "./wire.ts";

const TABLE_ID = "0123456789abcdef0123456789abcdef";
const KEY_1 = "1".repeat(64);
const KEY_2 = "2".repeat(64);
const KEY_3 = "3".repeat(64);
const CORNERS = { tl: 22, tr: 22, br: 12, bl: 12 };

function reading(seat: number, overrides: Partial<TileReading> = {}): TileReading {
    return {
        seat,
        key: String(seat).repeat(64),
        occupancy: `person-${String(seat)}`,
        rect: { x: 10.25 * seat, y: 20.5, width: 120.75, height: 90.125 },
        shape: "rect",
        radii: CORNERS,
        ...overrides,
    };
}

describe("seatsMessage", () => {
    it("gives each tile's box exactly as the browser measured it, with its shape and its four corners", () => {
        const tiles = [reading(1)];

        const message = seatsMessage(TABLE_ID, postedSeats(tiles));

        expect(message).toEqual({
            v: 1,
            type: "seats",
            table: TABLE_ID,
            seats: [{ key: KEY_1, box: { x: 10.25, y: 20.5, w: 120.75, h: 90.125 }, shape: "rect", radius: CORNERS }],
        });
    });

    it("gives a round tile no radius", () => {
        const [entry] = seatsMessage(TABLE_ID, postedSeats([reading(1, { shape: "round" })])).seats;

        expect(entry).toEqual({ key: KEY_1, box: { x: 10.25, y: 20.5, w: 120.75, h: 90.125 }, shape: "round" });
    });

    it("lists the chairs in seat order whatever order they were read in", () => {
        const message = seatsMessage(TABLE_ID, postedSeats([reading(3), reading(1), reading(2)]));

        expect(message.seats.map((entry) => entry.key)).toEqual([KEY_1, "2".repeat(64), "3".repeat(64)]);
    });

    it("lists at most three chairs", () => {
        const message = seatsMessage(TABLE_ID, postedSeats([reading(1), reading(2), reading(3), reading(4)]));

        expect(message.seats).toHaveLength(3);
    });

    it("posts an empty list when no chair is read, and never drops the message", () => {
        expect(seatsMessage(TABLE_ID, postedSeats([]))).toEqual({ v: 1, type: "seats", table: TABLE_ID, seats: [] });
    });

    it.each([
        { name: "no key", overrides: { key: undefined } },
        { name: "a zero width", overrides: { rect: { x: 0, y: 0, width: 0, height: 10 } } },
        { name: "a negative height", overrides: { rect: { x: 0, y: 0, width: 10, height: -1 } } },
        { name: "a NaN width", overrides: { rect: { x: 0, y: 0, width: Number.NaN, height: 10 } } },
        { name: "an infinite x", overrides: { rect: { x: Infinity, y: 0, width: 10, height: 10 } } },
        { name: "a NaN y", overrides: { rect: { x: 0, y: Number.NaN, width: 10, height: 10 } } },
        { name: "an unknown shape", overrides: { shape: "oval" } },
        { name: "an empty shape", overrides: { shape: "" } },
        { name: "a negative corner", overrides: { radii: { ...CORNERS, tl: -1 } } },
        { name: "a NaN corner", overrides: { radii: { ...CORNERS, br: Number.NaN } } },
        { name: "an infinite corner", overrides: { radii: { ...CORNERS, bl: Infinity } } },
        { name: "an infinite top right corner", overrides: { radii: { ...CORNERS, tr: Infinity } } },
    ])("drops a chair with $name and keeps the others", ({ overrides }) => {
        const message = seatsMessage(TABLE_ID, postedSeats([reading(1, overrides), reading(2)]));

        expect(message.seats.map((entry) => entry.key)).toEqual(["2".repeat(64)]);
    });

    it("keeps a round chair whose corners are not read", () => {
        const message = seatsMessage(
            TABLE_ID,
            postedSeats([reading(1, { shape: "round", radii: { tl: Number.NaN, tr: 0, br: 0, bl: 0 } })]),
        );

        expect(message.seats).toHaveLength(1);
    });

    it("keeps a negative origin and a zero corner", () => {
        const message = seatsMessage(
            TABLE_ID,
            postedSeats([
                reading(1, { rect: { x: -4, y: -2, width: 10, height: 10 }, radii: { tl: 0, tr: 0, br: 0, bl: 0 } }),
            ]),
        );

        expect(message.seats).toHaveLength(1);
    });
});

describe("postedSeats", () => {
    it("keeps the seat and the occupancy each entry was read with", () => {
        const posted = postedSeats([reading(2), reading(1)]);

        expect(posted.map(({ seat, occupancy }) => [seat, occupancy])).toEqual([
            [1, "person-1"],
            [2, "person-2"],
        ]);
    });
});

describe("shownAsInView", () => {
    it("drops a tile that still shows another occupant than the newest view seats and keeps the others", () => {
        const tiles = [reading(1), reading(2), reading(3)];
        const newest = new Map([
            [1, "person-1"],
            [2, "person-elsewhere"],
        ]);

        expect(shownAsInView(tiles, newest).map(({ seat }) => seat)).toEqual([1]);
    });

    it("keeps a tile again once the page shows the occupant the newest view seats", () => {
        const newest = new Map([[2, "person-2"]]);

        expect(shownAsInView([reading(2)], newest).map(({ seat }) => seat)).toEqual([2]);
    });
});

describe("holesPath", () => {
    const owner = { left: 100, top: 50, width: 400, height: 300 };
    const outer = "M -96 -96 H 496 V 396 H -96 Z";

    it("is the outer rectangle with one rounded rectangle per rect hole, in the element's own coordinates", () => {
        const hole: SeatEntry = { key: KEY_1, box: { x: 110, y: 60, w: 80, h: 60 }, shape: "rect", radius: CORNERS };

        expect(holesPath(owner, [hole])).toBe(
            `path(evenodd, "${outer} M 32 10 H 68 A 22 22 0 0 1 90 32 V 58 A 12 12 0 0 1 78 70 H 22 A 12 12 0 0 1 10 58 V 32 A 22 22 0 0 1 32 10 Z")`,
        );
    });

    it("draws a round hole as the ellipse inscribed in its box", () => {
        const hole: SeatEntry = { key: KEY_1, box: { x: 200, y: 100, w: 40, h: 40 }, shape: "round" };

        expect(holesPath(owner, [hole])).toBe(
            `path(evenodd, "${outer} M 100 70 A 20 20 0 1 0 140 70 A 20 20 0 1 0 100 70 Z")`,
        );
    });

    it("scales corners that do not fit their side down as a box does", () => {
        const hole: SeatEntry = {
            key: KEY_1,
            box: { x: 100, y: 50, w: 40, h: 40 },
            shape: "rect",
            radius: { tl: 40, tr: 40, br: 40, bl: 40 },
        };

        expect(holesPath(owner, [hole])).toBe(
            `path(evenodd, "${outer} M 20 0 H 20 A 20 20 0 0 1 40 20 V 20 A 20 20 0 0 1 20 40 H 20 A 20 20 0 0 1 0 20 V 20 A 20 20 0 0 1 20 0 Z")`,
        );
    });

    it("draws every hole of the list", () => {
        const holes: SeatEntry[] = [
            { key: KEY_1, box: { x: 100, y: 50, w: 20, h: 20 }, shape: "round" },
            { key: KEY_2, box: { x: 200, y: 50, w: 20, h: 20 }, shape: "round" },
        ];

        expect(holesPath(owner, holes).match(/ M /g)).toHaveLength(2);
    });

    it("is the outer rectangle alone for no hole", () => {
        expect(holesPath(owner, [])).toBe(`path(evenodd, "${outer}")`);
    });
});

describe("occupancyOf", () => {
    it("differs for a free chair, another name, another kind and the own chair", () => {
        const base = { occupant_name: "Anna", occupant_kind: "person", is_mine: false } as const;

        const signatures = [
            occupancyOf({ occupant_name: null, occupant_kind: null, is_mine: false }),
            occupancyOf(base),
            occupancyOf({ ...base, occupant_name: "Bert" }),
            occupancyOf({ ...base, occupant_kind: "agent" }),
            occupancyOf({ ...base, is_mine: true }),
        ];

        expect(new Set(signatures).size).toBe(signatures.length);
    });

    it("is equal for the same occupant", () => {
        const chair = { occupant_name: "Anna", occupant_kind: "person", is_mine: false } as const;

        expect(occupancyOf(chair)).toBe(occupancyOf({ ...chair }));
    });

    it("keeps a name that holds the separator apart from the kind", () => {
        const first = occupancyOf({ occupant_name: 'A","person', occupant_kind: "agent", is_mine: false });
        const second = occupancyOf({ occupant_name: "A", occupant_kind: "person", is_mine: false });

        expect(first).not.toBe(second);
    });
});

describe("holdOf", () => {
    const keys = { version: 5, keys: new Map([[1, KEY_1]]) };

    it.each([
        { name: "a closed table", closed: true, failed: false, keys, viewVersion: null, expected: "closed" },
        {
            name: "a closed table with a failed read",
            closed: true,
            failed: true,
            keys,
            viewVersion: 5,
            expected: "closed",
        },
        { name: "a failed read", closed: false, failed: true, keys, viewVersion: 5, expected: "failed" },
        {
            name: "a failed read before any keys",
            closed: false,
            failed: true,
            keys: null,
            viewVersion: 5,
            expected: "failed",
        },
        { name: "keys of the view's version", closed: false, failed: false, keys, viewVersion: 5, expected: "current" },
        { name: "keys older than the view", closed: false, failed: false, keys, viewVersion: 6, expected: "held" },
        { name: "keys newer than the view", closed: false, failed: false, keys, viewVersion: 4, expected: "held" },
        { name: "no keys yet", closed: false, failed: false, keys: null, viewVersion: 5, expected: "held" },
        { name: "no view yet", closed: false, failed: false, keys, viewVersion: null, expected: "held" },
    ])("is $expected for $name", ({ expected, ...state }) => {
        expect(holdOf(state)).toBe(expected);
    });
});

function posted(seat: number, key: string, occupancy = `person-${String(seat)}`): PostedSeat {
    return { seat, occupancy, entry: { key, box: { x: 0, y: 0, w: 10, h: 10 }, shape: "round" } };
}

describe("acceptedPlacements", () => {
    it("keeps the keys of the last posted seats and ignores any other on its own", () => {
        const accepted = acceptedPlacements([KEY_1, "f".repeat(64), KEY_2], [posted(1, KEY_1), posted(2, KEY_2)]);

        expect([...accepted]).toEqual([KEY_1, KEY_2]);
    });

    it("keeps nothing when nothing was posted", () => {
        expect(acceptedPlacements([KEY_1], []).size).toBe(0);
    });
});

describe("openSeats", () => {
    const seats = [posted(1, KEY_1), posted(2, KEY_2), posted(3, KEY_3)];
    const occupied = new Map([
        [1, "person-1"],
        [2, "person-2"],
        [3, "person-3"],
    ]);

    function open(overrides: Partial<Parameters<typeof openSeats>[0]> = {}): number[] {
        return openSeats({
            posted: seats,
            placed: new Set([KEY_1, KEY_2]),
            occupancyNow: occupied,
            current: true,
            ...overrides,
        }).map((seat) => seat.seat);
    }

    it("opens a chair whose key is in the posted seats and in the placed keys", () => {
        expect(open()).toEqual([1, 2]);
    });

    it("opens no chair before any placed", () => {
        expect(open({ placed: new Set() })).toEqual([]);
    });

    it("opens no chair of a key that was not posted", () => {
        expect(open({ placed: new Set(["f".repeat(64)]) })).toEqual([]);
    });

    it("closes a chair whose occupant changed since the seats were posted", () => {
        const changed = new Map(occupied).set(2, "agent-2");

        expect(open({ occupancyNow: changed })).toEqual([1]);
    });

    it("closes a chair that is free now", () => {
        const freed = new Map(occupied);
        freed.delete(1);

        expect(open({ occupancyNow: freed })).toEqual([2]);
    });

    it("closes every chair when the table is gone", () => {
        expect(open({ occupancyNow: new Map() })).toEqual([]);
    });

    it("closes every hole while the keys are not those of the view's version", () => {
        expect(open({ current: false })).toEqual([]);
    });
});

describe("readPersonKeys", () => {
    const answer = (status: number, body: unknown) => () =>
        Promise.resolve({ status, json: () => Promise.resolve(body) });

    it("asks the table's route and gives the version and the key of each seat", async () => {
        const asked: string[] = [];

        const keys = await readPersonKeys((path) => {
            asked.push(path);
            return answer(200, {
                version: 7,
                keys: [
                    { seat: 1, key: KEY_1 },
                    { seat: 3, key: KEY_3 },
                ],
            })();
        }, TABLE_ID);

        expect([keys?.version, [...(keys?.keys ?? [])], asked]).toEqual([
            7,
            [
                [1, KEY_1],
                [3, KEY_3],
            ],
            [`${TABLES_PATH}/${TABLE_ID}${TABLE_PERSON_KEYS_SUFFIX}`],
        ]);
    });

    it("gives no keys for a table with no seated account", async () => {
        const keys = await readPersonKeys(answer(200, { version: 1, keys: [] }), TABLE_ID);

        expect(keys?.keys.size).toBe(0);
    });

    it.each([
        { name: "a 401", fetchRoute: answer(401, { version: 1, keys: [] }) },
        { name: "a 404", fetchRoute: answer(404, { version: 1, keys: [] }) },
        { name: "a body that is no object", fetchRoute: answer(200, null) },
        { name: "a version that is no number", fetchRoute: answer(200, { version: "1", keys: [] }) },
        { name: "a fractional version", fetchRoute: answer(200, { version: 1.5, keys: [] }) },
        { name: "keys that are no array", fetchRoute: answer(200, { version: 1, keys: {} }) },
        { name: "an entry that is no object", fetchRoute: answer(200, { version: 1, keys: [null] }) },
        {
            name: "a seat that is no integer",
            fetchRoute: answer(200, { version: 1, keys: [{ seat: "1", key: KEY_1 }] }),
        },
        {
            name: "a key that is no hex of 64",
            fetchRoute: answer(200, { version: 1, keys: [{ seat: 1, key: "abc" }] }),
        },
        { name: "a key that is no string", fetchRoute: answer(200, { version: 1, keys: [{ seat: 1, key: 1 }] }) },
        {
            name: "more keys than a table has chairs",
            fetchRoute: answer(200, {
                version: 1,
                keys: [1, 2, 3, 4].map((seat) => ({ seat, key: KEY_1 })),
            }),
        },
        {
            name: "a seat that appears twice",
            fetchRoute: answer(200, {
                version: 1,
                keys: [
                    { seat: 1, key: KEY_1 },
                    { seat: 1, key: KEY_2 },
                ],
            }),
        },
        {
            name: "a body that is no JSON",
            fetchRoute: () => Promise.resolve({ status: 200, json: () => Promise.reject(new SyntaxError("no json")) }),
        },
        { name: "a rejected request", fetchRoute: () => Promise.reject(new TypeError("offline")) },
    ])("gives null for $name", async ({ fetchRoute }) => {
        expect(await readPersonKeys(fetchRoute, TABLE_ID)).toBeNull();
    });
});
