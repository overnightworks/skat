import { describe, expect, it } from "vitest";
import { declaredResult, ramschResultView, resultJustAppeared, weiterBar, type RamschView } from "#lib/result.ts";
import { words } from "#lib/words.ts";
import type { Chair, RamschResult, Table } from "../routes/(start)/tables.ts";

const NOBODY = 0;

function chairs(mine: number, changes: Record<number, Partial<Chair>>): Chair[] {
    return [1, 2, 3].map((seat) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === mine,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
        ...changes[seat],
    }));
}

const RAMSCH_NAMES: Record<number, Partial<Chair>> = {
    1: { occupant_name: "Anna" },
    2: { occupant_name: "Ben" },
    3: { occupant_name: "Felix" },
};

// A Ramsch's end as the server counted it: the seats' eyes and what each adds, the factors on the losers' score.
function ramschResult(
    eyes: [number, number, number],
    scores: [number, number, number],
    changes: Partial<RamschResult>,
) {
    return {
        kind: "ramsch",
        ordinal: 4,
        seats: eyes.map((points, index) => ({ seat: index + 1, points, score: scores[index] as number })),
        durchmarsch_seat: null,
        jungfrau: false,
        bock_factor: 1,
        pushes: 0,
        push_factor: 1,
        divided_by_ten: false,
        ...changes,
    } satisfies RamschResult;
}

function ramschTable(mine: number, result: RamschResult, left: Record<number, Partial<Chair>> = {}): Table {
    return {
        id: "a".repeat(32),
        version: 9,
        chairs: chairs(mine, { ...RAMSCH_NAMES, ...left }),
        watchers: 0,
        hand: null,
        result,
        passed_in: null,
        bock: null,
        ended: null,
    };
}

function drawnRamsch(table: Table): RamschView {
    return ramschResultView(table) as RamschView;
}

// The four blessed scenes of the Ramsch's card, seen from Felix at seat 3.
const LOST_WITH_PUSHES = ramschResult([20, 14, 86], [0, 0, -344], { pushes: 2, push_factor: 4 });
const OTHER_LOSES = ramschResult([14, 86, 20], [0, -86, 0], {});
const JUNGFRAU = ramschResult([0, 86, 34], [0, -172, 0], { jungfrau: true });
const DURCHMARSCH = ramschResult([120, 0, 0], [120, 0, 0], { durchmarsch_seat: 1 });

describe("a Ramsch result's card in a Bock game", () => {
    it.each([2, 4])("holds the factor ×%i after the pushes and the Jungfrau", (factor) => {
        const result = ramschResult([20, 14, 86], [0, 0, -86 * 4 * factor], {
            pushes: 2,
            push_factor: 4,
            bock_factor: factor,
        });

        expect(drawnRamsch(ramschTable(3, result)).chips).toEqual([
            "2× geschoben ×4",
            words["bock.factor"]({ factor: String(factor) }),
        ]);
    });

    it("holds the factor last, behind the division by ten and the Jungfrau", () => {
        const result = ramschResult([20, 14, 86], [0, 0, -64], {
            divided_by_ten: true,
            jungfrau: true,
            bock_factor: 2,
        });

        expect(drawnRamsch(ramschTable(3, result)).chips).toEqual(["÷ 10", "Jungfrau ×2", "Bock ×2"]);
    });

    it("holds no chip for a Ramsch outside Bock", () => {
        expect(drawnRamsch(ramschTable(3, OTHER_LOSES)).chips).toEqual([]);
    });
});

describe("a Ramsch result's card", () => {
    it.each([
        {
            scene: "ramsch-lost",
            result: LOST_WITH_PUSHES,
            word: "Verloren",
            mark: "cross",
            eyes: "86 Augen",
            chips: ["2× geschoben ×4"],
            score: "\u2212344",
            counts: ["Du 86", "Anna 20", "Ben 14"],
        },
        {
            scene: "ramsch-other",
            result: OTHER_LOSES,
            word: "Ben verliert",
            mark: null,
            eyes: "86 Augen",
            chips: [],
            score: "\u221286",
            counts: ["Du 20", "Anna 14", "Ben 86"],
        },
        {
            scene: "ramsch-jungfrau",
            result: JUNGFRAU,
            word: "Ben verliert",
            mark: null,
            eyes: "86 Augen",
            chips: ["Jungfrau ×2"],
            score: "\u2212172",
            counts: ["Du 34", "Anna 0", "Ben 86"],
        },
        {
            scene: "ramsch-durchmarsch",
            result: DURCHMARSCH,
            word: "Durchmarsch",
            mark: null,
            eyes: "120 Augen",
            chips: [],
            score: "+120",
            counts: ["Du 0", "Anna 120", "Ben 0"],
        },
    ])("draws $scene with the answer's numbers", ({ result, word, mark, eyes, chips, score, counts }) => {
        const view = drawnRamsch(ramschTable(3, result));

        expect(view.word).toBe(word);
        expect(view.mark).toBe(mark);
        expect(view.eyes).toBe(eyes);
        expect(view.chips).toEqual(chips);
        expect(view.score).toBe(score);
        expect(view.counts.map((count) => `${count.name} ${String(count.points)}`)).toEqual(counts);
    });

    it("marks the loser's own head as lost and the sweeper's as won", () => {
        expect(drawnRamsch(ramschTable(3, LOST_WITH_PUSHES))).toMatchObject({ lost: true, mark: "cross" });
        expect(drawnRamsch(ramschTable(1, DURCHMARSCH))).toMatchObject({
            word: words["result.won"],
            mark: "tick",
            lost: false,
        });
    });

    it("shows a watcher the loser by name and a Durchmarsch by its word", () => {
        expect(drawnRamsch(ramschTable(NOBODY, OTHER_LOSES)).word).toBe("Ben verliert");
        expect(drawnRamsch(ramschTable(NOBODY, DURCHMARSCH)).word).toBe("Durchmarsch");
    });

    it("names both losers of a tie, and tells a loser of the tie it is lost", () => {
        const tie = ramschResult([50, 50, 20], [-50, -50, 0], {});

        expect(drawnRamsch(ramschTable(3, tie)).word).toBe("Anna und Ben verlieren");
        expect(drawnRamsch(ramschTable(1, tie)).word).toBe("Verloren");
        expect(drawnRamsch(ramschTable(3, tie)).counts.filter((count) => count.strong)).toHaveLength(2);
    });

    it("reads a chair left while the result stands as free in the head and the counts", () => {
        const view = drawnRamsch(ramschTable(NOBODY, OTHER_LOSES, { 2: { occupant_name: null } }));

        expect(view.word).toBe(`${words["result.seatFree"]} verliert`);
        expect(view.counts.map((count) => count.name)).toEqual(["Anna", words["result.seatFree"], "Felix"]);
    });

    it.each([
        {
            scene: "a lost game",
            result: ramschResult([20, 14, 86], [0, 0, -86], { pushes: 2, push_factor: 1 }),
            score: "\u221286",
        },
        {
            scene: "a Durchmarsch",
            result: ramschResult([120, 0, 0], [120, 0, 0], { durchmarsch_seat: 1, pushes: 2, push_factor: 1 }),
            score: "+120",
        },
    ])("names the pushes of $scene without a factor when the table does not double them", ({ result, score }) => {
        const view = drawnRamsch(ramschTable(3, result));

        expect(view.chips).toEqual(["2× geschoben"]);
        expect(view.score).toBe(score);
    });

    it("names the division by ten before the pushes and the doubling it comes ahead of", () => {
        const byTen = ramschResult([20, 14, 86], [0, 0, -64], {
            divided_by_ten: true,
            jungfrau: true,
            pushes: 2,
            push_factor: 4,
        });

        expect(drawnRamsch(ramschTable(3, byTen))).toMatchObject({
            eyes: "86 Augen",
            chips: ["÷ 10", "2× geschoben ×4", "Jungfrau ×2"],
            score: "\u221264",
        });
    });

    it("lists the coasters with the viewer first and what each seat adds", () => {
        const view = drawnRamsch(ramschTable(3, LOST_WITH_PUSHES));

        expect(view.rows.map((row) => `${row.name ?? ""} ${row.gainText}`)).toEqual([
            "Du \u2212344",
            "Anna 0",
            "Ben 0",
        ]);
        expect(drawnRamsch(ramschTable(1, DURCHMARSCH)).rows[0]).toMatchObject({ gainText: "+120", won: true });
    });
});

describe("a Ramsch result", () => {
    const ramsch = (): Table => ramschTable(1, OTHER_LOSES);

    it("is no declared result, so the declared card is not drawn for it", () => {
        expect(declaredResult(ramsch())).toBeNull();
    });

    it("keeps the bar's Weiter, which taps with the result's ordinal", () => {
        expect(weiterBar(ramsch())).toEqual({ kind: "tap", again: false });
    });

    it("is no result that just appeared", () => {
        const before = { ...ramschTable(1, OTHER_LOSES), result: null, version: 8 };

        expect(resultJustAppeared(before, ramsch())).toBeNull();
    });
});
