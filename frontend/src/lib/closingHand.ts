import { bidRunBetween, type BidRun } from "#lib/bidRun.ts";
import { closeHand } from "#lib/closingTrick.ts";
import { closedHandOrdinal, cuesBetween, playedOutResultOrdinal, type Cue } from "#lib/cues.ts";
import { earlyDecidingTrick, type SheetTrick } from "#lib/gameSheet.ts";
import type { GameSheet, Table } from "../routes/(start)/tables.ts";

// A game sheet that is slower than this does not hold the result back.
const SHEET_WAIT_MILLISECONDS = 1500;

/** The last trick of a hand whose result waits for it: whether its declarer won, none in a Ramsch, and what shows the result. */
export type Closing = { declarerWon: boolean | null; whenResultShown: () => void };

/** Shows a table with the cues that brought it, and says how many seconds the voice takes to say their words. */
export type Presenter = (previous: Table | undefined, table: Table, cues: readonly Cue[], closing?: Closing) => number;

/** Paces a run: `tell` shows the word of a number and says how long the voice speaks it; the last word ends the run. */
export type RunTeller = (run: BidRun, tell: (word: number) => number) => void;

/** The trick that decided the game of the result `ordinal` before its tenth, and whether its declarer won. */
export type DecidingTrick = { ordinal: number; trick: SheetTrick; declarerWon: boolean | null };

/** The seal on the card that took a hand's deciding trick: how the declarer's game ended. */
export type Seal = "won" | "lost";

/** The seal of a hand's deciding trick; a Ramsch has no declarer, and its last trick carries none. */
export function outcomeSeal(declarerWon: boolean | null): Seal | null {
    if (declarerWon === null) return null;
    return declarerWon ? "won" : "lost";
}

/** Shows the deciding trick on a page whose stage stood still. */
export type StillTrick = (deciding: DecidingTrick) => void;

// Whether the declarer won the result the table shows; a Ramsch has none.
function declarerWonOf(table: Table): boolean | null {
    return table.result?.kind === "declared" ? table.result.won : null;
}

export type TableShowing = {
    /** Takes the table the page was answered with as the one shown, so the first streamed table is compared with it. */
    begin: (table: Table) => void;
    show: (table: Table) => void;
    /** A dropped connection forgets the table shown: the first table after it stands still. */
    forget: () => void;
    end: () => void;
};

type Held = { queued: [Table, Table][] };

/**
 * Shows each table the stream brings. The table that follows the last card has no hand, so the last trick is drawn from
 * the game's sheet, rests and sweeps as any trick, and the result of the game appears when the stage has settled; the
 * tables that arrive meanwhile wait behind it. A stage that stands still shows the result at once, and so does a closing
 * whose sheet is slow or draws no trick taken; a game decided before its tenth trick then shows that trick once the
 * sheet has come. So does a result the page shows from its first table, after a load or a dropped connection, as no
 * closing played before it. An update that brings several words of an auction tells them one after another while the
 * stage moves, each on the table as it stood then, and the tables that arrive meanwhile wait behind its last word.
 */
export function tableShowing(
    present: Presenter,
    readSheet: (ordinal: number) => Promise<GameSheet | null>,
    stageMoves: () => boolean,
    showStillTrick: StillTrick,
    tellRun: RunTeller,
): TableShowing {
    let shown: Table | undefined;
    let holding: Held | null = null;
    // Counts the ends of the page, so a sheet read before one shows nothing after it.
    let ends = 0;

    function showAfter(previous: Table | undefined, table: Table): void {
        if (holding !== null && previous !== undefined) {
            holding.queued.push([previous, table]);
            return;
        }
        holding = null;
        if (previous === undefined) {
            present(previous, table, cuesBetween(previous, table));
            showResultStill(table);
            return;
        }
        const ordinal = closedHandOrdinal(previous, table);
        if (ordinal === null) showAtItsPace(previous, table);
        else if (stageMoves()) closeAtItsLastTrick(previous, table, ordinal);
        else {
            present(previous, table, cuesBetween(previous, table));
            showResultStill(table);
        }
    }

    // The result of a played-out hand that shows at once, with no closing on the stage before it.
    function showResultStill(table: Table): void {
        const ordinal = playedOutResultOrdinal(table);
        if (ordinal !== null) showEarlyTrickOnceRead(readSheet(ordinal), table, ordinal);
    }

    // A result shown with no closing before it carries the trick that decided its game early, once the sheet has come.
    function showEarlyTrickOnceRead(reading: Promise<GameSheet | null>, table: Table, ordinal: number): void {
        const readAt = ends;
        void reading.then((sheet) => {
            const trick = earlyDecidingTrick(sheet);
            if (trick !== null && readAt === ends)
                showStillTrick({ ordinal, trick, declarerWon: declarerWonOf(table) });
        });
    }

    function showQueued(queued: readonly [Table, Table][]): void {
        for (const [previous, table] of queued) showAfter(previous, table);
    }

    // The words of a run are told one by one, each on the table as it stood after it; the last word brings the table
    // the update brought, with every other cue of the update.
    function showAtItsPace(previous: Table, table: Table): void {
        const cues = cuesBetween(previous, table);
        const said = cues.filter((cue) => cue.kind === "bid-said");
        const run = stageMoves() ? bidRunBetween(previous, table, said) : null;
        if (run === null) {
            present(previous, table, cues);
            return;
        }
        const hold: Held = { queued: [] };
        holding = hold;
        const last = said.length - 1;
        let told = previous;
        tellRun(run, (word) => {
            if (holding !== hold) return 0;
            const before = told;
            if (word < last) {
                told = run.tables[word] as Table;
                return present(before, told, [said[word] as Cue]);
            }
            holding = null;
            const spoken = present(
                before,
                table,
                cues.filter((cue) => cue.kind !== "bid-said" || cue === said[last]),
            );
            showQueued(hold.queued);
            return spoken;
        });
    }

    function closeAtItsLastTrick(previous: Table, table: Table, ordinal: number): void {
        const hold: Held = { queued: [] };
        holding = hold;
        let slowTimer: ReturnType<typeof setTimeout> | undefined;
        const slow = new Promise<null>((resolve) => {
            slowTimer = setTimeout(resolve, SHEET_WAIT_MILLISECONDS, null);
        });
        const reading = readSheet(ordinal);
        void Promise.race([reading, slow]).then((sheet) => {
            clearTimeout(slowTimer);
            if (holding !== hold) return;
            const cues = cuesBetween(previous, table);
            const held = stageMoves() ? closeHand(previous, table, sheet) : null;
            const trickCues = held === null ? [] : cuesBetween(previous, held);
            if (held === null || !trickCues.some((cue) => cue.kind === "trick-taken")) {
                holding = null;
                present(previous, table, cues);
                showEarlyTrickOnceRead(reading, table, ordinal);
                showQueued(hold.queued);
                return;
            }
            const isResult = (cue: Cue): boolean => cue.kind === "result-appeared";
            present(previous, held, [...trickCues, ...cues.filter((cue) => !isResult(cue))], {
                declarerWon: declarerWonOf(table),
                whenResultShown: () => {
                    if (holding !== hold) return;
                    holding = null;
                    present(held, table, cues.filter(isResult));
                    showQueued(hold.queued);
                },
            });
        });
    }

    return {
        begin: (table) => {
            shown = table;
            showResultStill(table);
        },
        show: (table) => {
            showAfter(shown, table);
            shown = table;
        },
        forget: () => {
            shown = undefined;
        },
        end: () => {
            holding = null;
            ends += 1;
        },
    };
}
