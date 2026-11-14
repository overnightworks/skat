import type { NoiseVoice, ToneVoice, Voice } from "./sound.ts";
import type { Key } from "./words.ts";

export type SoundMoment = "card-played" | "bid-said" | "word-said" | "trick-swept";

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

/** The two knocks of a Kontra or a Re are this far apart. */
const KNOCK_GAP_SECONDS = 0.12;

function knock(at: number, gain: number): readonly [ToneVoice, NoiseVoice, ToneVoice] {
    return [
        { kind: "tone", wave: "sine", at, seconds: 0.07, frequency: 190, endFrequency: 118, gain },
        { kind: "noise", at, seconds: 0.025, frequency: 1300, quality: 3, gain: gain * 0.6 },
        { kind: "tone", wave: "triangle", at, seconds: 0.03, frequency: 456, endFrequency: 266, gain: gain * 0.15 },
    ];
}

// A light tap of the tongue.
function bidTip(gain: number): readonly [ToneVoice, NoiseVoice] {
    return [
        { kind: "tone", wave: "sine", at: 0, seconds: 0.03, frequency: 900, gain: 0.18 * gain },
        { kind: "noise", at: 0, seconds: 0.02, frequency: 3000, quality: 1, gain: 0.2 * gain },
    ];
}

// A bubble that blubs upward.
function bidBlub(gain: number): readonly [ToneVoice] {
    return [{ kind: "tone", wave: "sine", at: 0, seconds: 0.09, frequency: 380, endFrequency: 760, gain: 0.3 * gain }];
}

// Two short notes, the second higher.
function bidPair(gain: number): readonly [ToneVoice, ToneVoice] {
    return [
        { kind: "tone", wave: "triangle", at: 0, seconds: 0.05, frequency: 660, gain: 0.22 * gain },
        { kind: "tone", wave: "triangle", at: 0.06, seconds: 0.07, frequency: 880, gain: 0.22 * gain },
    ];
}

function knocksPlain(gain: number): readonly Voice[] {
    return [...knock(0, 0.55 * gain), ...knock(KNOCK_GAP_SECONDS, 0.55 * gain)];
}

// The second knock lands with a deep blow.
function knocksDeep(gain: number): readonly Voice[] {
    return [
        ...knock(0, 0.6 * gain),
        ...knock(KNOCK_GAP_SECONDS, 0.6 * gain),
        {
            kind: "tone",
            wave: "sine",
            at: KNOCK_GAP_SECONDS,
            seconds: 0.3,
            frequency: 70,
            endFrequency: 42,
            gain: 0.55 * gain,
        },
    ];
}

// The second knock runs out in a wave.
function knocksWave(gain: number): readonly Voice[] {
    return [
        ...knock(0, 0.5 * gain),
        ...knock(KNOCK_GAP_SECONDS, 0.5 * gain),
        {
            kind: "noise",
            at: KNOCK_GAP_SECONDS,
            seconds: 0.38,
            frequency: 400,
            endFrequency: 3200,
            quality: 1.4,
            gain: 0.22 * gain,
        },
    ];
}

/** The swept trick sounds this long, whatever the time its glide takes. */
const SWEEP_SECONDS = 0.3;

// A soft wipe over the felt.
function sweepSoft(gain: number): readonly [NoiseVoice] {
    return [
        {
            kind: "noise",
            at: 0,
            seconds: SWEEP_SECONDS,
            frequency: 900,
            endFrequency: 2600,
            quality: 0.8,
            gain: 0.3 * gain,
        },
    ];
}

// A wipe that lands with a low thud at its end.
function sweepThud(gain: number): readonly [NoiseVoice, ToneVoice] {
    return [
        {
            kind: "noise",
            at: 0,
            seconds: SWEEP_SECONDS,
            frequency: 700,
            endFrequency: 2400,
            quality: 0.7,
            gain: 0.45 * gain,
        },
        {
            kind: "tone",
            wave: "sine",
            at: SWEEP_SECONDS * 0.85,
            seconds: 0.12,
            frequency: 130,
            endFrequency: 70,
            gain: 0.3 * gain,
        },
    ];
}

// A bright wipe with two glints at its end.
function sweepGlint(gain: number): readonly [NoiseVoice, ToneVoice, ToneVoice] {
    return [
        {
            kind: "noise",
            at: 0,
            seconds: SWEEP_SECONDS,
            frequency: 600,
            endFrequency: 4200,
            quality: 2,
            gain: 0.35 * gain,
        },
        { kind: "tone", wave: "sine", at: SWEEP_SECONDS * 0.7, seconds: 0.1, frequency: 1318, gain: 0.12 * gain },
        { kind: "tone", wave: "sine", at: SWEEP_SECONDS * 0.85, seconds: 0.12, frequency: 1760, gain: 0.12 * gain },
    ];
}

export const SOUND_SETS = {
    leise: {
        id: "leise",
        name: "sound.setLeise",
        voices: {
            "card-played": cardSnap,
            "bid-said": bidTip,
            "word-said": knocksPlain,
            "trick-swept": sweepSoft,
        },
    },
    stammtisch: {
        id: "stammtisch",
        name: "sound.setStammtisch",
        voices: {
            "card-played": cardClap,
            "bid-said": bidBlub,
            "word-said": knocksDeep,
            "trick-swept": sweepThud,
        },
    },
    funkeln: {
        id: "funkeln",
        name: "sound.setFunkeln",
        voices: {
            "card-played": cardGlint,
            "bid-said": bidPair,
            "word-said": knocksWave,
            "trick-swept": sweepGlint,
        },
    },
} as const satisfies Record<string, SoundSet>;

export type SoundSetId = keyof typeof SOUND_SETS;

export const DEFAULT_SOUND_SET: SoundSetId = "leise";
