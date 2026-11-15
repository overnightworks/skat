import type { NoiseVoice, ToneVoice, Voice } from "./sound.ts";
import type { Key } from "./words.ts";

export type SoundMoment =
    | "card-played"
    | "bid-said"
    | "word-said"
    | "trick-swept"
    | "turn-came"
    | "dealt"
    | "result-won"
    | "result-lost"
    | "chair-taken"
    | "chair-stood"
    | "chair-opened"
    | "nudged";

export interface SoundSet {
    readonly id: string;
    /** The catalog key of the set's name. */
    readonly name: Key;
    /** For each moment, the voices it sounds at the given gain (1 is a moment of the player's own). */
    readonly voices: Readonly<Record<SoundMoment, (gain: number) => readonly Voice[]>>;
    /** The ticks of the gains counting up over the given seconds, and the chime that ends them. */
    readonly counts: (gain: number, seconds: number) => readonly Voice[];
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

// Two partials above the pitch make a small bell of a sine.
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

// A quiet tone with a high partial.
function turnTone(gain: number): readonly [ToneVoice, ToneVoice] {
    return [
        { kind: "tone", wave: "sine", at: 0, seconds: 0.3, frequency: 660, gain: 0.16 * gain },
        { kind: "tone", wave: "sine", at: 0, seconds: 0.2, frequency: 1320, gain: 0.03 * gain },
    ];
}

// Two friendly bells, the second higher.
function turnBells(gain: number): readonly Voice[] {
    return [...bell(0, 523, 0.18 * gain, 0.3), ...bell(0.13, 784, 0.2 * gain, 0.25)];
}

// Three playful notes going up.
function turnRun(gain: number): readonly Voice[] {
    return [523, 659, 784].flatMap((frequency, index): Voice[] => [
        { kind: "tone", wave: "triangle", at: index * 0.09, seconds: 0.18, frequency, gain: 0.22 * gain },
        { kind: "tone", wave: "sine", at: index * 0.09, seconds: 0.08, frequency: frequency * 2, gain: 0.05 * gain },
    ]);
}

/** Cards land on the table this long after the cue and this far apart, as the cards of the hand fly in. */
const DEAL_FIRST_LANDING_SECONDS = 0.45;
const DEAL_LANDING_GAP_SECONDS = 0.055;
const DEAL_LANDING_CARDS = [2, 5, 8, 11, 14, 16] as const;
const DEAL_LANDINGS_SECONDS = DEAL_LANDING_CARDS.map(
    (card) => DEAL_FIRST_LANDING_SECONDS + card * DEAL_LANDING_GAP_SECONDS,
);
const SHUFFLE_BURSTS = 26;
const SHUFFLE_BURST_GAP_SECONDS = 0.016;

// The cards are dealt out with a soft snap each.
function dealSnaps(gain: number): readonly Voice[] {
    return DEAL_LANDINGS_SECONDS.flatMap((at) => [
        { kind: "noise", at, seconds: 0.045, frequency: 2800, quality: 0.9, gain: 0.22 * gain } as const,
        {
            kind: "tone",
            wave: "sine",
            at,
            seconds: 0.06,
            frequency: 170,
            endFrequency: 110,
            gain: 0.055 * gain,
        } as const,
    ]);
}

// A short shuffle, then the snaps.
function dealShuffled(gain: number): readonly Voice[] {
    const bursts = Array.from({ length: SHUFFLE_BURSTS }, (_, index): Voice => ({
        kind: "noise",
        at: index * SHUFFLE_BURST_GAP_SECONDS,
        seconds: 0.03,
        frequency: 1500 + ((index * 97) % 2200),
        quality: 0.8,
        gain: (0.16 + (index % 3) * 0.04) * gain,
    }));
    const snaps = DEAL_LANDINGS_SECONDS.map((at): Voice => ({
        kind: "noise",
        at,
        seconds: 0.045,
        frequency: 3000,
        quality: 0.9,
        gain: 0.3 * gain,
    }));
    return [...bursts, ...snaps];
}

// Quick flicks that climb.
function dealRiffle(gain: number): readonly Voice[] {
    return DEAL_LANDINGS_SECONDS.flatMap((at, index): Voice[] => {
        const frequency = 1800 + index * 190;
        return [
            {
                kind: "tone",
                wave: "triangle",
                at,
                seconds: 0.035,
                frequency,
                endFrequency: frequency * 0.7,
                gain: 0.12 * gain,
            },
            { kind: "noise", at, seconds: 0.025, frequency: frequency * 1.4, quality: 1.4, gain: 0.22 * gain },
        ];
    });
}

// The low blow of a stamp on the felt.
function stampBlow(gain: number): readonly [ToneVoice, NoiseVoice, NoiseVoice] {
    return [
        { kind: "tone", wave: "sine", at: 0, seconds: 0.22, frequency: 95, endFrequency: 48, gain },
        { kind: "noise", at: 0, seconds: 0.09, frequency: 420, quality: 0.7, gain: gain * 0.9 },
        { kind: "noise", at: 0, seconds: 0.025, frequency: 2600, quality: 1, gain: gain * 0.5 },
    ];
}

// The stamp, then one bell.
function resultWonBell(gain: number): readonly Voice[] {
    return [...stampBlow(0.5 * gain), ...bell(0.1, 784, 0.14 * gain, 0.28)];
}

// The stamp, then a note that sinks.
function resultLostSigh(gain: number): readonly Voice[] {
    return [
        ...stampBlow(0.5 * gain),
        {
            kind: "tone",
            wave: "triangle",
            at: 0.1,
            seconds: 0.28,
            frequency: 330,
            endFrequency: 290,
            gain: 0.16 * gain,
        },
    ];
}

// The stamp, then a rising chord of bells.
function resultWonChord(gain: number): readonly Voice[] {
    return [
        ...stampBlow(0.6 * gain),
        ...[523, 659, 784].flatMap((frequency, index) => bell(0.1 + index * 0.06, frequency, 0.15 * gain, 0.17)),
    ];
}

// The stamp, then two sinking notes.
function resultLostPair(gain: number): readonly Voice[] {
    return [
        ...stampBlow(0.6 * gain),
        { kind: "tone", wave: "triangle", at: 0.12, seconds: 0.16, frequency: 330, gain: 0.18 * gain },
        { kind: "tone", wave: "triangle", at: 0.2, seconds: 0.18, frequency: 262, gain: 0.18 * gain },
    ];
}

// The stamp, then a fanfare.
function resultWonFanfare(gain: number): readonly Voice[] {
    return [
        ...stampBlow(0.6 * gain),
        ...[523, 659, 784, 1047].flatMap((frequency, index): Voice[] => [
            { kind: "tone", wave: "square", at: 0.1 + index * 0.05, seconds: 0.12, frequency, gain: 0.06 * gain },
            ...bell(0.1 + index * 0.05, frequency, 0.1 * gain, 0.14),
        ]),
    ];
}

// The stamp, then four falling notes.
function resultLostFall(gain: number): readonly Voice[] {
    return [
        ...stampBlow(0.6 * gain),
        ...[392, 370, 349, 294].map((frequency, index): Voice => ({
            kind: "tone",
            wave: "sawtooth",
            at: 0.1 + index * 0.05,
            seconds: 0.12,
            frequency,
            endFrequency: frequency * 0.93,
            gain: 0.07 * gain,
        })),
    ];
}

const COUNT_TICKS = 16;
/** The chime that ends a count follows its last tick by this long. */
const COUNT_CHIME_AFTER_SECONDS = 0.02;

// The ticks fall at the pace the number climbs: quick at first, slowing as it settles.
function tickTimes(seconds: number): number[] {
    return Array.from(
        { length: COUNT_TICKS },
        (_, index) => (1 - (1 - (index + 1) / COUNT_TICKS) ** (1 / 3)) * seconds,
    );
}

// Dry little ticks.
function countTicks(gain: number, seconds: number): readonly Voice[] {
    return tickTimes(seconds).map((at): Voice => ({
        kind: "noise",
        at,
        seconds: 0.015,
        frequency: 4500,
        quality: 3,
        gain: 0.22 * gain,
    }));
}

// Ticks with one bell to close.
function countBell(gain: number, seconds: number): readonly Voice[] {
    return [
        ...tickTimes(seconds).flatMap((at): Voice[] => [
            { kind: "noise", at, seconds: 0.018, frequency: 4200, quality: 3, gain: 0.24 * gain },
            { kind: "tone", wave: "sine", at, seconds: 0.02, frequency: 1700, gain: 0.05 * gain },
        ]),
        ...bell(seconds + COUNT_CHIME_AFTER_SECONDS, 988, 0.16 * gain, 0.3),
    ];
}

// Coins that climb, two bells to close.
function countCoins(gain: number, seconds: number): readonly Voice[] {
    return [
        ...tickTimes(seconds).flatMap((at, index): Voice[] => [
            { kind: "tone", wave: "square", at, seconds: 0.045, frequency: 1100 + index * 55, gain: 0.05 * gain },
            { kind: "noise", at, seconds: 0.012, frequency: 5200, quality: 2, gain: 0.12 * gain },
        ]),
        ...[1318, 1760].flatMap((frequency, index) =>
            bell(seconds + COUNT_CHIME_AFTER_SECONDS + index * 0.08, frequency, 0.12 * gain, 0.2),
        ),
    ];
}

/** A chair's sound starts this long after its cue, as the chair begins to move. */
const CHAIR_HIT_SECONDS = 0.1;
/** The second note of a chair's bells follows the first this far behind. */
const CHAIR_BELL_GAP_SECONDS = 0.1;

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

/** The two strikes of a ringing cowbell are this far apart. */
const COWBELL_STRIKE_GAP_SECONDS = 0.17;

// One strike on a cowbell: two tones that are no octave apart, the upper a little under a fifth above the lower, and the click
// of the clapper.
function cowbellStrike(
    at: number,
    gain: number,
    wave: OscillatorType,
    pitch: number,
    seconds: number,
): readonly [ToneVoice, ToneVoice, NoiseVoice] {
    return [
        { kind: "tone", wave, at, seconds, frequency: pitch, gain },
        { kind: "tone", wave, at, seconds: seconds * 0.7, frequency: Math.round(pitch * 1.48), gain: gain * 0.7 },
        { kind: "noise", at, seconds: 0.02, frequency: 3400, quality: 1.5, gain: gain * 0.5 },
    ];
}

// A soft cowbell of sines, the second strike quieter.
function cowbellSoft(gain: number): readonly Voice[] {
    return [
        ...cowbellStrike(0, 0.2 * gain, "sine", 587, 0.26),
        ...cowbellStrike(COWBELL_STRIKE_GAP_SECONDS, 0.14 * gain, "sine", 587, 0.26),
    ];
}

// A clanking cowbell of squares, as drum machines play it.
function cowbellClank(gain: number): readonly Voice[] {
    return [
        ...cowbellStrike(0, 0.16 * gain, "square", 540, 0.22),
        ...cowbellStrike(COWBELL_STRIKE_GAP_SECONDS, 0.16 * gain, "square", 540, 0.3),
    ];
}

// A bright cowbell of triangles, the second strike higher.
function cowbellBright(gain: number): readonly Voice[] {
    return [
        ...cowbellStrike(0, 0.2 * gain, "triangle", 680, 0.22),
        ...cowbellStrike(COWBELL_STRIKE_GAP_SECONDS, 0.2 * gain, "triangle", 820, 0.3),
    ];
}

type VoicesOf = (gain: number) => readonly Voice[];

// Each moment is brought to one loudness at the full volume, so no set and no moment sounds markedly quieter than another;
// the sets' test measures the result, and a voice that changes is levelled anew by the factor beside its name.
function levelled(voices: VoicesOf, level: number): VoicesOf {
    return (gain) => voices(gain * level);
}

type CountsOf = (gain: number, seconds: number) => readonly Voice[];

function levelledCounts(counts: CountsOf, level: number): CountsOf {
    return (gain, seconds) => counts(gain * level, seconds);
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
            "turn-came": levelled(turnTone, 1.01),
            dealt: levelled(dealSnaps, 3.38),
            "result-won": levelled(resultWonBell, 0.92),
            "result-lost": levelled(resultLostSigh, 1.02),
            "chair-taken": levelled(chairKnock, 1.42),
            "chair-stood": levelled(chairKnock, 1.42),
            "chair-opened": levelled(chairKnockLow, 3.46),
            nudged: levelled(cowbellSoft, 0.64),
        },
        counts: levelledCounts(countTicks, 4.7),
    },
    stammtisch: {
        id: "stammtisch",
        name: "sound.setStammtisch",
        voices: {
            "card-played": levelled(cardClap, 1.26),
            "bid-said": levelled(bidBlub, 1.09),
            "word-said": levelled(knocksDeep, 0.62),
            "trick-swept": levelled(sweepThud, 1.9),
            "turn-came": levelled(turnBells, 0.63),
            dealt: levelled(dealShuffled, 1.93),
            "result-won": levelled(resultWonChord, 0.78),
            "result-lost": levelled(resultLostPair, 1),
            "chair-taken": levelled(chairScrapeKnock, 1.63),
            "chair-stood": levelled(chairKnockDeep, 1.63),
            "chair-opened": levelled(chairSlide, 1.83),
            nudged: levelled(cowbellClank, 0.5),
        },
        counts: levelledCounts(countBell, 1),
    },
    funkeln: {
        id: "funkeln",
        name: "sound.setFunkeln",
        voices: {
            "card-played": levelled(cardGlint, 1.26),
            "bid-said": levelled(bidPair, 1.45),
            "word-said": levelled(knocksWave, 0.72),
            "trick-swept": levelled(sweepGlint, 1.56),
            "turn-came": levelled(turnRun, 0.71),
            dealt: levelled(dealRiffle, 2.71),
            "result-won": levelled(resultWonFanfare, 0.64),
            "result-lost": levelled(resultLostFall, 1.17),
            "chair-taken": levelled(chairBellsUp, 0.78),
            "chair-stood": levelled(chairBellsDown, 0.85),
            "chair-opened": levelled(chairBellsDown, 0.85),
            nudged: levelled(cowbellBright, 0.7),
        },
        counts: levelledCounts(countCoins, 1.09),
    },
} as const satisfies Record<string, SoundSet>;

export type SoundSetId = keyof typeof SOUND_SETS;

export const DEFAULT_SOUND_SET: SoundSetId = "leise";
