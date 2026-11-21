import type { AuctionAction } from "../../routes/(start)/tables.ts";
import { fork } from "./seed.ts";
import { phase, type Pose, type Timeline, type Track } from "./timeline.ts";

/** How a motion set tells an auction: the pace of the words one update brings, and how the counter follows them. */
export interface BidSet {
    /** The least and the most seconds a „Ja“ or a „Weg“ waits after the word before it, in a run that has the time. */
    readonly answerAfterSeconds: readonly [number, number];
    /** The least and the most seconds a bid waits after the word before it, in a run that has the time. */
    readonly bidAfterSeconds: readonly [number, number];
    /** The longest the table takes to tell a run and move on, however many words it has; no key waits longer on it. */
    readonly runSeconds: number;
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
 * How long after the word before it a word of a run is told while the run has the time: the pause its set draws for it
 * from the game's seed, which every seat draws alike.
 */
export function toldAfterSeconds(set: BidSet, seed: string, word: ToldWord): number {
    const [least, most] = word.action === "bid" ? set.bidAfterSeconds : set.answerAfterSeconds;
    return fork(seed, `bid/${String(word.step)}/pause`).between(least, most);
}

const sum = (seconds: readonly number[]): number => seconds.reduce((all, each) => all + each, 0);

/** The pace of a run, in seconds from its first word. */
export interface RunPace {
    /** When each word is told. */
    readonly told: readonly number[];
    /** When the last word has stood and the table moves on. */
    readonly over: number;
}

/**
 * The pace the table tells a run at: each word after the pause drawn for it, and the last word stands for its own pause
 * once more before the table moves on. A run whose pauses outlast the set's `runSeconds` keeps their shares of that
 * time, so a long run riffles through and a short one keeps the pauses as drawn. The pace reads the seed and the words
 * alone, never a voice or a device, so it is the same on every seat.
 */
export function runPace(set: BidSet, seed: string, words: readonly ToldWord[]): RunPace {
    const pauses = words.slice(1).map((word) => toldAfterSeconds(set, seed, word));
    const drawn = sum(pauses) + toldAfterSeconds(set, seed, words.at(-1) as ToldWord);
    const over = Math.min(drawn, set.runSeconds);
    const share = over / drawn;
    return { told: words.map((_, word) => sum(pauses.slice(0, word)) * share), over };
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
