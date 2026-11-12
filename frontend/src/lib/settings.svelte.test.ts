import { afterEach, describe, expect, it, vi } from "vitest";

const KEY = "skat.settings";

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
        { name: "a muted that is no boolean", held: JSON.stringify({ muted: "yes" }), fails: {} },
    ])("leaves the sound on for $name", async ({ held, fails }) => {
        storeHolding(held, fails);
        const { loadSettings, soundSettings } = await freshSettings();

        loadSettings();

        expect(soundSettings().muted).toBe(false);
    });

    it("reads a muted table back, also from a record with other fields", async () => {
        storeHolding(JSON.stringify({ muted: true, volume: 3, other: "x" }));
        const { loadSettings, soundSettings } = await freshSettings();

        loadSettings();

        expect(soundSettings().muted).toBe(true);
    });

    it("writes nothing", async () => {
        const storage = storeHolding(JSON.stringify({ muted: true }));
        const { loadSettings } = await freshSettings();

        loadSettings();

        expect(storage.writes).toEqual([]);
    });

    it("keeps the engine's volume", async () => {
        storeHolding(null);
        const { loadSettings, soundSettings } = await freshSettings();
        const { DEFAULT_SOUND_SETTINGS } = await import("./sound.ts");

        loadSettings();

        expect(soundSettings().volume).toBe(DEFAULT_SOUND_SETTINGS.volume);
    });
});

describe("setMuted", () => {
    it.each([true, false])("writes exactly the record for %s under the one key", async (muted) => {
        const storage = storeHolding(null);
        const { setMuted, soundSettings } = await freshSettings();

        setMuted(muted);

        expect(storage.writes).toEqual([[KEY, JSON.stringify({ muted })]]);
        expect(soundSettings().muted).toBe(muted);
    });

    it("keeps the value for the life of the page when the write throws", async () => {
        storeHolding(null, { write: true });
        const { setMuted, soundSettings } = await freshSettings();

        expect(() => {
            setMuted(true);
        }).not.toThrow();

        expect(soundSettings().muted).toBe(true);
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
