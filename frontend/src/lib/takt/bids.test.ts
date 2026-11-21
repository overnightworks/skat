import { describe, expect, it } from "vitest";
import { MOTION_SETS } from "#lib/motionSets.ts";
import { duelTimeline, rollTimeline, toldAfterSeconds, type BidSet, type ToldWord } from "#lib/takt/bids.ts";
import { sampled } from "#lib/takt/timeline.ts";

const SEED = "table/1/8";
const NEXT_GAME = "table/1/9";
const SETS = Object.values(MOTION_SETS).map((set) => ({ id: set.id, bids: set.bids }));
const SWINGING = MOTION_SETS.verspielt.bids;
const STRAIGHT = MOTION_SETS.dezent.bids;
const BID: ToldWord = { step: 2, action: "bid" };
const UNHEARD = 0;
const DRUM_HEIGHT = 60;
const ONES = { height: DRUM_HEIGHT, place: 0 };
const TENS = { height: DRUM_HEIGHT, place: 1 };
const FRAME_SECONDS = 1 / 60;

const dropsOf = (set: BidSet, drum: typeof ONES): number[] => {
    const { tracks, seconds } = rollTimeline(set, drum);
    return sampled(tracks.reel, seconds, FRAME_SECONDS).map((pose) => pose.y);
};

describe.each(SETS)("the pause before a word of a run in $id", ({ bids }) => {
    it.each([
        { action: "bid", range: bids.bidAfterSeconds },
        { action: "hold", range: bids.answerAfterSeconds },
        { action: "pass", range: bids.answerAfterSeconds },
    ] as const)("of a $action lies within the range the set gives it", ({ action, range: [least, most] }) => {
        for (let step = 0; step < 40; step += 1) {
            const pause = toldAfterSeconds(bids, SEED, { step, action }, UNHEARD);

            expect(pause).toBeGreaterThanOrEqual(least);
            expect(pause).toBeLessThanOrEqual(most);
        }
    });

    it("is the same wherever it is asked for, so every seat tells the word at the same instant", () => {
        expect(toldAfterSeconds(bids, SEED, { ...BID }, UNHEARD)).toBe(toldAfterSeconds(bids, SEED, BID, UNHEARD));
    });

    it("is each word's own, and another one in the next game", () => {
        const pauses = [
            toldAfterSeconds(bids, SEED, BID, UNHEARD),
            toldAfterSeconds(bids, SEED, { ...BID, step: BID.step + 2 }, UNHEARD),
            toldAfterSeconds(bids, NEXT_GAME, BID, UNHEARD),
        ];

        expect(new Set(pauses).size).toBe(pauses.length);
    });

    it("lasts until a longer word before it has been spoken, and a breath more", () => {
        const spokenSeconds = bids.bidAfterSeconds[1] + 1;

        expect(toldAfterSeconds(bids, SEED, BID, spokenSeconds)).toBe(spokenSeconds + bids.breathSeconds);
    });
});

describe.each(SETS)("the roll of a drum in $id", ({ bids }) => {
    it("brings the digit up from one drum height below to where the stylesheet rests it", () => {
        const drops = dropsOf(bids, ONES);

        expect(drops[0]).toBe(DRUM_HEIGHT);
        expect(drops.at(-1)).toBeCloseTo(0);
    });

    it("lasts as long as the set rolls a drum, each drum to the left starting later by the set's stagger", () => {
        expect(rollTimeline(bids, ONES).seconds).toBe(bids.rollSeconds);
        expect(rollTimeline(bids, TENS).seconds).toBe(bids.rollSeconds + bids.staggerSeconds);
    });

    it("moves the digit straight up and down, at its size and fully seen", () => {
        const { tracks, seconds } = rollTimeline(bids, TENS);

        for (const pose of sampled(tracks.reel, seconds, FRAME_SECONDS))
            expect(pose).toMatchObject({ x: 0, turn: 0, wide: 1, tall: 1, opacity: 1 });
    });
});

describe("the two ways a drum arrives", () => {
    it("swings past its digit in the set that swings", () => {
        expect(Math.min(...dropsOf(SWINGING, ONES))).toBeLessThan(0);
    });

    it("never passes its digit in the set that rolls straight in", () => {
        expect(Math.min(...dropsOf(STRAIGHT, ONES))).toBeGreaterThanOrEqual(0);
    });

    it("holds the tens still while the ones already roll, in the set that staggers", () => {
        const midStagger = SWINGING.staggerSeconds / 2;

        expect(rollTimeline(SWINGING, TENS).tracks.reel(midStagger).y).toBe(DRUM_HEIGHT);
        expect(rollTimeline(SWINGING, ONES).tracks.reel(midStagger).y).toBeLessThan(DRUM_HEIGHT);
    });
});

describe.each(SETS)("a new pair on the duel line in $id", ({ bids }) => {
    it("appears from nothing within the time the set gives it", () => {
        const { tracks, seconds } = duelTimeline(bids);

        expect(seconds).toBe(bids.duelAppearsSeconds);
        expect(tracks.line(0)).toBe(0);
        expect(tracks.line(seconds)).toBe(1);
    });
});
