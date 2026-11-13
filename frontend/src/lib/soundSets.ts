import type { NoiseVoice, ToneVoice, Voice } from "./sound.ts";
import type { Key } from "./words.ts";

export type SoundMoment = "card-played";

export interface SoundSet {
    readonly id: string;
    /** The catalog key of the set's name. */
    readonly name: Key;
    /** For each moment, the voices it sounds at the given gain (1 is a moment of the player's own). */
    readonly voices: Readonly<Record<SoundMoment, (gain: number) => readonly Voice[]>>;
}

const CARD_LEVEL = 0.45;
const CARD_THUMP_SHARE = 0.25;

function cardSnap(gain: number): readonly [NoiseVoice, ToneVoice] {
    return [
        { kind: "noise", at: 0, seconds: 0.045, frequency: 3200, quality: 0.9, gain: CARD_LEVEL * gain },
        {
            kind: "tone",
            wave: "sine",
            at: 0,
            seconds: 0.06,
            frequency: 170,
            endFrequency: 110,
            gain: CARD_LEVEL * gain * CARD_THUMP_SHARE,
        },
    ];
}

// Dry wood under a full clap.
function cardClap(gain: number): readonly [NoiseVoice, NoiseVoice, ToneVoice] {
    return [
        { kind: "noise", at: 0, seconds: 0.07, frequency: 2200, quality: 0.7, gain: 0.7 * gain },
        { kind: "noise", at: 0, seconds: 0.05, frequency: 600, quality: 1, gain: 0.4 * gain },
        { kind: "tone", wave: "sine", at: 0, seconds: 0.1, frequency: 150, endFrequency: 80, gain: 0.3 * gain },
    ];
}

// A bright pock with a small glint after it.
function cardGlint(gain: number): readonly [ToneVoice, NoiseVoice, ToneVoice] {
    return [
        { kind: "tone", wave: "sine", at: 0, seconds: 0.07, frequency: 620, endFrequency: 300, gain: 0.25 * gain },
        { kind: "noise", at: 0, seconds: 0.04, frequency: 3800, quality: 1.2, gain: 0.45 * gain },
        { kind: "tone", wave: "triangle", at: 0.055, seconds: 0.05, frequency: 880, gain: 0.08 * gain },
    ];
}

export const SOUND_SETS = {
    leise: { id: "leise", name: "sound.setLeise", voices: { "card-played": cardSnap } },
    stammtisch: { id: "stammtisch", name: "sound.setStammtisch", voices: { "card-played": cardClap } },
    funkeln: { id: "funkeln", name: "sound.setFunkeln", voices: { "card-played": cardGlint } },
} as const satisfies Record<string, SoundSet>;

export type SoundSetId = keyof typeof SOUND_SETS;

export const DEFAULT_SOUND_SET: SoundSetId = "leise";
