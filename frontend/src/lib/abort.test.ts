import { describe, expect, it } from "vitest";
import { abortView } from "#lib/abort.ts";
import { words } from "#lib/words.ts";
import type { Chair, Table } from "../routes/(start)/tables.ts";

const WATCHER = 0;

// Seats 1 to 3 hold players 1 to 3; the `open` seat is free.
function chairs(mine: number, open: number | null): Chair[] {
    return [1, 2, 3].map((seat) => ({
        seat,
        occupant_name: seat === open ? null : `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === mine,
        is_away: false,
        ready: false,
        total: null,
        hand: seat === open ? null : { position: "forehand", card_count: 9 },
        former_holder_name: null,
        is_mine_to_return: false,
    }));
}

// A running hand seen by the chair `mine` (0 is a watcher's), with the chair `open` free and the seats `yes` voted.
function tableWith(mine: number, open: number | null, yes: number[] | null): Table {
    return {
        id: "a".repeat(32),
        version: 7,
        chairs: chairs(mine, open),
        watchers: 0,
        result: null,
        passed_in: null,
        series: null,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
        hand: {
            dealer_seat: 3,
            own_cards: [],
            skat_count: 2,
            waiting_seat: open,
            abort: yes,
            abortable: open !== null,
            ramsch: false,
            pushing: null,
            pushes: 0,
            push_factor: 1,
            auction: {
                turn_seat: null,
                facing_seat: null,
                awaiting: null,
                standing: null,
                values: [],
                words: [],
                declared: null,
            },
            declaring: null,
            playing: null,
        },
    };
}

describe("the vote to abort a hand with an open chair", () => {
    it.each([1, 3])("offers the first yes to the seated chair %i while no vote stands", (viewer) => {
        expect(abortView(tableWith(viewer, 2, null))).toEqual({ offered: true, ask: null, marks: new Map() });
    });

    it.each([
        { name: "a watcher", table: tableWith(WATCHER, 2, null) },
        { name: "a table with no open chair", table: tableWith(1, null, null) },
        { name: "a table between hands", table: { ...tableWith(1, 2, null), hand: null } },
    ])("offers nothing to $name", ({ table }) => {
        expect(abortView(table)).toEqual({ offered: false, ask: null, marks: new Map() });
    });

    it("asks the other seated chair with the proposer's face and the two answers", () => {
        const view = abortView(tableWith(3, 2, [1]));

        expect(view).toEqual({
            offered: false,
            ask: {
                text: words["table.wantsToAbort"]({ name: "player 1" }),
                faces: [{ seat: 1, name: "player 1", initial: "p" }],
                waits: false,
                buttons: [
                    { answer: "agree", word: words["table.abort"], icon: "check", primary: true },
                    { answer: "refuse", word: words["table.abortWait"], icon: "cross", primary: false },
                ],
            },
            marks: new Map(),
        });
    });

    it("tells the proposer whom it waits for, takes the key and the answers away and marks that chair", () => {
        const view = abortView(tableWith(1, 2, [1]));

        expect(view).toEqual({
            offered: false,
            ask: {
                text: words["table.waitingFor"]({ names: "player 3" }),
                faces: [{ seat: 3, name: "player 3", initial: "p" }],
                waits: true,
                buttons: [],
            },
            marks: new Map([[3, "unanswered"]]),
        });
    });

    it("shows a watcher the proposal with no answers and no marks", () => {
        const view = abortView(tableWith(WATCHER, 2, [1]));

        expect(view.ask?.text).toBe(words["table.wantsToAbort"]({ name: "player 1" }));
        expect(view.ask?.buttons).toEqual([]);
        expect(view.marks).toEqual(new Map());
    });
});
