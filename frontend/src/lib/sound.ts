/** Every voice starts `at` seconds into its moment and lasts `seconds`. */
interface VoiceShape {
    readonly at: number;
    readonly seconds: number;
    readonly frequency: number;
    /** The pitch the voice glides to over its length; the pitch stays when it is absent. */
    readonly endFrequency?: number;
    readonly gain: number;
}

/** An oscillator. */
export interface ToneVoice extends VoiceShape {
    readonly kind: "tone";
    readonly wave: OscillatorType;
}

/** A band-passed noise burst. */
export interface NoiseVoice extends VoiceShape {
    readonly kind: "noise";
    /** How narrow the band around the frequency is. */
    readonly quality: number;
}

export type Voice = ToneVoice | NoiseVoice;

/** What the engine needs of an audio device; the adapter alone knows Web Audio. */
export interface AudioPort {
    /** Whether a sound starts now; a hidden window is ready only for a sound that was asked for there. */
    ready(whenHidden: boolean): boolean;
    /** Wakes the device inside a player's gesture; it never rejects, and a device that stays silent stays not ready. */
    resume(): Promise<void>;
    setLoudness(gain: number): void;
    playVoice(voice: Voice, afterSeconds: number): void;
    /** Fetches and decodes recordings so they play at once; it never rejects, and one that failed is fetched again by the next call. */
    loadRecordings(urls: readonly string[]): Promise<void>;
    /** Plays a recording that is loaded; one that is not is skipped. */
    playRecording(url: string, afterSeconds: number): void;
}

export interface SoundSettings {
    readonly muted: boolean;
    /** From 0 to 100. */
    readonly volume: number;
}

export const DEFAULT_SOUND_SETTINGS: SoundSettings = { muted: false, volume: 70 };

const FULL_VOLUME = 100;
const LOUDNESS_CURVE = 1.6;
const LEAD_SECONDS = 0.03;

/** Where a sound is wanted. */
export interface Hearing {
    /** The sound also plays while the window is hidden. */
    readonly whenHidden: boolean;
}

const HEARD_IN_VIEW: Hearing = { whenHidden: false };

export interface Sound {
    play(voices: readonly Voice[], hearing?: Hearing): void;
    /** Plays a recording `afterSeconds` from now under the same mute and volume. */
    speak(url: string, afterSeconds: number): void;
    prepare(urls: readonly string[]): Promise<void>;
    resume(): Promise<void>;
}

/** A sound that comes late is worse than none, so a voice list plays at once or not at all. */
export function createSound(port: AudioPort, settings: () => SoundSettings): Sound {
    // Sets the loudness for the sound about to start, or says the device stays silent.
    function audible({ whenHidden }: Hearing): boolean {
        const { muted, volume } = settings();
        if (muted || !port.ready(whenHidden)) return false;
        port.setLoudness((volume / FULL_VOLUME) ** LOUDNESS_CURVE);
        return true;
    }

    return {
        play(voices, hearing = HEARD_IN_VIEW) {
            if (!audible(hearing)) return;
            for (const voice of voices) port.playVoice(voice, LEAD_SECONDS);
        },
        speak(url, afterSeconds) {
            if (audible(HEARD_IN_VIEW)) port.playRecording(url, LEAD_SECONDS + afterSeconds);
        },
        prepare: (urls) => port.loadRecordings(urls),
        resume: () => port.resume(),
    };
}
