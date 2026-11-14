import type { NoiseVoice, ToneVoice, Voice } from "./sound.ts";
import type { Key } from "./words.ts";

export type SoundMoment =
    "card-played" | "bid-said" | "word-said" | "trick-swept" | "chair-taken" | "chair-stood" | "chair-opened";

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

const KNOCK_PITCH_HERTZ = 190;

// A wooden knock that falls from its pitch; the overtone sits a little above twice the pitch and falls as well.
function knock(at: number, gain: number, pitch = KNOCK_PITCH_HERTZ): readonly [ToneVoice, NoiseVoice, ToneVoice] {
    return [
        {
            kind: "tone",
            wave: "sine",
            at,
            seconds: 0.07,
            frequency: pitch,
            endFrequency: Math.round(pitch * 0.62),
            gain,
        },
        { kind: "noise", at, seconds: 0.025, frequency: 1300, quality: 3, gain: gain * 0.6 },
        {
            kind: "tone",
            wave: "triangle",
            at,
            seconds: 0.03,
            frequency: Math.round(pitch * 2.4),
            endFrequency: Math.round(pitch * 1.4),
            gain: gain * 0.15,
        },
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

/** A chair's sound starts this long after its cue, as the chair begins to move. */
const CHAIR_HIT_SECONDS = 0.1;
/** The second note of a chair's bells follows the first this far behind. */
const CHAIR_BELL_GAP_SECONDS = 0.1;

// A struck bell: its tone with two overtones that die away sooner.
function bell(
    at: number,
    frequency: number,
    gain: number,
    seconds: number,
): readonly [ToneVoice, ToneVoice, ToneVoice] {
    return [
        { kind: "tone", wave: "sine", at, seconds, frequency, gain },
        { kind: "tone", wave: "sine", at, seconds: seconds * 0.6, frequency: frequency * 2.01, gain: gain * 0.3 },
        { kind: "tone", wave: "sine", at, seconds: seconds * 0.3, frequency: frequency * 3.02, gain: gain * 0.12 },
    ];
}

// A dry knock of the chair on the floor.
function chairKnock(gain: number): readonly Voice[] {
    return knock(CHAIR_HIT_SECONDS, 0.32 * gain, 230);
}

// A chair that opens knocks lower and softer.
function chairKnockLow(gain: number): readonly Voice[] {
    return knock(CHAIR_HIT_SECONDS, 0.22 * gain, 140);
}

// The chair is pulled in with a scrape and knocks as it stands.
function chairScrapeKnock(gain: number): readonly Voice[] {
    return [
        {
            kind: "noise",
            at: CHAIR_HIT_SECONDS - 0.08,
            seconds: 0.22,
            frequency: 280,
            endFrequency: 760,
            quality: 7,
            gain: 0.2 * gain,
        },
        ...knock(CHAIR_HIT_SECONDS + 0.12, 0.34 * gain, 170),
    ];
}

// A chair that stands up again knocks on its own.
function chairKnockDeep(gain: number): readonly Voice[] {
    return knock(CHAIR_HIT_SECONDS, 0.34 * gain, 170);
}

// A chair that opens slides back with a soft scrape and settles with a thud.
function chairSlide(gain: number): readonly Voice[] {
    return [
        {
            kind: "noise",
            at: CHAIR_HIT_SECONDS,
            seconds: 0.26,
            frequency: 520,
            endFrequency: 200,
            quality: 2,
            gain: 0.18 * gain,
        },
        {
            kind: "tone",
            wave: "sine",
            at: CHAIR_HIT_SECONDS + 0.12,
            seconds: 0.12,
            frequency: 200,
            endFrequency: 120,
            gain: 0.2 * gain,
        },
    ];
}

// Two bells, the second higher: someone sits down.
function chairBellsUp(gain: number): readonly Voice[] {
    return [
        ...bell(CHAIR_HIT_SECONDS, 784, 0.14 * gain, 0.35),
        ...bell(CHAIR_HIT_SECONDS + CHAIR_BELL_GAP_SECONDS, 1047, 0.12 * gain, 0.35),
    ];
}

// Two bells, the second lower: someone stands up, or a chair opens.
function chairBellsDown(gain: number): readonly Voice[] {
    return [
        ...bell(CHAIR_HIT_SECONDS, 784, 0.14 * gain, 0.35),
        ...bell(CHAIR_HIT_SECONDS + CHAIR_BELL_GAP_SECONDS, 587, 0.1 * gain, 0.3),
    ];
}

type VoicesOf = (gain: number) => readonly Voice[];

// Each moment is brought to one loudness at the full volume, so no set and no moment sounds markedly quieter than another;
// the sets' test measures the result, and a voice that changes is levelled anew by the factor beside its name.
function levelled(voices: VoicesOf, level: number): VoicesOf {
    return (gain) => voices(gain * level);
}

export const SOUND_SETS = {
    leise: {
        id: "leise",
        name: "sound.setLeise",
        voices: {
            "card-played": levelled(cardSnap, 2.54),
            "bid-said": levelled(bidTip, 2.68),
            "word-said": levelled(knocksPlain, 0.66),
            "trick-swept": levelled(sweepSoft, 2.63),
            "chair-taken": levelled(chairKnock, 1.42),
            "chair-stood": levelled(chairKnock, 1.42),
            "chair-opened": levelled(chairKnockLow, 3.46),
        },
    },
    stammtisch: {
        id: "stammtisch",
        name: "sound.setStammtisch",
        voices: {
            "card-played": levelled(cardClap, 1.26),
            "bid-said": levelled(bidBlub, 1.09),
            "word-said": levelled(knocksDeep, 0.62),
            "trick-swept": levelled(sweepThud, 1.9),
            "chair-taken": levelled(chairScrapeKnock, 1.63),
            "chair-stood": levelled(chairKnockDeep, 1.63),
            "chair-opened": levelled(chairSlide, 1.83),
        },
    },
    funkeln: {
        id: "funkeln",
        name: "sound.setFunkeln",
        voices: {
            "card-played": levelled(cardGlint, 1.26),
            "bid-said": levelled(bidPair, 1.45),
            "word-said": levelled(knocksWave, 0.72),
            "trick-swept": levelled(sweepGlint, 1.56),
            "chair-taken": levelled(chairBellsUp, 0.78),
            "chair-stood": levelled(chairBellsDown, 0.85),
            "chair-opened": levelled(chairBellsDown, 0.85),
        },
    },
} as const satisfies Record<string, SoundSet>;

export type SoundSetId = keyof typeof SOUND_SETS;

export const DEFAULT_SOUND_SET: SoundSetId = "leise";
