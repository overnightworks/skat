import { closeHand } from "#lib/closingTrick.ts";
import { closedHandOrdinal, cuesBetween, playedOutResultOrdinal, type Cue } from "#lib/cues.ts";
import { earlyDecidingTrick, type SheetTrick } from "#lib/gameSheet.ts";
import type { GameSheet, Table } from "../routes/(start)/tables.ts";

// A game sheet that is slower than this does not hold the result back.
const SHEET_WAIT_MILLISECONDS = 1500;

/** The last trick of a hand whose result waits for it: whether its declarer won, none in a Ramsch, and what shows the result. */
export type Closing = { declarerWon: boolean | null; whenResultShown: () => void };

export type Presenter = (previous: Table | undefined, table: Table, cues: readonly Cue[], closing?: Closing) => void;

/** The trick that decided the game of the result `ordinal` before its tenth, and whether its declarer won. */
export type DecidingTrick = { ordinal: number; trick: SheetTrick; declarerWon: boolean | null };

/**
 * The rim of the card that took a hand's deciding trick: gold when the declarer won, red when he lost. A Ramsch has no
 * declarer, and the card keeps the brass of the pile's last trick.
 */
export function outcomeRim(declarerWon: boolean | null): "won" | "lost" | null {
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
 * tables that arrive meanwhile wait behind it. A stage that stands still shows the result at once, and a game decided
 * before its tenth trick then shows that trick once the sheet has come; so does a result the page shows from its first
 * table, after a load or a dropped connection, as no closing played before it.
 */
export function tableShowing(
    present: Presenter,
    readSheet: (ordinal: number) => Promise<GameSheet | null>,
    stageMoves: () => boolean,
    showStillTrick: StillTrick,
): TableShowing {
    let shown: Table | undefined;
    let closing: Held | null = null;
    // Counts the ends of the page, so a sheet read before one shows nothing after it.
    let ends = 0;

    function showAfter(previous: Table | undefined, table: Table): void {
        if (closing !== null && previous !== undefined) {
            closing.queued.push([previous, table]);
            return;
        }
        closing = null;
        if (previous === undefined) {
            present(previous, table, cuesBetween(previous, table));
            showResultStill(table);
            return;
        }
        const ordinal = closedHandOrdinal(previous, table);
        if (ordinal === null) present(previous, table, cuesBetween(previous, table));
        else if (stageMoves()) closeAtItsLastTrick(previous, table, ordinal);
        else {
            present(previous, table, cuesBetween(previous, table));
            showResultStill(table);
        }
    }

    // The result of a played-out hand that shows at once, with no closing on the stage before it.
    function showResultStill(table: Table): void {
        const ordinal = playedOutResultOrdinal(table);
        if (ordinal === null) return;
        const readAt = ends;
        void readSheet(ordinal).then((sheet) => {
            showEarlyTrick(readAt, table, ordinal, sheet);
        });
    }

    function showEarlyTrick(readAt: number, table: Table, ordinal: number, sheet: GameSheet | null): void {
        const trick = earlyDecidingTrick(sheet);
        if (trick !== null && readAt === ends) showStillTrick({ ordinal, trick, declarerWon: declarerWonOf(table) });
    }

    function showQueued(queued: readonly [Table, Table][]): void {
        for (const [previous, table] of queued) showAfter(previous, table);
    }

    function closeAtItsLastTrick(previous: Table, table: Table, ordinal: number): void {
        const hold: Held = { queued: [] };
        closing = hold;
        let slowTimer: ReturnType<typeof setTimeout> | undefined;
        const slow = new Promise<null>((resolve) => {
            slowTimer = setTimeout(resolve, SHEET_WAIT_MILLISECONDS, null);
        });
        void Promise.race([readSheet(ordinal), slow]).then((sheet) => {
            clearTimeout(slowTimer);
            if (closing !== hold) return;
            const cues = cuesBetween(previous, table);
            const held = stageMoves() ? closeHand(previous, table, sheet) : null;
            const trickCues = held === null ? [] : cuesBetween(previous, held);
            if (held === null || !trickCues.some((cue) => cue.kind === "trick-taken")) {
                closing = null;
                present(previous, table, cues);
                if (!stageMoves()) showEarlyTrick(ends, table, ordinal, sheet);
                showQueued(hold.queued);
                return;
            }
            const isResult = (cue: Cue): boolean => cue.kind === "result-appeared";
            present(previous, held, [...trickCues, ...cues.filter((cue) => !isResult(cue))], {
                declarerWon: declarerWonOf(table),
                whenResultShown: () => {
                    if (closing !== hold) return;
                    closing = null;
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
            closing = null;
            ends += 1;
        },
    };
}
