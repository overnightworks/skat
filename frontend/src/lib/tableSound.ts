import type { Cue } from "./cues.ts";
import { watchDeviceMotion } from "./deviceMotion.svelte.ts";
import { MOTION_SETS, type MotionSet } from "./motionSets.ts";
import { currentSettings, loadSettings, motionInForce, soundSettings } from "./settings.svelte.ts";
import { createSound, type AudioPort, type SoundSettings, type Voice } from "./sound.ts";
import { SOUND_SETS, type SoundMoment, type SoundSet } from "./soundSets.ts";
import { everyRecording, recordingOf, voiceKeyOf, type VoiceKey } from "./voice.ts";
import { createWebAudioPort } from "./webAudio.ts";
import type { Table } from "../routes/(start)/tables.ts";

/** A card another player lays sounds quieter than the player's own. */
const FOREIGN_CARD_GAIN = 0.65;
const OWN_CARD_GAIN = 1;
/** A person standing up sounds this much of a person sitting down. */
const STAND_UP_GAIN = 0.4;
/** Two cards of one update land on the felt together; heard together they sound as one. */
const MOMENT_STAGGER_SECONDS = 0.12;
const ARMING_EVENTS = ["pointerup", "keydown"] as const;
/** One short buzz, for a device that can vibrate. */
const TURN_VIBRATION_MILLISECONDS: readonly number[] = [40];

export interface TableSoundParts {
    readonly port: AudioPort;
    readonly settings: () => SoundSettings;
    /** Whether „Du bist dran“ also sounds while the window is hidden. */
    readonly turnInBackground: () => boolean;
    /** Whether „Du bist dran“ also vibrates the device. */
    readonly vibrationOn: () => boolean;
    readonly vibrate: (pattern: readonly number[]) => void;
    readonly soundSet: () => SoundSet;
    /** The set the cards move in, or nothing while they stand still. */
    readonly motion: () => MotionSet | undefined;
    /** Whether the player wants the bids and the words said. */
    readonly voiceOn: () => boolean;
    readonly recording: (key: VoiceKey) => string | undefined;
    /** Every recording of the page's language, which the voice fetches before it is needed. */
    readonly recordings: () => readonly string[];
}

export interface TableSound {
    /** Wakes the sound at every tap and key on the target; the returned function stops it. */
    arm(target: Pick<EventTarget, "addEventListener" | "removeEventListener">): () => void;
    forCues(cues: readonly Cue[], table: Table): void;
    /** Sounds the swept trick at the moment it begins to glide, when it has gathered. */
    forGlide(): void;
    /** Sounds and vibrates „Du bist dran“ for the viewer once the table shows it, after the moves of `cues` have landed. */
    forTurn(cues: readonly Cue[]): void;
    /** Sounds the chosen set's played card once, as the player's own card, for the player to hear what the choice sounds like. */
    preview(): Promise<void>;
    /** Fetches the recordings while the voice is on, so a word is said the moment its cue comes. */
    prepareVoice(): Promise<void>;
}

interface Moment {
    readonly moment: SoundMoment;
    readonly gain: number;
}

// A cue without a sound maps to nothing: the table already shows what it tells. A pass has no bubble to tap.
function momentOf(cue: Cue, table: Table): Moment | undefined {
    switch (cue.kind) {
        case "card-played": {
            const own = table.chairs.some((chair) => chair.is_mine && chair.seat === cue.seat);
            return { moment: "card-played", gain: own ? OWN_CARD_GAIN : FOREIGN_CARD_GAIN };
        }
        case "bid-said":
            return cue.word.action === "pass" ? undefined : { moment: "bid-said", gain: 1 };
        case "word-said":
            return { moment: "word-said", gain: 1 };
        case "dealt":
            return { moment: "dealt", gain: 1 };
        case "result-appeared":
            return { moment: cue.won ? "result-won" : "result-lost", gain: 1 };
        case "chair-taken":
            return { moment: "chair-taken", gain: 1 };
        case "chair-stood":
            return { moment: "chair-stood", gain: STAND_UP_GAIN };
        case "chair-opened":
            return { moment: "chair-opened", gain: 1 };
        default:
            return undefined;
    }
}

// From the cue to the moment the table shows it: a card touches the felt, a bubble has sprung, the stamp hits. A chair's
// own sound starts when it begins to move, so the set keeps that time.
const LANDS_AFTER: Record<Cue["kind"], (motion: MotionSet) => number> = {
    "card-played": (motion) => motion.cardLandsSeconds,
    "bid-said": (motion) => motion.bidSpringsSeconds,
    "word-said": (motion) => motion.stampLandsSeconds,
    "auction-ended": () => 0,
    "trick-taken": () => 0,
    "give-up-refused": () => 0,
    "turn-came": () => 0,
    dealt: () => 0,
    "result-appeared": (motion) => motion.resultLandsSeconds,
    "chair-taken": () => 0,
    "chair-stood": () => 0,
    "chair-opened": () => 0,
};

// The gains count up from the moment the result has risen, and tick as long as the set's count runs.
function countVoices(cues: readonly Cue[], set: SoundSet, motion: MotionSet | undefined): Voice[] {
    if (motion === undefined) return [];
    return cues
        .filter((cue) => cue.kind === "result-appeared" && cue.counts)
        .flatMap(() =>
            set.counts(1, motion.countSeconds).map((voice) => ({ ...voice, at: voice.at + motion.countStartsSeconds })),
        );
}

export function createTableSound({
    port,
    settings,
    turnInBackground,
    vibrationOn,
    vibrate,
    soundSet,
    motion,
    voiceOn,
    recording,
    recordings,
}: TableSoundParts): TableSound {
    const sound = createSound(port, settings);

    async function prepareVoice(): Promise<void> {
        if (voiceOn()) await sound.prepare(recordings());
    }

    return {
        arm(target) {
            const wake = (): void => {
                void sound.resume().then(prepareVoice);
            };
            const options = { capture: true, passive: true };
            for (const event of ARMING_EVENTS) target.addEventListener(event, wake, options);
            return () => {
                for (const event of ARMING_EVENTS) target.removeEventListener(event, wake, options);
            };
        },
        forCues(cues, table) {
            const set = soundSet();
            const moving = motion();
            const landings = cues.map((cue) => ({
                cue,
                lands: moving === undefined ? 0 : LANDS_AFTER[cue.kind](moving),
            }));
            const voices = landings
                .flatMap(({ cue, lands }) => {
                    const moment = momentOf(cue, table);
                    return moment === undefined ? [] : [{ ...moment, lands }];
                })
                .flatMap(({ moment, gain, lands }, index): Voice[] =>
                    set.voices[moment](gain).map((voice) => ({
                        ...voice,
                        at: voice.at + lands + index * MOMENT_STAGGER_SECONDS,
                    })),
                );
            const ticks = countVoices(cues, set, moving);
            if (voices.length + ticks.length > 0) sound.play([...voices, ...ticks]);
            if (!voiceOn()) return;
            for (const { cue, lands } of landings) {
                const key = voiceKeyOf(cue);
                const url = key === undefined ? undefined : recording(key);
                if (url !== undefined) sound.speak(url, lands);
            }
        },
        forGlide() {
            const gathers = motion()?.trickGatherSeconds ?? 0;
            sound.play(
                soundSet()
                    .voices["trick-swept"](1)
                    .map((voice) => ({ ...voice, at: voice.at + gathers })),
            );
        },
        forTurn(cues) {
            const moving = motion();
            const lands = moving === undefined ? 0 : Math.max(0, ...cues.map((cue) => LANDS_AFTER[cue.kind](moving)));
            sound.play(
                soundSet()
                    .voices["turn-came"](1)
                    .map((voice) => ({ ...voice, at: voice.at + lands })),
                { whenHidden: turnInBackground() },
            );
            if (vibrationOn()) vibrate(TURN_VIBRATION_MILLISECONDS);
        },
        async preview() {
            await sound.resume();
            sound.play(soundSet().voices["card-played"](OWN_CARD_GAIN));
        },
        prepareVoice,
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
            turnInBackground: () => currentSettings().turnInBackground,
            vibrationOn: () => currentSettings().vibration,
            vibrate: (pattern) => {
                if ("vibrate" in window.navigator) window.navigator.vibrate(pattern);
            },
            soundSet: () => SOUND_SETS[currentSettings().soundSet],
            motion: () => {
                const id = motionInForce();
                return id === undefined ? undefined : MOTION_SETS[id];
            },
            voiceOn: () => currentSettings().voice,
            recording: recordingOf,
            recordings: everyRecording,
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

/** Sounds the trick that begins to glide to its taker's pile. */
export function soundForGlide(): void {
    pageSound().forGlide();
}

/** Sounds and vibrates the viewer's turn, which the stage shows after the moves of `cues` have landed. */
export function soundForTurn(cues: readonly Cue[]): void {
    pageSound().forTurn(cues);
}

/** Lets the player hear the sound set they just chose. */
export function previewSound(): Promise<void> {
    return pageSound().preview();
}

/** Fetches the recordings of the voice once the player has switched it on. */
export function prepareVoice(): Promise<void> {
    return pageSound().prepareVoice();
}
