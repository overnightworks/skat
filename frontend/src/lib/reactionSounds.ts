import type { Voice } from "./sound.ts";
import type { Reaction } from "../routes/(start)/reaction.ts";

/** How a sound set colours the reactions: the wave of its tones and how high it pitches everything. */
export interface Timbre {
    readonly wave: OscillatorType;
    readonly pitch: number;
}

/** The reactions sound softer than the cues, which a game waits for. */
const REACTION_LEVEL = 0.5;
const KNOCK_GAP_SECONDS = 0.13;

function burst(at: number, hertz: number, seconds: number, gain: number, quality = 0.8): Voice {
    return { kind: "noise", at, seconds, frequency: hertz, quality, gain };
}

function tone(wave: OscillatorType, at: number, hertz: number, endHertz: number, seconds: number, gain: number): Voice {
    return { kind: "tone", wave, at, seconds, frequency: hertz, endFrequency: endHertz, gain };
}

// Two glasses meet: a bright ring and its overtone, and a tick of glass.
function clink(at: number, timbre: Timbre, gain: number): Voice[] {
    return [
        tone("sine", at, 2350 * timbre.pitch, 2300 * timbre.pitch, 0.16, 0.22 * gain),
        tone("sine", at + 0.01, 3150 * timbre.pitch, 3100 * timbre.pitch, 0.12, 0.14 * gain),
        burst(at, 5200, 0.02, 0.25 * gain, 1.4),
    ];
}

// A dry knock of wood on wood.
function wood(at: number, timbre: Timbre, gain: number): Voice[] {
    return [
        tone("sine", at, 260 * timbre.pitch, 150 * timbre.pitch, 0.07, 0.4 * gain),
        burst(at, 1700, 0.03, 0.3 * gain),
    ];
}

function clap(timbre: Timbre, gain: number): Voice[] {
    return [0, 0.07, 0.13, 0.22].map((at, index) =>
        burst(at, (1900 - index * 120) * timbre.pitch, 0.05, 0.5 * gain, 0.7),
    );
}

function laugh(timbre: Timbre, gain: number): Voice[] {
    return [0, 0.13, 0.26, 0.39].map((at, index) =>
        tone(timbre.wave, at, (360 - index * 25) * timbre.pitch, (270 - index * 20) * timbre.pitch, 0.1, 0.28 * gain),
    );
}

function gasp(timbre: Timbre, gain: number): Voice[] {
    return [
        burst(0, 900 * timbre.pitch, 0.25, 0.4 * gain, 0.8),
        tone(timbre.wave, 0, 420 * timbre.pitch, 720 * timbre.pitch, 0.2, 0.14 * gain),
    ];
}

function fire(timbre: Timbre, gain: number): Voice[] {
    return [
        burst(0, 520 * timbre.pitch, 0.35, 0.5 * gain, 0.5),
        ...[0.08, 0.15, 0.22, 0.3].map((at) => burst(at, 3000 * timbre.pitch, 0.02, 0.3 * gain, 1)),
    ];
}

function cheers(timbre: Timbre, gain: number): Voice[] {
    return [...clink(0, timbre, gain), ...clink(0.17, { ...timbre, pitch: timbre.pitch * 0.9 }, gain * 0.8)];
}

function knock(timbre: Timbre, gain: number): Voice[] {
    return [...wood(0, timbre, gain), ...wood(KNOCK_GAP_SECONDS, timbre, gain)];
}

function cocktail(timbre: Timbre, gain: number): Voice[] {
    return [
        ...clink(0, timbre, gain),
        ...[0.12, 0.19, 0.25].map((at, index) =>
            tone("sine", at, 600 + index * 120, 1000 + index * 160, 0.05, 0.1 * gain),
        ),
    ];
}

function shell(timbre: Timbre, gain: number): Voice[] {
    return [
        ...[0, 0.04, 0.09].map((at) => burst(at, 3500 * timbre.pitch, 0.025, 0.3 * gain, 1.2)),
        burst(0.05, 700 * timbre.pitch, 0.3, 0.25 * gain, 0.5),
    ];
}

function coaster(timbre: Timbre, gain: number): Voice[] {
    return [...wood(0, timbre, gain), ...wood(0.08, { ...timbre, pitch: timbre.pitch * 1.2 }, gain * 0.5)];
}

function lamp(timbre: Timbre, gain: number): Voice[] {
    return [
        burst(0, 4000, 0.012, 0.5 * gain, 1.2),
        tone("sine", 0.01, 110 * timbre.pitch, 105 * timbre.pitch, 0.3, 0.18 * gain),
        tone("sine", 0.01, 220 * timbre.pitch, 210 * timbre.pitch, 0.35, 0.08 * gain),
    ];
}

const SOUNDS: Record<Reaction, (timbre: Timbre, gain: number) => Voice[]> = {
    clap,
    laugh,
    gasp,
    fire,
    cheers,
    knock,
    cocktail,
    shell,
    coaster,
    lamp,
};

/** The voices of a reaction in the colour of a sound set, at the given gain (1 is the full cue volume). */
export function reactionVoices(reaction: Reaction, timbre: Timbre, gain: number): readonly Voice[] {
    return SOUNDS[reaction](timbre, gain * REACTION_LEVEL);
}
