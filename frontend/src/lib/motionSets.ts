import type { Key } from "./words.ts";

export interface MotionSet {
    readonly id: string;
    /** The catalog key of the set's name. */
    readonly name: Key;
    /** From the cue to the moment a card touches the felt; the set's CSS keeps the same time. */
    readonly cardLandsSeconds: number;
}

export const MOTION_SETS = {
    dezent: { id: "dezent", name: "sound.motionDezent", cardLandsSeconds: 0.18 },
    verspielt: { id: "verspielt", name: "sound.motionVerspielt", cardLandsSeconds: 0.28 },
} as const satisfies Record<string, MotionSet>;

export type MotionSetId = keyof typeof MOTION_SETS;

export const DEFAULT_MOTION_SET: MotionSetId = "verspielt";
