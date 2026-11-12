import { DEFAULT_SOUND_SETTINGS, type SoundSettings } from "./sound.ts";

// The only code that reads or writes this key; the record holds one field per setting a player has changed.
const STORAGE_KEY = "skat.settings";

const settings = $state({ muted: DEFAULT_SOUND_SETTINGS.muted });

// A storage that throws, a record that is not an object or a field of the wrong type gives that field's default.
function storedMuted(): boolean {
    try {
        const held = window.localStorage.getItem(STORAGE_KEY);
        if (held === null) return DEFAULT_SOUND_SETTINGS.muted;
        const record: unknown = JSON.parse(held);
        const muted = typeof record === "object" && record !== null ? (record as { muted?: unknown }).muted : undefined;
        return typeof muted === "boolean" ? muted : DEFAULT_SOUND_SETTINGS.muted;
    } catch {
        return DEFAULT_SOUND_SETTINGS.muted;
    }
}

/** Reads the device's settings once; nothing is written. */
export function loadSettings(): void {
    settings.muted = storedMuted();
}

/** The settings the sound engine plays by; read at every sound. */
export function soundSettings(): SoundSettings {
    return { muted: settings.muted, volume: DEFAULT_SOUND_SETTINGS.volume };
}

/** The player's choice holds for the life of the page even when the device refuses to keep it. */
export function setMuted(muted: boolean): void {
    settings.muted = muted;
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ muted }));
    } catch {
        // The choice stays in memory; the table is no worse for a device that keeps nothing.
    }
}
