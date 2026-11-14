import { afterEach, describe, expect, it, vi } from "vitest";

const KEY = "skat.settings";
const DEFAULTS = {
    muted: false,
    volume: 70,
    soundSet: "leise",
    motionSet: "verspielt",
    replayMotion: false,
    voice: false,
    lastTrick: "sweep",
    turnInBackground: false,
    vibration: false,
};

// The record is module state, so each test reads a module of its own.
async function freshSettings() {
    vi.resetModules();
    return import("./settings.svelte.ts");
}

class FakeStorage {
    readonly writes: [string, string][] = [];
    constructor(
        private held: string | null,
        private readonly fails: { read?: boolean; write?: boolean } = {},
    ) {}

    getItem(key: string): string | null {
        if (this.fails.read === true) throw new Error("storage is blocked");
        return key === KEY ? this.held : null;
    }

    setItem(key: string, value: string): void {
        if (this.fails.write === true) throw new Error("storage is full");
        this.writes.push([key, value]);
        this.held = value;
    }
}

function storeHolding(held: string | null, fails: { read?: boolean; write?: boolean } = {}): FakeStorage {
    const storage = new FakeStorage(held, fails);
    vi.stubGlobal("window", { localStorage: storage });
    return storage;
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("loadSettings", () => {
    it.each([
        { name: "no record", held: null, fails: {} },
        { name: "a read that throws", held: JSON.stringify({ muted: true }), fails: { read: true } },
        { name: "JSON that does not parse", held: "{muted", fails: {} },
        { name: "a record that is no object", held: "true", fails: {} },
        { name: "a record that is null", held: "null", fails: {} },
    ])("leaves every setting at its default for $name", async ({ held, fails }) => {
        storeHolding(held, fails);
        const { currentSettings, loadSettings } = await freshSettings();

        loadSettings();

        expect(currentSettings()).toEqual(DEFAULTS);
    });

    it("reads every field back, also from a record with other fields", async () => {
        const kept = {
            muted: true,
            volume: 30,
            soundSet: "funkeln",
            motionSet: "dezent",
            replayMotion: true,
            voice: true,
            lastTrick: "stay",
            turnInBackground: true,
            vibration: true,
        };
        storeHolding(JSON.stringify({ ...kept, other: "x" }));
        const { currentSettings, loadSettings } = await freshSettings();

        loadSettings();

        expect(currentSettings()).toEqual(kept);
    });

    it.each([
        { field: "muted", bad: "yes" },
        { field: "volume", bad: "loud" },
        { field: "volume", bad: -1 },
        { field: "volume", bad: 101 },
        { field: "volume", bad: 50.5 },
        { field: "soundSet", bad: "laut" },
        { field: "soundSet", bad: "toString" },
        { field: "motionSet", bad: 7 },
        { field: "replayMotion", bad: 1 },
        { field: "voice", bad: "on" },
        { field: "lastTrick", bad: "wegfegen" },
        { field: "lastTrick", bad: "toString" },
        { field: "turnInBackground", bad: "on" },
        { field: "vibration", bad: 1 },
    ])("gives a $field of $bad its default and keeps the other fields as stored", async ({ field, bad }) => {
        const kept = {
            muted: true,
            volume: 30,
            soundSet: "funkeln",
            motionSet: "dezent",
            replayMotion: true,
            voice: true,
            lastTrick: "stay",
            turnInBackground: true,
            vibration: true,
        };
        storeHolding(JSON.stringify({ ...kept, [field]: bad }));
        const { currentSettings, loadSettings } = await freshSettings();

        loadSettings();

        expect(currentSettings()).toEqual({ ...kept, [field]: DEFAULTS[field as keyof typeof DEFAULTS] });
    });

    it("writes nothing", async () => {
        const storage = storeHolding(JSON.stringify({ muted: true }));
        const { loadSettings } = await freshSettings();

        loadSettings();

        expect(storage.writes).toEqual([]);
    });

    it("hands the engine the muted flag and the volume", async () => {
        storeHolding(JSON.stringify({ muted: true, volume: 20 }));
        const { loadSettings, soundSettings } = await freshSettings();

        loadSettings();

        expect(soundSettings()).toEqual({ muted: true, volume: 20 });
    });
});

describe("changeSetting", () => {
    it.each([
        { field: "muted", value: true, record: '{"muted":true}' },
        { field: "muted", value: false, record: '{"muted":false}' },
        { field: "volume", value: 0, record: '{"volume":0}' },
        { field: "soundSet", value: "stammtisch", record: '{"soundSet":"stammtisch"}' },
        { field: "motionSet", value: "dezent", record: '{"motionSet":"dezent"}' },
        { field: "replayMotion", value: true, record: '{"replayMotion":true}' },
        { field: "voice", value: true, record: '{"voice":true}' },
        { field: "lastTrick", value: "stay", record: '{"lastTrick":"stay"}' },
        { field: "turnInBackground", value: true, record: '{"turnInBackground":true}' },
        { field: "vibration", value: true, record: '{"vibration":true}' },
    ] as const)("writes exactly the record for $field $value under the one key", async ({ field, value, record }) => {
        const storage = storeHolding(null);
        const { changeSetting, currentSettings } = await freshSettings();

        changeSetting(field, value as never);

        expect(storage.writes).toEqual([[KEY, record]]);
        expect(currentSettings()[field]).toBe(value);
    });

    it("keeps the fields a player changed earlier and drops a stored field that was bad", async () => {
        const storage = storeHolding(JSON.stringify({ muted: true, volume: "loud" }));
        const { changeSetting, loadSettings } = await freshSettings();
        loadSettings();

        changeSetting("soundSet", "funkeln");

        expect(storage.writes).toEqual([[KEY, '{"muted":true,"soundSet":"funkeln"}']]);
    });

    it("keeps the value for the life of the page when the write throws", async () => {
        storeHolding(null, { write: true });
        const { changeSetting, currentSettings } = await freshSettings();

        expect(() => {
            changeSetting("volume", 10);
        }).not.toThrow();

        expect(currentSettings().volume).toBe(10);
    });
});

describe("motionInForce", () => {
    it.each([
        { reduces: false, replay: false, moving: true },
        { reduces: true, replay: false, moving: false },
        { reduces: true, replay: true, moving: true },
        { reduces: false, replay: true, moving: true },
    ])(
        "moves in the chosen set only when the device allows it or the player overrides it ($reduces, $replay)",
        async ({ reduces, replay, moving }) => {
            vi.stubGlobal("window", {
                localStorage: { getItem: () => JSON.stringify({ motionSet: "dezent", replayMotion: replay }) },
                matchMedia: () => ({ matches: reduces, addEventListener: vi.fn() }),
            });
            const { loadSettings, motionInForce } = await freshSettings();
            const { watchDeviceMotion } = await import("./deviceMotion.svelte.ts");

            loadSettings();
            watchDeviceMotion();

            expect(motionInForce()).toBe(moving ? "dezent" : undefined);
        },
    );

    it("stands still before the device is asked", async () => {
        storeHolding(null);
        const { loadSettings, motionInForce } = await freshSettings();

        loadSettings();

        expect(motionInForce()).toBeUndefined();
    });
});

describe("the module", () => {
    it("touches no storage when it is imported", async () => {
        const touched = vi.fn();
        vi.stubGlobal("window", {
            get localStorage() {
                touched();
                return new FakeStorage(null);
            },
        });

        await freshSettings();

        expect(touched).not.toHaveBeenCalled();
    });
});
