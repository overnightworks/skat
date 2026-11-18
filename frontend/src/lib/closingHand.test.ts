import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { tableShowing } from "#lib/closingHand.ts";
import {
    afterTheLastCard,
    beforeTheLastCard,
    sheetOfTheLastTrick,
    sheetOfTrickThree,
} from "#lib/closingTrick.fixtures.ts";
import type { Cue } from "#lib/cues.ts";
import { MIDDLEHAND } from "#lib/cues.fixtures.ts";
import type { SheetTrick } from "#lib/gameSheet.ts";
import type { GameSheet, Table } from "../routes/(start)/tables.ts";

type Presented = { previous: Table | undefined; table: Table; cues: readonly Cue[] };

const SLOW_SHEET_MILLISECONDS = 1500;
const nextHand: Table = { ...beforeTheLastCard, version: 20 };
const afterwards: Table = { ...afterTheLastCard, version: 21 };
const lastTrickSheet = sheetOfTheLastTrick(MIDDLEHAND);

let stageIsMoving = true;

function showing(readSheet: (ordinal: number) => Promise<GameSheet | null>) {
    const presented: Presented[] = [];
    const resultShown: (() => void)[] = [];
    const declarerWon: (boolean | null)[] = [];
    const stillTricks: { ordinal: number; trick: SheetTrick }[] = [];
    const shown = tableShowing(
        (previous, table, cues, closing) => {
            presented.push({ previous, table, cues });
            if (closing === undefined) return;
            resultShown.push(closing.whenResultShown);
            declarerWon.push(closing.declarerWon);
        },
        readSheet,
        () => stageIsMoving,
        (ordinal, trick) => stillTricks.push({ ordinal, trick }),
    );
    return { shown, presented, resultShown, declarerWon, stillTricks };
}

const kinds = (presentation: Presented | undefined): string[] => presentation?.cues.map((cue) => cue.kind) ?? [];

beforeEach(() => {
    vi.useFakeTimers();
    stageIsMoving = true;
});

afterEach(() => {
    vi.useRealTimers();
});

describe("the tables the stream brings", () => {
    it("shows the first table as it is, and each next one against the one before", () => {
        const { shown, presented } = showing(() => Promise.resolve(null));

        shown.show(beforeTheLastCard);
        shown.show(nextHand);

        expect(presented.map(({ previous, table }) => [previous, table])).toEqual([
            [undefined, beforeTheLastCard],
            [beforeTheLastCard, nextHand],
        ]);
    });

    it("compares the first streamed table with the one the page was answered with", () => {
        const { shown, presented } = showing(() => Promise.resolve(null));

        shown.begin(beforeTheLastCard);
        shown.show(nextHand);

        expect(presented[0]?.previous).toBe(beforeTheLastCard);
    });

    it("shows the first table after a dropped connection as it is", () => {
        const { shown, presented } = showing(() => Promise.resolve(null));

        shown.begin(beforeTheLastCard);
        shown.forget();
        shown.show(nextHand);

        expect(presented[0]?.previous).toBeUndefined();
    });
});

describe("the table that follows the last card", () => {
    it("draws the last trick from the sheet and shows the result once the stage has settled", async () => {
        const readSheet = vi.fn(() => Promise.resolve<GameSheet | null>(lastTrickSheet));
        const { shown, presented, resultShown } = showing(readSheet);
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        await vi.advanceTimersByTimeAsync(0);

        expect(readSheet).toHaveBeenCalledWith(afterwards.result?.ordinal);
        expect(presented).toHaveLength(1);
        expect(kinds(presented[0])).toContain("trick-taken");
        expect(kinds(presented[0])).not.toContain("result-appeared");

        resultShown[0]?.();

        expect(presented).toHaveLength(2);
        expect(presented[1]?.table).toBe(afterwards);
        expect(kinds(presented[1])).toEqual(["result-appeared"]);
    });

    it("holds the tables that arrive meanwhile until the result is shown", async () => {
        const { shown, presented, resultShown } = showing(() => Promise.resolve(lastTrickSheet));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        shown.show(nextHand);
        await vi.advanceTimersByTimeAsync(0);

        expect(presented).toHaveLength(1);

        resultShown[0]?.();

        expect(presented.map(({ table }) => table)).toEqual([presented[0]?.table, afterwards, nextHand]);
    });

    it("shows the result at once when the sheet has no last trick, and then the tables held", async () => {
        const { shown, presented } = showing(() => Promise.resolve(null));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        shown.show(nextHand);
        await vi.advanceTimersByTimeAsync(0);

        expect(presented.map(({ table }) => table)).toEqual([afterwards, nextHand]);
        expect(kinds(presented[0])).toContain("result-appeared");
    });

    it("shows the result at once when the last trick it draws brings no trick taken", async () => {
        const { shown, presented } = showing(() => Promise.resolve(lastTrickSheet));
        const alreadyTaken = {
            ...beforeTheLastCard,
            hand: {
                ...beforeTheLastCard.hand,
                playing: {
                    ...beforeTheLastCard.hand?.playing,
                    current_trick: [],
                    last_trick: {
                        cards: lastTrickSheet.cards?.tricks.at(-1)?.cards.map(({ card }) => card),
                        leader_seat: 1,
                        taker_seat: MIDDLEHAND,
                    },
                },
            },
        } as Table;
        shown.begin(alreadyTaken);

        shown.show(afterwards);
        await vi.advanceTimersByTimeAsync(0);

        expect(presented.map(({ table }) => table)).toEqual([afterwards]);
    });

    it("does not wait for a sheet that is slower than the sheet wait", async () => {
        const { shown, presented } = showing(() => new Promise<GameSheet | null>(() => undefined));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        await vi.advanceTimersByTimeAsync(SLOW_SHEET_MILLISECONDS - 1);
        expect(presented).toHaveLength(0);
        await vi.advanceTimersByTimeAsync(1);

        expect(presented.map(({ table }) => table)).toEqual([afterwards]);
    });

    it("tells whether the declarer won the hand whose last trick it holds", async () => {
        const { shown, declarerWon } = showing(() => Promise.resolve(lastTrickSheet));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        await vi.advanceTimersByTimeAsync(0);

        expect(afterwards.result?.kind).toBe("declared");
        expect(declarerWon).toEqual([afterwards.result?.kind === "declared" && afterwards.result.won]);
    });

    it("shows the result at once when the stage does not move, and a trick played to the last on no row", async () => {
        stageIsMoving = false;
        const { shown, presented, stillTricks } = showing(() => Promise.resolve(lastTrickSheet));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        expect(presented.map(({ table }) => table)).toEqual([afterwards]);
        await vi.advanceTimersByTimeAsync(0);

        expect(stillTricks).toEqual([]);
    });

    it("shows the trick that decided the game before its tenth once the sheet has come, when the stage does not move", async () => {
        stageIsMoving = false;
        const { shown, presented, stillTricks } = showing(() => Promise.resolve(sheetOfTrickThree));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        await vi.advanceTimersByTimeAsync(0);

        expect(presented.map(({ table }) => table)).toEqual([afterwards]);
        expect(stillTricks.map(({ ordinal, trick }) => [ordinal, trick.taker?.seat])).toEqual([
            [afterwards.result?.ordinal, sheetOfTrickThree.cards?.tricks.at(-1)?.taker_seat],
        ]);
    });

    it("shows no still trick once the page has ended while the sheet was read", async () => {
        stageIsMoving = false;
        const { shown, stillTricks } = showing(() => Promise.resolve(sheetOfTrickThree));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        shown.end();
        await vi.advanceTimersByTimeAsync(0);

        expect(stillTricks).toEqual([]);
    });

    it("shows the result at once when the stage stopped moving while the sheet was read", async () => {
        const { shown, presented } = showing(() => Promise.resolve(lastTrickSheet));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        stageIsMoving = false;
        await vi.advanceTimersByTimeAsync(0);

        expect(presented.map(({ table }) => table)).toEqual([afterwards]);
    });

    it("shows nothing of the closing hand once the page has ended", async () => {
        const { shown, presented, resultShown } = showing(() => Promise.resolve(lastTrickSheet));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        shown.end();
        await vi.advanceTimersByTimeAsync(0);

        expect(presented).toEqual([]);
        expect(resultShown).toEqual([]);
    });

    it("shows no result once the page has ended while the last trick rests", async () => {
        const { shown, presented, resultShown } = showing(() => Promise.resolve(lastTrickSheet));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        await vi.advanceTimersByTimeAsync(0);
        shown.end();
        resultShown[0]?.();

        expect(presented).toHaveLength(1);
    });

    it("shows a table after a dropped connection at once, whatever the closing hand held", async () => {
        const { shown, presented } = showing(() => Promise.resolve(lastTrickSheet));
        shown.begin(beforeTheLastCard);

        shown.show(afterwards);
        shown.forget();
        shown.show(nextHand);
        await vi.advanceTimersByTimeAsync(0);

        expect(presented.map(({ table }) => table)).toEqual([nextHand]);
    });
});
