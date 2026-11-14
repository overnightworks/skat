import type { Cue } from "./cues.ts";
import { watchDeviceMotion } from "./deviceMotion.svelte.ts";
import { MOTION_SETS, type MotionSet } from "./motionSets.ts";
import { currentSettings, loadSettings, motionInForce, soundSettings } from "./settings.svelte.ts";
import { createSound, type AudioPort, type SoundSettings, type Voice } from "./sound.ts";
import { SOUND_SETS, type SoundMoment, type SoundSet } from "./soundSets.ts";
import { createWebAudioPort } from "./webAudio.ts";
import type { Table } from "../routes/(start)/tables.ts";

/** A card another player lays sounds quieter than the player's own. */
const FOREIGN_CARD_GAIN = 0.65;
const OWN_CARD_GAIN = 1;
/** Two cards of one update land on the felt together; heard together they sound as one. */
const CARD_STAGGER_SECONDS = 0.12;
const ARMING_EVENTS = ["pointerup", "keydown"] as const;

export interface TableSoundParts {
    readonly port: AudioPort;
    readonly settings: () => SoundSettings;
    readonly soundSet: () => SoundSet;
    /** The set the cards move in, or nothing while they stand still. */
    readonly motion: () => MotionSet | undefined;
}

export interface TableSound {
    /** Wakes the sound at every tap and key on the target; the returned function stops it. */
    arm(target: Pick<EventTarget, "addEventListener" | "removeEventListener">): () => void;
    forCues(cues: readonly Cue[], table: Table): void;
    /** Sounds the chosen set's played card once, as the player's own card, for the player to hear what the choice sounds like. */
    preview(): Promise<void>;
}

interface Moment {
    readonly moment: SoundMoment;
    readonly gain: number;
}

// A cue without a sound maps to nothing: the table already shows what it tells.
function momentOf(cue: Cue, table: Table): Moment | undefined {
    if (cue.kind !== "card-played") return undefined;
    const own = table.chairs.some((chair) => chair.is_mine && chair.seat === cue.seat);
    return { moment: "card-played", gain: own ? OWN_CARD_GAIN : FOREIGN_CARD_GAIN };
}

export function createTableSound({ port, settings, soundSet, motion }: TableSoundParts): TableSound {
    const sound = createSound(port, settings);
    return {
        arm(target) {
            const wake = (): void => {
                void sound.resume();
            };
            const options = { capture: true, passive: true };
            for (const event of ARMING_EVENTS) target.addEventListener(event, wake, options);
            return () => {
                for (const event of ARMING_EVENTS) target.removeEventListener(event, wake, options);
            };
        },
        forCues(cues, table) {
            const delay = motion()?.cardLandsSeconds ?? 0;
            const set = soundSet();
            const voices = cues
                .flatMap((cue) => momentOf(cue, table) ?? [])
                .flatMap(({ moment, gain }, index): Voice[] =>
                    set.voices[moment](gain).map((voice) => ({
                        ...voice,
                        at: voice.at + delay + index * CARD_STAGGER_SECONDS,
                    })),
                );
            if (voices.length > 0) sound.play(voices);
        },
        async preview() {
            await sound.resume();
            sound.play(soundSet().voices["card-played"](OWN_CARD_GAIN));
        },
    };
}

let shared: TableSound | undefined;

// Made at the first use: the page is prerendered, so nothing of the browser is read at import.
// The device's settings are read before the engine exists, whichever of the tap and the first cue comes first.
function pageSound(): TableSound {
    if (shared === undefined) {
        loadSettings();
        watchDeviceMotion();
        shared = createTableSound({
            port: createWebAudioPort(window),
            settings: soundSettings,
            soundSet: () => SOUND_SETS[currentSettings().soundSet],
            motion: () => {
                const id = motionInForce();
                return id === undefined ? undefined : MOTION_SETS[id];
            },
        });
    }
    return shared;
}

/** Arms the page's sound at its first tap; the returned function disarms it. */
export function armSound(): () => void {
    return pageSound().arm(window);
}

/** Sounds the cues a table update brought. */
export function soundForCues(cues: readonly Cue[], table: Table): void {
    pageSound().forCues(cues, table);
}

/** Lets the player hear the sound set they just chose. */
export function previewSound(): Promise<void> {
    return pageSound().preview();
}
