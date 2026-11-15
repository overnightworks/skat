import { closeHand } from "#lib/closingTrick.ts";
import { closedHandOrdinal, cuesBetween, type Cue } from "#lib/cues.ts";
import { stageMoves } from "#lib/stage.svelte.ts";
import type { GameSheet, Table } from "../routes/(start)/tables.ts";

// A game sheet that is slower than this does not hold the result back.
const SHEET_WAIT_MILLISECONDS = 1500;

export type Presenter = (
    previous: Table | undefined,
    table: Table,
    cues: readonly Cue[],
    whenResultShown?: () => void,
) => void;

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
 * tables that arrive meanwhile wait behind it.
 */
export function tableShowing(
    present: Presenter,
    readSheet: (ordinal: number) => Promise<GameSheet | null>,
): TableShowing {
    let shown: Table | undefined;
    let closing: Held | null = null;

    function showAfter(previous: Table | undefined, table: Table): void {
        if (closing !== null && previous !== undefined) {
            closing.queued.push([previous, table]);
            return;
        }
        closing = null;
        const ordinal = previous === undefined ? null : closedHandOrdinal(previous, table);
        if (previous !== undefined && ordinal !== null && stageMoves()) closeAtItsLastTrick(previous, table, ordinal);
        else present(previous, table, cuesBetween(previous, table));
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
                showQueued(hold.queued);
                return;
            }
            const isResult = (cue: Cue): boolean => cue.kind === "result-appeared";
            present(previous, held, [...trickCues, ...cues.filter((cue) => !isResult(cue))], () => {
                if (closing !== hold) return;
                closing = null;
                present(held, table, cues.filter(isResult));
                showQueued(hold.queued);
            });
        });
    }

    return {
        begin: (table) => {
            shown = table;
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
        },
    };
}
