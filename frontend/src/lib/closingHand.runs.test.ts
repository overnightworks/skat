import { beforeEach, describe, expect, it } from "vitest";
import type { BidRun } from "#lib/bidRun.ts";
import { tableShowing } from "#lib/closingHand.ts";
import type { Cue } from "#lib/cues.ts";
import { declaringAt, EVERY_HAND_DEALT, FOREHAND, MIDDLEHAND, table } from "#lib/cues.fixtures.ts";
import type { AuctionWord, Hand, Table } from "../routes/(start)/tables.ts";

type Presented = { previous: Table | undefined; table: Table; cues: readonly Cue[] };

const BID_EIGHTEEN: AuctionWord = { seat: MIDDLEHAND, action: "bid", value: 18 };
const HOLD_EIGHTEEN: AuctionWord = { seat: FOREHAND, action: "hold", value: 18 };
const BID_TWENTY: AuctionWord = { seat: MIDDLEHAND, action: "bid", value: 20 };
const PASS: AuctionWord = { seat: FOREHAND, action: "pass", value: null };
const RUN = [BID_EIGHTEEN, HOLD_EIGHTEEN, BID_TWENTY];
// How long the stand-in voice speaks each word it is given.
const SPOKEN_SECONDS = 0.5;

const auctionTable = (version: number, said: AuctionWord[]): Table =>
    table(version, EVERY_HAND_DEALT, { declaring: null, spoken: said });
const dealt = auctionTable(4, []);
const afterTheRun = auctionTable(5, RUN);
// The update that brings the run's last word also ends the auction.
const wonByTheRun: Table = {
    ...afterTheRun,
    hand: { ...(afterTheRun.hand as Hand), declaring: declaringAt("choosing") },
};
const afterwards = auctionTable(6, [...RUN, PASS]);

let stageIsMoving = true;

// The stand-in stage keeps the run it was given and tells a word when the test asks for it.
function showing() {
    const presented: Presented[] = [];
    const runs: { run: BidRun; tell: (word: number) => number }[] = [];
    const shown = tableShowing(
        (previous, table, cues) => {
            presented.push({ previous, table, cues });
            return SPOKEN_SECONDS;
        },
        () => Promise.resolve(null),
        () => stageIsMoving,
        () => undefined,
        (run, tell) => runs.push({ run, tell }),
    );
    const tell = (word: number, run = 0): number => (runs[run] as (typeof runs)[number]).tell(word);
    return { shown, presented, runs, tell };
}

const wordsOf = (presentation: Presented | undefined): string[] =>
    (presentation?.cues ?? []).flatMap((cue) =>
        cue.kind === "bid-said" ? [`${String(cue.seat)} ${cue.word.action} ${String(cue.word.value)}`] : [cue.kind],
    );
const stepsOf = (presentation: Presented | undefined): AuctionWord[] | undefined =>
    presentation?.table.hand?.auction.steps;

beforeEach(() => {
    stageIsMoving = true;
});

describe("an update that brings several words of an auction", () => {
    it("hands its run to the stage and shows nothing before the stage tells a word", () => {
        const { shown, presented, runs } = showing();
        shown.begin(dealt);

        shown.show(afterTheRun);

        expect(runs.map(({ run }) => run.words.length)).toEqual([RUN.length]);
        expect(presented).toEqual([]);
    });

    it("shows each word the stage tells on the table as it stood after it, with that word's cue alone", () => {
        const { shown, presented, tell } = showing();
        shown.begin(dealt);
        shown.show(afterTheRun);

        tell(0);
        tell(1);

        expect(presented.map(stepsOf)).toEqual([RUN.slice(0, 1), RUN.slice(0, 2)]);
        expect(presented.map(wordsOf)).toEqual([["2 bid 18"], ["1 hold 18"]]);
        expect(presented.map(({ previous }) => previous)).toEqual([dealt, presented[0]?.table]);
    });

    it("says to the stage how long the voice speaks the word it told", () => {
        const { shown, tell } = showing();
        shown.begin(dealt);
        shown.show(afterTheRun);

        expect([tell(0), tell(1), tell(2)]).toEqual([SPOKEN_SECONDS, SPOKEN_SECONDS, SPOKEN_SECONDS]);
    });

    it("brings the table of the update with its last word, and every other cue of the update with it", () => {
        const { shown, presented, tell } = showing();
        shown.begin(dealt);
        shown.show(wonByTheRun);

        tell(0);
        tell(1);
        tell(2);

        expect(presented[2]?.table).toBe(wonByTheRun);
        expect(presented[2]?.previous).toBe(presented[1]?.table);
        expect(wordsOf(presented[2])).toEqual(["auction-ended", "2 bid 20"]);
    });

    it("brings the table of the update against the last table shown when the stage skips to the last word", () => {
        const { shown, presented, tell } = showing();
        shown.begin(dealt);
        shown.show(afterTheRun);

        tell(0);
        tell(2);

        expect(presented[1]?.table).toBe(afterTheRun);
        expect(presented[1]?.previous).toBe(presented[0]?.table);
        expect(wordsOf(presented[1])).toEqual(["2 bid 20"]);
    });

    it("holds the tables that arrive meanwhile behind its last word", () => {
        const { shown, presented, tell } = showing();
        shown.begin(dealt);
        shown.show(afterTheRun);
        tell(0);

        shown.show(afterwards);

        expect(presented).toHaveLength(1);

        tell(2);

        expect(presented.map(({ table: each }) => each).slice(1)).toEqual([afterTheRun, afterwards]);
        expect(presented[2]?.previous).toBe(afterTheRun);
        expect(wordsOf(presented[2])).toEqual(["1 pass null"]);
    });

    it("tells a run that waited behind another one once that one's last word is told", () => {
        const { shown, runs, tell } = showing();
        const secondRun = auctionTable(6, [...RUN, HOLD_EIGHTEEN, PASS]);
        shown.begin(dealt);
        shown.show(afterTheRun);
        shown.show(secondRun);

        expect(runs).toHaveLength(1);

        tell(2);

        expect(runs.map(({ run }) => run.words.map((word) => word.step))).toEqual([
            [0, 1, 2],
            [3, 4],
        ]);
    });

    it("shows the table at once, with every word, while the stage stands still", () => {
        stageIsMoving = false;
        const { shown, presented, runs } = showing();
        shown.begin(dealt);

        shown.show(afterTheRun);

        expect(runs).toEqual([]);
        expect(presented.map(({ table: each }) => each)).toEqual([afterTheRun]);
        expect(wordsOf(presented[0])).toEqual(["2 bid 18", "1 hold 18", "2 bid 20"]);
    });

    it("shows a single word at once", () => {
        const { shown, presented, runs } = showing();
        shown.begin(dealt);

        shown.show(auctionTable(5, [BID_EIGHTEEN]));

        expect(runs).toEqual([]);
        expect(wordsOf(presented[0])).toEqual(["2 bid 18"]);
    });

    it.each([
        {
            name: "the page has ended",
            drop: (shown: ReturnType<typeof showing>["shown"]) => {
                shown.end();
            },
        },
        {
            name: "a dropped connection brought the table as it is",
            drop: (shown: ReturnType<typeof showing>["shown"]) => {
                shown.forget();
                shown.show(afterwards);
            },
        },
    ])("tells no word of a run once $name", ({ drop }) => {
        const { shown, presented, tell } = showing();
        shown.begin(dealt);
        shown.show(afterTheRun);
        tell(0);

        drop(shown);
        const shownSince = presented.length;

        expect(tell(1)).toBe(0);
        expect(presented).toHaveLength(shownSince);
    });
});
