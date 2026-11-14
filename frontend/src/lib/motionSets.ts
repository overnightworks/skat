import type { Key } from "./words.ts";

export interface MotionSet {
    readonly id: string;
    /** The catalog key of the set's name. */
    readonly name: Key;
    /** From the cue to the moment a card touches the felt; the set's CSS keeps the same time. */
    readonly cardLandsSeconds: number;
    /** From the cue to the moment a bid's bubble has sprung up. */
    readonly bidSpringsSeconds: number;
    /** From the cue to the moment the Kontra stamp hits the felt. */
    readonly stampLandsSeconds: number;
    /** How long a finished trick lies still on the felt before it is swept; the set's CSS keeps no time of it. */
    readonly trickRestSeconds: number;
    /** From the sweep's start to the moment the trick has come together in the middle; the set's CSS keeps the same time. */
    readonly trickGatherSeconds: number;
    /** From the gathered trick to the moment it lies on its taker's pile; the set's CSS keeps the same time. */
    readonly trickGlideSeconds: number;
}

export const MOTION_SETS = {
    dezent: {
        id: "dezent",
        name: "sound.motionDezent",
        cardLandsSeconds: 0.18,
        bidSpringsSeconds: 0.04,
        stampLandsSeconds: 0.18,
        trickRestSeconds: 0.5,
        trickGatherSeconds: 0,
        trickGlideSeconds: 0.28,
    },
    verspielt: {
        id: "verspielt",
        name: "sound.motionVerspielt",
        cardLandsSeconds: 0.28,
        bidSpringsSeconds: 0.04,
        stampLandsSeconds: 0.3,
        trickRestSeconds: 0.8,
        trickGatherSeconds: 0.25,
        trickGlideSeconds: 0.75,
    },
} as const satisfies Record<string, MotionSet>;

export type MotionSetId = keyof typeof MOTION_SETS;

export const DEFAULT_MOTION_SET: MotionSetId = "verspielt";
