import { beforeEach, describe, expect, it } from "vitest";
import type { BidRun } from "#lib/bidRun.ts";
import { tableShowing, type RunTelling } from "#lib/closingHand.ts";
import type { Cue } from "#lib/cues.ts";
import { declaringAt, EVERY_HAND_DEALT, FOREHAND, MIDDLEHAND, table } from "#lib/cues.fixtures.ts";
import type { AuctionWord, Hand, Table } from "../routes/(start)/tables.ts";

type Presented = { previous: Table | undefined; table: Table; cues: readonly Cue[]; saidWithinSeconds?: number };

const BID_EIGHTEEN: AuctionWord = { seat: MIDDLEHAND, action: "bid", value: 18 };
const HOLD_EIGHTEEN: AuctionWord = { seat: FOREHAND, action: "hold", value: 18 };
const BID_TWENTY: AuctionWord = { seat: MIDDLEHAND, action: "bid", value: 20 };
const PASS: AuctionWord = { seat: FOREHAND, action: "pass", value: null };
const RUN = [BID_EIGHTEEN, HOLD_EIGHTEEN, BID_TWENTY];
// How long the stand-in stage gives the voice for a word another one follows, and for the last word.
const UNTIL_THE_NEXT_WORD = 0.5;
const THE_LAST_WORD = Infinity;

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

// The stand-in stage keeps the run it was given, tells a word when the test asks for it and moves on when it says so.
function showing() {
    const presented: Presented[] = [];
    const runs: { run: BidRun; telling: RunTelling }[] = [];
    const shown = tableShowing(
        (previous, table, cues, _closing, saidWithinSeconds) => {
            presented.push({ previous, table, cues, saidWithinSeconds });
        },
        () => Promise.resolve(null),
        () => stageIsMoving,
        () => undefined,
        (run, telling) => runs.push({ run, telling }),
    );
    const tell = (word: number, saidWithinSeconds = UNTIL_THE_NEXT_WORD): void => {
        runs[0]?.telling.tell(word, saidWithinSeconds);
    };
    const moveOn = (): void => {
        runs[0]?.telling.moveOn();
    };
    return { shown, presented, runs, tell, moveOn };
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

    it("gives the voice of each word the time the stage has for it, and the voice of any other update none", () => {
        const { shown, presented, tell, moveOn } = showing();
        shown.begin(dealt);
        shown.show(afterTheRun);
        shown.show(afterwards);

        tell(0);
        tell(1);
        tell(2, THE_LAST_WORD);
        moveOn();

        expect(presented.map(({ saidWithinSeconds }) => saidWithinSeconds)).toEqual([
            UNTIL_THE_NEXT_WORD,
            UNTIL_THE_NEXT_WORD,
            THE_LAST_WORD,
            undefined,
        ]);
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

    it("shows its last word on its own, and the tables that arrived meanwhile only once the stage moves on", () => {
        const { shown, presented, tell, moveOn } = showing();
        shown.begin(dealt);
        shown.show(afterTheRun);
        tell(0);

        shown.show(afterwards);
        tell(2);

        expect(presented.map(({ table: each }) => each).slice(1)).toEqual([afterTheRun]);

        moveOn();

        expect(presented.map(({ table: each }) => each).slice(1)).toEqual([afterTheRun, afterwards]);
        expect(presented[2]?.previous).toBe(afterTheRun);
        expect(wordsOf(presented[2])).toEqual(["1 pass null"]);
    });

    it("holds a table that arrives while its last word stands, and shows the next one at once after moving on", () => {
        const { shown, presented, tell, moveOn } = showing();
        const later = auctionTable(7, [...RUN, PASS]);
        shown.begin(dealt);
        shown.show(afterTheRun);
        tell(2);

        shown.show(afterwards);

        expect(presented.map(({ table: each }) => each)).toEqual([afterTheRun]);

        moveOn();
        shown.show(later);

        expect(presented.map(({ table: each }) => each)).toEqual([afterTheRun, afterwards, later]);
    });

    it("tells a run that waited behind another one once that one moves on", () => {
        const { shown, runs, tell, moveOn } = showing();
        const secondRun = auctionTable(6, [...RUN, HOLD_EIGHTEEN, PASS]);
        shown.begin(dealt);
        shown.show(afterTheRun);
        shown.show(secondRun);
        tell(2);

        expect(runs).toHaveLength(1);

        moveOn();

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
    ])("tells no word of a run and moves on to nothing once $name", ({ drop }) => {
        const { shown, presented, tell, moveOn } = showing();
        shown.begin(dealt);
        shown.show(afterTheRun);
        tell(0);
        shown.show(auctionTable(6, [...RUN, HOLD_EIGHTEEN]));

        drop(shown);
        const shownSince = presented.length;
        tell(1);
        moveOn();

        expect(presented).toHaveLength(shownSince);
    });
});
