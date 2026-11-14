import { describe, expect, it } from "vitest";
import type { Voice } from "./sound.ts";
import { SOUND_SETS, type SoundMoment } from "./soundSets.ts";
import { LIMITER_THRESHOLD_DECIBELS } from "./webAudio.ts";

const MOMENTS: SoundMoment[] = ["card-played", "bid-said", "word-said"];
const LONGEST_SOUND_SECONDS = 0.6;
/** The most a moment may stray from the target and still sound as loud as the others. */
const TOLERANCE_DECIBELS = 1.5;
/** The most the loudest peak may stay below the limiter before the sets are called too quiet. */
const HEADROOM_LEFT_DECIBELS = 1.5;

const SAMPLE_RATE = 48000;
const RENDER_SECONDS = 0.8;
const NOISE_DRAWS = 8;
const TONE_ATTACK_SECONDS = 0.004;
const NOISE_ATTACK_SECONDS = 0.003;
const TAIL_SECONDS = 0.05;
const ENVELOPE_FLOOR = 0.0001;
const GAIN_FLOOR = 0.0002;

const WINDOW_SECONDS = 0.2;
const SPEAKER_CUTOFF_HERTZ = 200;

// A second-order Butterworth high-pass at the cutoff below which a phone's speaker plays nothing.
function highPassed(samples: ArrayLike<number>): Float64Array {
    const omega = (2 * Math.PI * SPEAKER_CUTOFF_HERTZ) / SAMPLE_RATE;
    const alpha = Math.sin(omega) / Math.SQRT2;
    const scale = 1 + alpha;
    const forward = (1 + Math.cos(omega)) / 2 / scale;
    const back1 = (-2 * Math.cos(omega)) / scale;
    const back2 = (1 - alpha) / scale;
    const filtered = new Float64Array(samples.length);
    let [previousIn, olderIn, previousOut, olderOut] = [0, 0, 0, 0];
    for (let index = 0; index < samples.length; index += 1) {
        const input = samples[index] as number;
        const output = forward * (input - 2 * previousIn + olderIn) - back1 * previousOut - back2 * olderOut;
        [olderIn, previousIn, olderOut, previousOut] = [previousIn, input, previousOut, output];
        filtered[index] = output;
    }
    return filtered;
}

/** The mean power in decibels of the loudest 200 ms, as a phone's speaker plays it; a shorter sound counts by its energy, as the ear adds it up. */
function loudnessDecibels(samples: ArrayLike<number>): number {
    const filtered = highPassed(samples);
    const window = Math.round(WINDOW_SECONDS * SAMPLE_RATE);
    let energy = 0;
    let loudest = 0;
    for (let index = 0; index < filtered.length; index += 1) {
        const entering = filtered[index] as number;
        const leaving = index >= window ? (filtered[index - window] as number) : 0;
        energy += entering * entering - leaving * leaving;
        loudest = Math.max(loudest, energy / window);
    }
    return 10 * Math.log10(loudest);
}

function peakOf(samples: ArrayLike<number>): number {
    return Array.from(samples).reduce((peak, sample) => Math.max(peak, Math.abs(sample)), 0);
}

const WAVES: Partial<Record<OscillatorType, (phase: number) => number>> = {
    sine: (phase) => Math.sin(2 * Math.PI * phase),
    triangle: (phase) => 4 * Math.abs(phase - Math.floor(phase + 0.5)) - 1,
};

// The same noise on every run, so the measurement is repeatable.
function randomSource(seed: number): () => number {
    let state = seed;
    return () => {
        state = (state + 0x6d2b79f5) | 0;
        let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
        mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
        return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
    };
}

// The pitch of a voice at a time: held, or gliding exponentially to its end over the voice's length.
function frequencyAt(voice: Voice, attack: number, time: number): number {
    if (voice.endFrequency === undefined) return voice.frequency;
    const progress = Math.min(Math.max((time - attack) / voice.seconds, 0), 1);
    return voice.frequency * (voice.endFrequency / voice.frequency) ** progress;
}

// A quick rise to the voice's gain and an exponential fall, as the engine draws it.
function envelopeAt(voice: Voice, attack: number, time: number): number {
    const peak = Math.max(voice.gain, GAIN_FLOOR);
    if (time < attack) return ENVELOPE_FLOOR * (peak / ENVELOPE_FLOOR) ** (time / attack);
    const fall = Math.min((time - attack) / voice.seconds, 1);
    return peak * (ENVELOPE_FLOOR / peak) ** fall;
}

// A band-pass filter of constant peak gain, with a centre that may glide from sample to sample.
function bandPass(input: number, centre: number, quality: number, memory: number[]): number {
    const omega = (2 * Math.PI * centre) / SAMPLE_RATE;
    const alpha = Math.sin(omega) / (2 * quality);
    const scale = 1 + alpha;
    const [previousIn, olderIn, previousOut, olderOut] = memory as [number, number, number, number];
    const output = (alpha * (input - olderIn) + 2 * Math.cos(omega) * previousOut - (1 - alpha) * olderOut) / scale;
    memory.splice(0, 4, input, previousIn, output, previousOut);
    return output;
}

function renderVoice(voice: Voice, into: Float64Array, random: () => number): void {
    const attack = voice.kind === "tone" ? TONE_ATTACK_SECONDS : NOISE_ATTACK_SECONDS;
    const length = Math.min(Math.round((voice.at + attack + voice.seconds + TAIL_SECONDS) * SAMPLE_RATE), into.length);
    const first = Math.round(voice.at * SAMPLE_RATE);
    const memory = [0, 0, 0, 0];
    let phase = 0;
    for (let index = first; index < length; index += 1) {
        const time = (index - first) / SAMPLE_RATE;
        const frequency = frequencyAt(voice, attack, time);
        phase += frequency / SAMPLE_RATE;
        const source =
            voice.kind === "tone"
                ? (WAVES[voice.wave] as (phase: number) => number)(phase)
                : bandPass(random() * 2 - 1, frequency, voice.quality, memory);
        into[index] = (into[index] as number) + source * envelopeAt(voice, attack, time);
    }
}

/** The samples a moment makes at the full volume, as the engine's graph would play it with one draw of the noise. */
function renderMoment(voices: readonly Voice[], seed: number): Float64Array {
    const samples = new Float64Array(Math.round(RENDER_SECONDS * SAMPLE_RATE));
    const random = randomSource(seed);
    for (const voice of voices) renderVoice(voice, samples, random);
    return samples;
}

// The page draws its noise anew, so a moment is measured over several draws.
function renderDraws(voices: readonly Voice[]): Float64Array[] {
    return Array.from({ length: NOISE_DRAWS }, (_, seed) => renderMoment(voices, seed + 1));
}

interface Measure {
    readonly set: string;
    readonly moment: SoundMoment;
    readonly decibels: number;
    readonly peak: number;
}

// Every moment of every set at the full volume, its loudness the mean over the draws and its peak the highest of them.
const MEASURES: Measure[] = Object.values(SOUND_SETS).flatMap((set) =>
    MOMENTS.map((moment) => {
        const draws = renderDraws(set.voices[moment](1));
        const decibels = draws.map(loudnessDecibels);
        return {
            set: set.id,
            moment,
            decibels: decibels.reduce((sum, each) => sum + each, 0) / decibels.length,
            peak: Math.max(...draws.map(peakOf)),
        };
    }),
);
const LIMITER_CEILING = 10 ** (LIMITER_THRESHOLD_DECIBELS / 20);

describe.each(Object.values(SOUND_SETS))("the set $id", (set) => {
    it.each(MOMENTS)("sounds %s in under 600 ms", (moment) => {
        const voices = set.voices[moment](1);

        expect(voices.length).toBeGreaterThan(0);
        for (const voice of voices) expect(voice.at + voice.seconds).toBeLessThan(LONGEST_SOUND_SECONDS);
    });

    it.each(MOMENTS)("sounds %s louder at a higher gain", (moment) => {
        const loudest = (gain: number): number => Math.max(...set.voices[moment](gain).map((voice) => voice.gain));

        expect(loudest(1)).toBeGreaterThan(loudest(0.5));
    });
});

describe("the sets together", () => {
    it("sound every moment within a few decibels of one loudness", () => {
        const loudness = MEASURES.map((measure) => measure.decibels);

        expect(Math.max(...loudness) - Math.min(...loudness)).toBeLessThanOrEqual(2 * TOLERANCE_DECIBELS);
    });

    it.each(MEASURES)("sound $moment of $set below the limiter's threshold at the full volume", ({ peak }) => {
        expect(peak).toBeLessThanOrEqual(LIMITER_CEILING);
    });

    it("use the headroom the limiter leaves", () => {
        const highestPeak = Math.max(...MEASURES.map((measure) => measure.peak));

        expect(20 * Math.log10(LIMITER_CEILING / highestPeak)).toBeLessThanOrEqual(HEADROOM_LEFT_DECIBELS);
    });
});
