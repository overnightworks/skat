import { describe, expect, it } from "vitest";
import {
    awaitedNames,
    declaredResult,
    ramschResultView,
    resultJustAppeared,
    resultView,
    weiterBar,
    withMinus,
    type RamschView,
} from "#lib/result.ts";
import { words } from "#lib/words.ts";
import type { Chair, RamschResult, Table, Result } from "../routes/(start)/tables.ts";

const DECLARER_SEAT = 2;
const NOBODY = 0;

function chairs(mine: number, changes: Record<number, Partial<Chair>> = {}): Chair[] {
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

// Kreuz mit 2, won by the declarer at seat 2: 3 × 12 = 36 plus the list's 50 (ISkO 2.1, 4.1).
const WON_GAME: Result = {
    kind: "declared",
    ordinal: 3,
    declarer_seat: DECLARER_SEAT,
    game: "kreuz",
    hand: false,
    ouvert: false,
    announcement: "none",
    matadors: { mit: true, count: 2 },
    base_value: 12,
    levels: ["spiel"],
    multiplier: 3,
    list_bonus: 50,
    announcement_missed: false,
    won: true,
    doubled: false,
    overbid: false,
    bid: 18,
    game_value: 36,
    settled_value: 36,
    score: 36,
    declarer_points: 78,
    opponents_points: 42,
    gains: [
        { seat: 1, gain: 0, won: false },
        { seat: 2, gain: 86, won: true },
        { seat: 3, gain: 0, won: false },
    ],
    kontra: null,
};

// The same game lost: the value doubles to −72, the list takes 50 and each opponent gets 40.
const LOST_GAME: Partial<Result> = {
    won: false,
    doubled: true,
    list_bonus: -50,
    score: -72,
    gains: [
        { seat: 1, gain: 40, won: true },
        { seat: 2, gain: -122, won: false },
        { seat: 3, gain: 40, won: true },
    ],
};

// Null counts no matadors, levels or multiplier.
const NULL_GAME: Partial<Result> = { game: "null", matadors: null, levels: [], multiplier: null, base_value: null };

function result(changes: Partial<Result> = {}): Result {
    return { ...WON_GAME, ...changes };
}

function table(
    mine: number,
    changes: Partial<Result> | null,
    chairChanges: Record<number, Partial<Chair>> = {},
): Table {
    return {
        id: "a".repeat(32),
        version: 9,
        chairs: chairs(mine, chairChanges),
        watchers: 0,
        hand: null,
        result: changes === null ? null : result(changes),
        passed_in: null,
        ended: null,
    };
}

describe("the card's words and sides for each viewer", () => {
    it.each([
        { viewer: "the declarer who won", mine: 2, won: true, word: words["result.won"], good: true },
        { viewer: "the declarer who lost", mine: 2, won: false, word: words["result.lost"], good: false },
        { viewer: "an opponent when the declarer won", mine: 1, won: true, word: words["result.lost"], good: false },
        { viewer: "an opponent when the declarer lost", mine: 1, won: false, word: words["result.won"], good: true },
        { viewer: "a watcher when the declarer won", mine: NOBODY, won: true, word: "player 2 gewinnt", good: true },
        {
            viewer: "a watcher when the declarer lost",
            mine: NOBODY,
            won: false,
            word: "player 2 verliert",
            good: false,
        },
    ])("gives $viewer the word $word", ({ mine, won, word, good }) => {
        const view = resultView(table(mine, won ? {} : LOST_GAME));

        expect(view.word).toBe(word);
        expect(view.good).toBe(good);
    });

    it.each([
        {
            viewer: "the declarer",
            mine: 2,
            sides: { declarer: words["result.sideYou"], opponents: words["result.sideThem"] },
        },
        { viewer: "an opponent", mine: 1, sides: { declarer: "player 2", opponents: words["play.sideUs"] } },
        { viewer: "a watcher", mine: NOBODY, sides: { declarer: "player 2", opponents: words["play.sideThem"] } },
    ])("names the sides for $viewer", ({ mine, sides }) => {
        expect(resultView(table(mine, {})).sides).toEqual(sides);
    });

    it("reads a side's trick points as one sentence with the points as its gap", () => {
        const sentence = words["result.sidePoints"]({ side: words["result.sideYou"], points: "61" });

        expect(sentence).toContain(words["result.sideYou"]);
        expect(sentence).toContain("61");
    });

    it.each([
        { hand: false, label: words["game.kreuz"] },
        { hand: true, label: words["game.handName"]({ game: words["game.kreuz"] }) },
    ])("names the game with its levels when hand is $hand", ({ hand, label }) => {
        expect(resultView(table(2, { hand })).gameLine).toBe(label);
    });

    it("names an announced Hand game without its announcement, which stands as a chip", () => {
        expect(resultView(table(2, { hand: true, announcement: "schneider" })).gameLine).toBe(
            words["game.handName"]({ game: words["game.kreuz"] }),
        );
    });

    it.each([
        { game: "kreuz", word: words["game.kreuz"] },
        { game: "grand", word: words["game.grand"] },
        { game: "null", word: words["game.null"] },
    ] as const)("carries the word $word for the equation", ({ game, word }) => {
        expect(resultView(table(2, { game })).gameWord).toBe(word);
    });

    it("names a Null game with its levels in the equation", () => {
        const nullOuvertHand = { game: "null", hand: true, ouvert: true } as const;
        expect(resultView(table(2, nullOuvertHand)).gameWord).toBe(
            words["game.ouvertHandName"]({ game: words["game.null"] }),
        );
    });

    it("carries the points of both sides as the server counted them", () => {
        expect(resultView(table(2, {})).points).toEqual({ declarer: 78, opponents: 42 });
    });

    it("gives a Null game no points bar", () => {
        expect(resultView(table(2, { game: "null" })).points).toBeNull();
    });

    it.each([
        { name: "two levels", changes: { levels: ["spiel", "hand"] }, snug: false },
        { name: "three levels", changes: { levels: ["spiel", "hand", "schneider"] }, snug: true },
        { name: "an overbid", changes: { overbid: true }, snug: true },
    ] as const)("packs a reckoning with $name snug is $snug", ({ changes, snug }) => {
        expect(resultView(table(2, { ...changes, levels: [...(changes.levels ?? ["spiel"])] })).snug).toBe(snug);
    });

    it.each([
        { viewer: "the declarer", mine: 2 },
        { viewer: "an opponent", mine: 1 },
        { viewer: "a watcher", mine: NOBODY },
    ])("shows $viewer the signed score of a won and a lost game", ({ mine }) => {
        expect(resultView(table(mine, {})).score).toBe("+36");
        expect(resultView(table(mine, LOST_GAME)).score).toBe("−72");
    });

    it.each([
        { viewer: "the declarer", mine: 2, gameLine: words["game.kreuz"] },
        { viewer: "an opponent", mine: 1, gameLine: `player 2, ${words["game.kreuz"]}` },
        { viewer: "a watcher", mine: NOBODY, gameLine: words["game.kreuz"] },
    ])("names the declarer on the game line for $viewer only when it is not their own game", ({ mine, gameLine }) => {
        const view = resultView(table(mine, {}));

        expect(view.suit).toBe("kreuz");
        expect(view.gameLine).toBe(gameLine);
    });

    it.each(["grand", "null"] as const)("gives a %s game no trump suit", (game) => {
        expect(resultView(table(2, { game })).suit).toBeNull();
    });
});

describe("a declarer who has left", () => {
    it("leaves their name empty on the opponent's game line", () => {
        expect(resultView(table(1, {}, { 2: { occupant_name: null } })).gameLine).toBe(`, ${words["game.kreuz"]}`);
    });
});

describe("the overbid", () => {
    // Karo mit 1, bid 20: the value 2 × 9 = 18 falls short and is raised to 27, the next multiple of 9 above 20.
    const overbid: Partial<Result> = {
        ...LOST_GAME,
        overbid: true,
        bid: 20,
        game_value: 18,
        settled_value: 27,
        score: -54,
    };

    it("states the worth against the bid and the value it was raised to", () => {
        expect(resultView(table(2, overbid)).raise).toBe(
            words["result.raise"]({ value: "18", bid: "20", settled: "27" }),
        );
    });

    it("states nothing when the game was not overbid", () => {
        expect(resultView(table(2, {})).raise).toBeNull();
    });
});

describe("the chips", () => {
    it("ticks each counted level after the unticked matadors", () => {
        expect(resultView(table(2, {})).chips).toEqual([
            { word: words["result.matadorsWith"](2), ticked: false },
            { word: words["result.levelSpiel"], ticked: true },
        ]);
    });

    it("counts the matadors a game is played without", () => {
        const view = resultView(table(2, { matadors: { mit: false, count: 2 }, game: "grand" }));

        expect(view.chips[0]).toEqual({ word: words["result.matadorsWithout"](2), ticked: false });
    });

    it("words every level the answer sends", () => {
        const levels = [
            "spiel",
            "hand",
            "schneider",
            "schneider_announced",
            "schwarz",
            "schwarz_announced",
            "ouvert",
        ] as const;

        expect(
            resultView(table(2, { levels: [...levels] }))
                .chips.slice(1)
                .map(({ word }) => word),
        ).toEqual([
            words["result.levelSpiel"],
            words["result.hand"],
            words["result.levelSchneider"],
            words["result.announcedSchneider"],
            words["result.levelSchwarz"],
            words["result.announcedSchwarz"],
            words["result.levelOuvert"],
        ]);
    });

    it("gives a Null game no chips", () => {
        const view = resultView(table(2, NULL_GAME));

        expect(view.chips).toEqual([]);
    });
});

describe("the multiplier line", () => {
    it("shows the multiplier times the base without the value for a won game", () => {
        expect(resultView(table(2, {})).equation).toEqual({ multiplier: 3, base: 12, product: null });
    });

    it("adds the value of a lost game", () => {
        expect(resultView(table(2, LOST_GAME)).equation).toEqual({ multiplier: 3, base: 12, product: 36 });
    });

    it("shows a won Null game no line", () => {
        expect(resultView(table(2, { ...NULL_GAME, game_value: 35, score: 35 })).equation).toBeNull();
    });

    it("shows a lost Null game its fixed value alone", () => {
        expect(resultView(table(2, { ...NULL_GAME, ...LOST_GAME, game_value: 23, score: -46 })).equation).toEqual({
            multiplier: null,
            base: null,
            product: 23,
        });
    });
});

describe("the doubling and the list line", () => {
    it("shows no doubling and no share for a won game", () => {
        const view = resultView(table(2, {}));

        expect(view.doubled).toBe(false);
        expect(view.list).toEqual({
            side: words["result.sideYou"],
            steps: [words["result.listGame"]({ score: "+36" }), words["result.listBonus"]({ bonus: "+50" }), "= +86"],
            share: null,
        });
    });

    it("shows the doubling and what each opponent gets for a lost game", () => {
        const view = resultView(table(2, LOST_GAME));

        expect(view.doubled).toBe(true);
        expect(view.list).toEqual({
            side: words["result.sideYou"],
            steps: [words["result.listGame"]({ score: "−72" }), words["result.listBonus"]({ bonus: "−50" }), "= −122"],
            share: words["result.share"]({ opponents: words["result.sideThem"], gain: "+40" }),
        });
    });

    it.each([
        { viewer: "an opponent", mine: 1, side: "player 2", opponents: words["play.sideUs"] },
        { viewer: "a watcher", mine: NOBODY, side: "player 2", opponents: words["play.sideThem"] },
    ])("names the sides of the list line for $viewer", ({ mine, side, opponents }) => {
        const view = resultView(table(mine, LOST_GAME));

        expect(view.list.side).toBe(side);
        expect(view.list.share).toBe(words["result.share"]({ opponents, gain: "+40" }));
    });
});

// Each word said doubles the game's score once more; the list's 50 stays.
describe("the Kontra words on the card", () => {
    const KONTRA_SCORES = [
        { word: "kontra", text: "Kontra", factor: 2, steps: ["Kontra ×2"] },
        { word: "re", text: "Re", factor: 4, steps: ["Kontra ×2", "Re ×4"] },
        { word: "supra", text: "Supra", factor: 8, steps: ["Kontra ×2", "Re ×4", "Supra ×8"] },
        { word: "hirsch", text: "Hirsch", factor: 16, steps: ["Kontra ×2", "Re ×4", "Supra ×8", "Hirsch ×16"] },
    ] as const;

    it.each(KONTRA_SCORES)("draws a won game after $text as steps that multiply to its score", (said) => {
        const view = resultView(
            table(2, { kontra: { word: said.word, factor: said.factor }, score: 36 * said.factor, list_bonus: 50 }),
        );
        const drawn = view.doublings.map((chip) => Number(chip.split("×")[1]));

        expect(view.doublings).toEqual(said.steps);
        expect((view.equation?.multiplier as number) * (view.equation?.base as number) * (drawn.at(-1) as number)).toBe(
            Number(view.score.replace("+", "")),
        );
    });

    it.each(KONTRA_SCORES)("draws a lost game after $text with the loss doubled once more", (said) => {
        const view = resultView(
            table(2, {
                ...LOST_GAME,
                kontra: { word: said.word, factor: said.factor },
                score: -72 * said.factor,
            }),
        );
        const drawn = Number(view.doublings.at(-1)?.split("×")[1]);

        expect(view.equation?.product).toBe(36);
        expect(view.doubled).toBe(true);
        expect(2 * (view.equation?.product as number) * drawn).toBe(-Number(view.score.replace("−", "-")));
    });

    it.each(KONTRA_SCORES)("names $text in the list line's game step", (said) => {
        const view = resultView(
            table(2, { kontra: { word: said.word, factor: said.factor }, score: 36 * said.factor }),
        );

        expect(view.list.steps[0]).toBe(
            words["result.listGameWord"]({ word: said.text, score: `+${String(36 * said.factor)}` }),
        );
        expect(view.snug).toBe(true);
    });

    it("leaves a game nobody doubled as it was", () => {
        const view = resultView(table(2, {}));

        expect(view.doublings).toEqual([]);
        expect(view.list.steps[0]).toBe(words["result.listGame"]({ score: "+36" }));
        expect(view.snug).toBe(false);
    });
});

describe("the missed announcement", () => {
    it.each([
        { announcement: "schneider", missed: words["result.missedSchneider"] },
        { announcement: "schwarz", missed: words["result.missedSchwarz"] },
    ] as const)("says that the $announcement announcement was not reached", ({ announcement, missed }) => {
        const view = resultView(table(2, { ...LOST_GAME, announcement, announcement_missed: true }));

        expect(view.missed).toBe(missed);
    });

    it("says Schwarz was not reached for a lost ouvert game, which counts as announced Schwarz", () => {
        const view = resultView(
            table(2, { ...LOST_GAME, ouvert: true, game: "grand", announcement: "schwarz", announcement_missed: true }),
        );

        expect(view.missed).toBe(words["result.missedSchwarz"]);
        expect(view.gameLine).toBe(words["game.ouvertName"]({ game: words["game.grand"] }));
    });

    it("says nothing when the announcement was reached or none was made", () => {
        expect(resultView(table(2, { announcement: "schneider" })).missed).toBeNull();
    });
});

describe("the reckoning row", () => {
    it("lists the own chair first and glows the side the answer says won", () => {
        const rows = resultView(table(3, {})).rows;

        expect(rows.map(({ seat }) => seat)).toEqual([3, 1, 2]);
        expect(rows.map(({ gain }) => gain)).toEqual([0, 0, 86]);
        expect(rows.map(({ won }) => won)).toEqual([false, false, true]);
        expect(rows.map(({ name }) => name)).toEqual([words["result.sideYou"], "player 1", "player 2"]);
        expect(rows.map(({ initial }) => initial)).toEqual(["p", "p", "p"]);
    });

    it("names every row of a watcher by its occupant", () => {
        expect(resultView(table(NOBODY, {})).rows.map(({ name }) => name)).toEqual([
            "player 1",
            "player 2",
            "player 3",
        ]);
    });

    it("writes a gain with a plus, a loss with a minus sign and nothing with a bare zero", () => {
        const rows = resultView(
            table(2, {
                gains: [
                    { seat: 1, gain: -4, won: false },
                    { seat: 2, gain: 86, won: true },
                    { seat: 3, gain: 0, won: false },
                ],
            }),
        ).rows;

        expect(rows.map(({ gainText }) => gainText)).toEqual(["+86", "\u22124", "0"]);
    });

    it("glows both opponents of a lost game", () => {
        const rows = resultView(table(2, LOST_GAME)).rows;

        expect(rows.map(({ seat, won }) => [seat, won])).toEqual([
            [2, false],
            [1, true],
            [3, true],
        ]);
    });

    it("lists a watcher's rows in seat order", () => {
        expect(resultView(table(NOBODY, {})).rows.map(({ seat }) => seat)).toEqual([1, 2, 3]);
    });

    it("keeps the row of a chair that has been left, without a name", () => {
        const rows = resultView(table(2, {}, { 1: { occupant_name: null } })).rows;

        expect(rows.find(({ seat }) => seat === 1)?.name).toBeNull();
    });
});

describe("who is awaited", () => {
    it("names the occupied chairs that have not tapped", () => {
        expect(awaitedNames(chairs(1, { 1: { ready: true } }))).toEqual(["player 2", "player 3"]);
    });

    it("still awaits a member who tapped and is away", () => {
        expect(
            awaitedNames(chairs(1, { 1: { ready: true }, 2: { ready: true, is_away: true }, 3: { ready: true } })),
        ).toEqual(["player 2"]);
    });

    it("does not await a free chair", () => {
        expect(awaitedNames(chairs(1, { 3: { occupant_name: null } }))).toEqual(["player 1", "player 2"]);
    });
});

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
    return { ...table(mine, null, { ...RAMSCH_NAMES, ...left }), result };
}

function drawnRamsch(table: Table): RamschView {
    return ramschResultView(table) as RamschView;
}

// The four blessed scenes of the Ramsch's card, seen from Felix at seat 3.
const LOST_WITH_PUSHES = ramschResult([20, 14, 86], [0, 0, -344], { pushes: 2, push_factor: 4 });
const OTHER_LOSES = ramschResult([14, 86, 20], [0, -86, 0], {});
const JUNGFRAU = ramschResult([0, 86, 34], [0, -172, 0], { jungfrau: true });
const DURCHMARSCH = ramschResult([120, 0, 0], [120, 0, 0], { durchmarsch_seat: 1 });

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
        expect(ramschResultView(table(1, {}))).toBeNull();
        expect(declaredResult(table(1, {}))).toEqual(WON_GAME);
    });

    it("keeps the bar's Weiter, which taps with the result's ordinal", () => {
        expect(weiterBar(ramsch())).toEqual({ kind: "tap", again: false });
    });
});

describe("the bar's Weiter", () => {
    it("offers a watcher neither the button nor the status", () => {
        expect(weiterBar(table(NOBODY, {}))).toBeNull();
    });

    it("offers nothing while no result stands", () => {
        expect(weiterBar(table(1, null))).toBeNull();
    });

    it("offers the button to a seated viewer who has not tapped", () => {
        expect(weiterBar(table(1, {}))).toEqual({ kind: "tap", again: false });
    });

    it("names the others the viewer waits for, joined with und", () => {
        expect(weiterBar(table(1, {}, { 1: { ready: true } }))).toEqual({
            kind: "wait",
            names: "player 2 und player 3",
        });
    });

    it("names the one away member who tapped", () => {
        const bar = weiterBar(
            table(1, {}, { 1: { ready: true }, 2: { ready: true }, 3: { ready: true, is_away: true } }),
        );

        expect(bar).toEqual({ kind: "wait", names: "player 3" });
    });

    it("keeps the button when the viewer tapped and nobody is awaited, so a tap asks for the deal again", () => {
        const everyoneReady = { 1: { ready: true }, 2: { ready: true }, 3: { ready: true } };

        expect(weiterBar(table(1, {}, everyoneReady))).toEqual({ kind: "tap", again: true });
    });
});

describe("the result that just appeared", () => {
    const before = { ...table(1, null), version: 8 };
    const after = (changes: Partial<Result> | null = {}): Table => ({ ...table(1, changes), version: 9 });

    it("is the ordinal of a result that the update brings to a table that had none", () => {
        expect(resultJustAppeared(before, after({ ordinal: 4 }))).toBe(4);
    });

    it("is the next ordinal when a result stands and the update brings another one", () => {
        const standing = { ...after({ ordinal: 4 }), version: 8 };

        expect(resultJustAppeared(standing, after({ ordinal: 5 }))).toBe(5);
    });

    it("is nothing for the first table of a page, a reload or a late join", () => {
        expect(resultJustAppeared(undefined, after())).toBeNull();
    });

    it("is nothing while the same result stands, as when a Weiter mark arrives", () => {
        expect(resultJustAppeared({ ...after({ ordinal: 4 }), version: 8 }, after({ ordinal: 4 }))).toBeNull();
    });

    it("is nothing for an update that is not newer than the one before", () => {
        expect(resultJustAppeared({ ...before, version: 9 }, after())).toBeNull();
    });

    it("is nothing when the update brings no result or a Ramsch result", () => {
        const ramsch: Table = { ...after(null), result: { kind: "ramsch", ordinal: 6 } };

        expect(resultJustAppeared(before, after(null))).toBeNull();
        expect(resultJustAppeared(before, ramsch)).toBeNull();
    });
});

describe("withMinus", () => {
    it.each([
        [0, "0"],
        [160, "160"],
        [-46, "\u221246"],
    ])("reads the total %i as %s", (total, text) => {
        expect(withMinus(total)).toBe(text);
    });
});
