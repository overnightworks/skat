import { deviceReducesMotion } from "./deviceMotion.svelte.ts";
import { DEFAULT_MOTION_SET, MOTION_SETS, type MotionSetId } from "./motionSets.ts";
import { DEFAULT_SOUND_SETTINGS, type SoundSettings } from "./sound.ts";
import { DEFAULT_SOUND_SET, SOUND_SETS, type SoundSetId } from "./soundSets.ts";
import { DEFAULT_LAST_TRICK_MODE, LAST_TRICK_MODES, type LastTrickMode } from "./stage.ts";

// The only code that reads or writes this key; the record holds one field per setting a player has changed.
const STORAGE_KEY = "skat.settings";

/** What a player chooses on a device. */
export interface Settings extends SoundSettings {
    readonly soundSet: SoundSetId;
    readonly motionSet: MotionSetId;
    /** Moves the table although the device asks for reduced motion. */
    readonly replayMotion: boolean;
    /** Says the bids and the words of Kontra from recordings. */
    readonly voice: boolean;
    /** Whether a finished trick is swept to its taker's pile or stays on the felt until the next lead. */
    readonly lastTrick: LastTrickMode;
    /** Sounds „Du bist dran“ while the window is hidden. */
    readonly turnInBackground: boolean;
    /** Vibrates on „Du bist dran“, on a device that can. */
    readonly vibration: boolean;
}

const DEFAULT_SETTINGS: Settings = {
    ...DEFAULT_SOUND_SETTINGS,
    soundSet: DEFAULT_SOUND_SET,
    motionSet: DEFAULT_MOTION_SET,
    replayMotion: false,
    voice: false,
    lastTrick: DEFAULT_LAST_TRICK_MODE,
    turnInBackground: false,
    vibration: false,
};

const VOLUME_STEPS = 100;

// Each field is checked alone, so one bad field never costs the others.
const CHECKS: { readonly [Field in keyof Settings]: (value: unknown) => value is Settings[Field] } = {
    muted: (value): value is boolean => typeof value === "boolean",
    volume: (value): value is number =>
        Number.isInteger(value) && (value as number) >= 0 && (value as number) <= VOLUME_STEPS,
    soundSet: (value): value is SoundSetId => typeof value === "string" && Object.hasOwn(SOUND_SETS, value),
    motionSet: (value): value is MotionSetId => typeof value === "string" && Object.hasOwn(MOTION_SETS, value),
    replayMotion: (value): value is boolean => typeof value === "boolean",
    voice: (value): value is boolean => typeof value === "boolean",
    lastTrick: (value): value is LastTrickMode => LAST_TRICK_MODES.includes(value as LastTrickMode),
    turnInBackground: (value): value is boolean => typeof value === "boolean",
    vibration: (value): value is boolean => typeof value === "boolean",
};

const FIELDS = Object.keys(CHECKS) as (keyof Settings)[];

const settings: Settings = $state({ ...DEFAULT_SETTINGS });
// The valid fields of the stored record, which is what the next write keeps.
let held: Partial<Settings> = {};

// A storage that throws, a record that is not an object or a field of the wrong type gives that field's default.
function storedFields(): Partial<Settings> {
    try {
        const text = window.localStorage.getItem(STORAGE_KEY);
        if (text === null) return {};
        const record: unknown = JSON.parse(text);
        if (typeof record !== "object" || record === null) return {};
        const fields = record as Record<string, unknown>;
        return Object.fromEntries(
            FIELDS.filter((field) => CHECKS[field](fields[field])).map((field) => [field, fields[field]]),
        );
    } catch {
        return {};
    }
}

/** Reads the device's settings once; nothing is written. */
export function loadSettings(): void {
    held = storedFields();
    Object.assign(settings, DEFAULT_SETTINGS, held);
}

/** Every setting, as the panel shows it. */
export function currentSettings(): Readonly<Settings> {
    return settings;
}

/** The settings the sound engine plays by; read at every sound. */
export function soundSettings(): SoundSettings {
    return { muted: settings.muted, volume: settings.volume };
}

/** The motion set a card lands in: the chosen one while the device allows motion or the player overrides it, else none. */
export function motionInForce(): MotionSetId | undefined {
    return deviceReducesMotion() && !settings.replayMotion ? undefined : settings.motionSet;
}

/** The player's choice holds for the life of the page even when the device refuses to keep it. */
export function changeSetting<Field extends keyof Settings>(field: Field, value: Settings[Field]): void {
    settings[field] = value;
    held = { ...held, [field]: value };
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(held));
    } catch {
        // The choice stays in memory; the table is no worse for a device that keeps nothing.
    }
}
