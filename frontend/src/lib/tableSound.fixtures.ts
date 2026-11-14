import type { Cue } from "./cues.ts";
import { MOTION_SETS, type MotionSetId } from "./motionSets.ts";
import type { AudioPort, Voice } from "./sound.ts";
import { SOUND_SETS, type SoundSetId } from "./soundSets.ts";
import { createTableSound, type TableSound } from "./tableSound.ts";
import type { Card, Chair, LastTrick, Table } from "../routes/(start)/tables.ts";

export const OWN_SEAT = 1;
export const OTHER_SEAT = 2;
export const THIRD_SEAT = 3;
const CARD: Card = { suit: "kreuz", rank: "king" };
export const TRICK: LastTrick = { cards: [CARD, CARD, CARD], leader_seat: OWN_SEAT, taker_seat: OTHER_SEAT };
const SETTINGS = { muted: false, volume: 70 };
export const FUNKELN_VOICES = 3;
// Waking the device plays one silent sample, which the stand-in counts as a start.
export const WAKING_SAMPLE_STARTS = 1;

export class FakePort implements AudioPort {
    resumed = 0;
    played: { voice: Voice; afterSeconds: number }[] = [];
    // What each sound asked of the window: true for a sound that is wanted while it is hidden.
    askedWhenHidden: boolean[] = [];
    // The patterns the device was asked to vibrate with.
    vibrations: (readonly number[])[] = [];

    ready(whenHidden: boolean): boolean {
        this.askedWhenHidden.push(whenHidden);
        return true;
    }

    resume(): Promise<void> {
        this.resumed += 1;
        return Promise.resolve();
    }

    setLoudness(): void {
        // The loudness is the engine's, not this module's.
    }

    playVoice(voice: Voice, afterSeconds: number): void {
        this.played.push({ voice, afterSeconds });
    }

    loaded: string[] = [];
    spoken: { url: string; afterSeconds: number }[] = [];

    loadRecordings(urls: readonly string[]): Promise<void> {
        this.loaded.push(...urls);
        return Promise.resolve();
    }

    playRecording(url: string, afterSeconds: number): void {
        this.spoken.push({ url, afterSeconds });
    }

    setSea(): void {
        // The sea is the engine's, not this module's.
    }
}

export function cardPlayedBy(seat: number): Cue {
    return { kind: "card-played", seat, card: CARD };
}

export function tableSeenFrom(ownSeat: number): Table {
    const chairs = [OWN_SEAT, OTHER_SEAT, THIRD_SEAT].map((seat): Chair => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === ownSeat,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
        former_holder_name: null,
        is_mine_to_return: false,
        nudge: null,
    }));
    return {
        id: "a".repeat(32),
        version: 2,
        chairs,
        watchers: 0,
        opened_by_me: false,
        hand: null,
        result: null,
        passed_in: null,
        series: null,
        aborted: null,
        options: null,
        style: null,
        bock: null,
        ended: null,
    };
}

export const RECORDING_OF = (key: string): string => `/voice/${key}.mp3`;

interface Options {
    motion?: MotionSetId;
    soundSet?: SoundSetId;
    voice?: boolean;
    muted?: boolean;
    background?: boolean;
    vibration?: boolean;
}

export function soundAt(port: FakePort, options: Options = {}): TableSound {
    return createTableSound({
        port,
        settings: () => ({ ...SETTINGS, muted: options.muted ?? false }),
        turnInBackground: () => options.background ?? false,
        vibrationOn: () => options.vibration ?? false,
        vibrate: (pattern) => port.vibrations.push(pattern),
        soundSet: () => SOUND_SETS[options.soundSet ?? "leise"],
        motion: () => (options.motion === undefined ? undefined : MOTION_SETS[options.motion]),
        voiceOn: () => options.voice ?? false,
        recording: (key) => (key === "voice.supra" ? undefined : RECORDING_OF(key)),
        recordings: () => [RECORDING_OF("voice.kontra"), RECORDING_OF("voice.re")],
    });
}

export const loudest = (port: FakePort): number => Math.max(...port.played.map(({ voice }) => voice.gain));
export const earliest = (port: FakePort): number => Math.min(...port.played.map(({ voice }) => voice.at));
