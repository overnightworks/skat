import type { AuctionAction } from "../../routes/(start)/tables.ts";
import { fork } from "./seed.ts";
import { phase, type Pose, type Timeline, type Track } from "./timeline.ts";

/** How a motion set tells an auction: the pace of the words one update brings, and how the counter follows them. */
export interface BidSet {
    /** The least and the most seconds a „Ja“ or a „Weg“ waits after the word before it. */
    readonly answerAfterSeconds: readonly [number, number];
    /** The least and the most seconds a bid waits after the word before it. */
    readonly bidAfterSeconds: readonly [number, number];
    /** How long the table stays quiet once a word has been spoken, before the next is told. */
    readonly breathSeconds: number;
    /** How long a drum of the counter takes to roll to its digit. */
    readonly rollSeconds: number;
    /** How much a drum swings past its digit as it arrives, in drum heights; none rolls straight in. */
    readonly swing: number;
    /** How much later each drum starts to roll than the drum to its right. */
    readonly staggerSeconds: number;
    /** How long the duel line takes to show a new pair. */
    readonly duelAppearsSeconds: number;
}

/** A word of a run: its number among the words of its auction, which every seat counts alike, and what it says. */
export interface ToldWord {
    readonly step: number;
    readonly action: AuctionAction;
}

/**
 * How long after the word before it a word of a run is told: the pause its set draws for it from the game's seed, or
 * the `spokenSeconds` the voice takes for the word before it and a breath, whichever is longer. A seat that hears no
 * voice keeps the drawn pause, which is the same on every seat.
 */
export function toldAfterSeconds(set: BidSet, seed: string, word: ToldWord, spokenSeconds: number): number {
    const [least, most] = word.action === "bid" ? set.bidAfterSeconds : set.answerAfterSeconds;
    const pause = fork(seed, `bid/${String(word.step)}/pause`).between(least, most);
    return Math.max(pause, spokenSeconds + set.breathSeconds);
}

/** One drum of the counter as the page measured it: its height, and its place counted from the ones. */
export interface Drum {
    readonly height: number;
    readonly place: number;
}

export interface RollTracks {
    /** The digit the drum shows now; the stylesheet draws the digit before it right above. */
    readonly reel: Track<Pose>;
}

const easedOut = (share: number): number => 1 - (1 - share) ** 3;

/**
 * A drum rolls to its digit: the digit comes up from below by the drum's height while the one before it leaves above,
 * each drum a little after the one to its right.
 */
export function rollTimeline(set: BidSet, { height, place }: Drum): Timeline<RollTracks> {
    const starts = place * set.staggerSeconds;
    const reel = (seconds: number): Pose => {
        const share = phase(seconds, starts, set.rollSeconds);
        const rolled = easedOut(share) + set.swing * Math.sin(Math.PI * share) * share;
        return { x: 0, y: height * (1 - rolled), turn: 0, wide: 1, tall: 1, opacity: 1 };
    };
    return { seconds: starts + set.rollSeconds, tracks: { reel } };
}

/** The duel line shows a new pair: how much of it is seen. */
export function duelTimeline(set: BidSet): Timeline<{ readonly line: Track<number> }> {
    return {
        seconds: set.duelAppearsSeconds,
        tracks: { line: (seconds) => phase(seconds, 0, set.duelAppearsSeconds) },
    };
}
