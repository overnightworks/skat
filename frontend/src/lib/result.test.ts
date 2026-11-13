import { describe, expect, it } from "vitest";
import { awaitedNames, resultJustAppeared, resultView, weiterBar, withMinus } from "#lib/result.ts";
import { chairs, LOST_GAME, NOBODY, NULL_GAME, OTHER_LOSES, table, WON_GAME } from "#lib/result.fixtures.ts";
import { words } from "#lib/words.ts";
import type { Table, Result } from "../routes/(start)/tables.ts";

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

    it("reads a side's trick points as one sentence that marks the side's name and the points", () => {
        const parts = words["result.sidePoints"]({ side: words["result.sideYou"], points: "61" });

        expect(parts).toContainEqual({ marker: "side", text: words["result.sideYou"] });
        expect(parts).toContainEqual({ marker: "tally", text: "61" });
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

// A Bock game multiplies the list score by the factor; the game's value and the list's 50 stay.
const BOCK_GAME: Partial<Result> = { bock_factor: 2, score: 72, gains: [...WON_GAME.gains] };

describe("a Bock game's card", () => {
    it.each([2, 4])("holds the factor ×%i as a ticked chip after the counted levels", (factor) => {
        const view = resultView(table(2, { ...BOCK_GAME, bock_factor: factor, score: 36 * factor }));

        expect(view.chips).toEqual([
            { word: words["result.matadorsWith"](2), ticked: false },
            { word: words["result.levelSpiel"], ticked: true },
            { word: words["bock.factor"]({ factor: String(factor) }), ticked: true },
        ]);
    });

    it("shows the game's value under the multiplier line, so the factor takes it to the score", () => {
        const view = resultView(table(2, BOCK_GAME));

        expect(view.equation).toEqual({ multiplier: 3, base: 12, product: 36 });
        expect(view.score).toBe("+72");
    });

    it("holds the factor of a lost game beside its doubling", () => {
        const view = resultView(table(2, { ...LOST_GAME, bock_factor: 2, score: -144 }));

        expect(view.chips.map(({ word }) => word)).toContain(words["bock.factor"]({ factor: "2" }));
        expect(view.equation).toEqual({ multiplier: 3, base: 12, product: 36 });
        expect(view.score).toBe("\u2212144");
    });

    it("holds the factor in the Kontra row, after the word, when a word was said", () => {
        const view = resultView(table(2, { ...BOCK_GAME, kontra: { word: "kontra", factor: 2 }, score: 144 }));

        expect(view.doublings).toEqual(["Kontra ×2", words["bock.factor"]({ factor: "2" })]);
        expect(view.chips.map(({ word }) => word)).not.toContain(words["bock.factor"]({ factor: "2" }));
        expect(view.equation).toEqual({ multiplier: 3, base: 12, product: 36 });
    });

    it("gives a Null game the chip and its fixed value as the line", () => {
        const view = resultView(table(2, { ...NULL_GAME, bock_factor: 2, game_value: 35, score: 70 }));

        expect(view.chips).toEqual([{ word: words["bock.factor"]({ factor: "2" }), ticked: true }]);
        expect(view.equation).toEqual({ multiplier: null, base: null, product: 35 });
    });

    it("leaves a game without Bock its counted steps and no line under them", () => {
        const view = resultView(table(2, {}));

        expect(view.chips).toHaveLength(2);
        expect(view.equation?.product).toBeNull();
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

    it("names the others the viewer waits for, joined by the list format", () => {
        expect(weiterBar(table(1, {}, { 1: { ready: true } }))).toEqual({
            kind: "wait",
            text: words["table.waitingFor"]({ names: "player 2 und player 3" }),
        });
    });

    it("names the one away member who tapped", () => {
        const bar = weiterBar(
            table(1, {}, { 1: { ready: true }, 2: { ready: true }, 3: { ready: true, is_away: true } }),
        );

        expect(bar).toEqual({ kind: "wait", text: words["table.waitingFor"]({ names: "player 3" }) });
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
        const ramsch: Table = { ...after(null), result: OTHER_LOSES };

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
