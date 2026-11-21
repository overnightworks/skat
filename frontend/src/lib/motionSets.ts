import type { GatherSet } from "./takt/gather.ts";
import type { LandSet } from "./takt/land.ts";
import type { Key } from "./words.ts";

export interface MotionSet {
    readonly id: string;
    /** The catalog key of the set's name. */
    readonly name: Key;
    /** How a played card is thrown onto the felt; Takt plays it, and the set's CSS keeps none of it. */
    readonly land: LandSet;
    /** From the cue to the moment a bid's bubble has sprung up. */
    readonly bidSpringsSeconds: number;
    /** From the cue to the moment the Kontra stamp hits the felt. */
    readonly stampLandsSeconds: number;
    /** How a finished trick rests, lifts the card that took it and is gathered onto its taker's pile; Takt plays it, and the set's CSS keeps none of it. */
    readonly trick: GatherSet;
    /** How long a chair that is taken fills and its gold ring glows; the set's CSS keeps the same time. */
    readonly chairSitsSeconds: number;
    /** How long a chair that stands up or opens fades; the set's CSS keeps the same time. */
    readonly chairEmptiesSeconds: number;
    /** From the cue to the moment the result has risen and its stamp lands; the set's CSS keeps the same time. */
    readonly resultLandsSeconds: number;
    /** From the cue to the moment the gains begin to count up; the set's CSS keeps the same time. */
    readonly countStartsSeconds: number;
    /** How long the gains count up; the set's CSS keeps the same time. */
    readonly countSeconds: number;
    /** From the cue to the moment the cowbell has swung in over the nudged chair and rings; the set's CSS keeps the same time. */
    readonly bellRingsSeconds: number;
    /** From the cue to the moment a thrown emote has landed on the felt; the set's CSS keeps the same time. */
    readonly emoteLandsSeconds: number;
    /** How long a thrown emote stays on the felt after it landed, then fades; the set's CSS keeps the same time. */
    readonly emoteRestsSeconds: number;
    /** From a tap to the moment an object of the table makes its first move; the set's CSS keeps the same time. */
    readonly objectMovesSeconds: number;
    /** How many suit pieces a won result throws; none is none. */
    readonly confettiPieces: number;
}

export const MOTION_SETS = {
    dezent: {
        id: "dezent",
        name: "sound.motionDezent",
        land: {
            flightSeconds: 0.18,
            lift: 0.1,
            swell: 0.04,
            spin: [2, 5],
            grip: 14,
            ease: 0.85,
            squash: 0.015,
            flips: false,
        },
        bidSpringsSeconds: 0.04,
        stampLandsSeconds: 0.18,
        trick: {
            restSeconds: 0.5,
            liftAfterSeconds: 0.2,
            rise: 0.1,
            springs: false,
            gatherSeconds: 0,
            glideSeconds: 0.28,
            lastHoldSeconds: 0,
        },
        chairSitsSeconds: 0.9,
        chairEmptiesSeconds: 0.3,
        resultLandsSeconds: 0.52,
        countStartsSeconds: 0.3,
        countSeconds: 0.7,
        bellRingsSeconds: 0.18,
        emoteLandsSeconds: 0.3,
        emoteRestsSeconds: 1.8,
        objectMovesSeconds: 0.05,
        confettiPieces: 0,
    },
    verspielt: {
        id: "verspielt",
        name: "sound.motionVerspielt",
        land: {
            flightSeconds: 0.28,
            lift: 0.43,
            swell: 0.16,
            spin: [9, 22],
            grip: 12,
            ease: 0.6,
            squash: 0.04,
            flips: true,
        },
        bidSpringsSeconds: 0.04,
        stampLandsSeconds: 0.3,
        trick: {
            restSeconds: 0.8,
            liftAfterSeconds: 0.35,
            rise: 0.22,
            springs: true,
            gatherSeconds: 0.25,
            glideSeconds: 0.75,
            lastHoldSeconds: 0.23,
        },
        chairSitsSeconds: 1.4,
        chairEmptiesSeconds: 0.4,
        resultLandsSeconds: 0.83,
        countStartsSeconds: 0.3,
        countSeconds: 1.1,
        bellRingsSeconds: 0.3,
        emoteLandsSeconds: 0.83,
        emoteRestsSeconds: 2.4,
        objectMovesSeconds: 0.08,
        confettiPieces: 16,
    },
} as const satisfies Record<string, MotionSet>;

export type MotionSetId = keyof typeof MOTION_SETS;

export const DEFAULT_MOTION_SET: MotionSetId = "verspielt";
