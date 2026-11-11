import { describe, expect, it } from "vitest";
import { awaitedNames, declaredResult, resultView, weiterBar, withMinus } from "#lib/result.ts";
import { words } from "#lib/words.ts";
import type { Chair, Result, Table } from "../routes/(start)/tables.ts";

const DECLARER_SEAT = 2;
const NOBODY = 0;

function chairs(mine: number, changes: Record<number, Partial<Chair>> = {}): Chair[] {
    return [1, 2, 3].map((seat) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
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

    it.each([
        { hand: false, label: words["game.kreuz"] },
        { hand: true, label: `${words["game.kreuz"]} ${words["game.hand"]}` },
    ])("names the game with its levels when hand is $hand", ({ hand, label }) => {
        expect(resultView(table(2, { hand })).gameLine).toBe(label);
    });

    it("names an announced Hand game without its announcement, which stands as a chip", () => {
        expect(resultView(table(2, { hand: true, announcement: "schneider" })).gameLine).toBe(
            `${words["game.kreuz"]} ${words["game.hand"]}`,
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
            `${words["game.null"]} ${words["game.ouvert"]} ${words["game.hand"]}`,
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
            `${words["result.gameWorth"]} 18 < ${words["result.bidValue"]} 20 → 27`,
        );
    });

    it("states nothing when the game was not overbid", () => {
        expect(resultView(table(2, {})).raise).toBeNull();
    });
});

describe("the chips", () => {
    it("ticks each counted level after the unticked matadors", () => {
        expect(resultView(table(2, {})).chips).toEqual([
            { word: `${words["result.matadorsWith"]} 2`, ticked: false },
            { word: words["result.levelSpiel"], ticked: true },
        ]);
    });

    it("counts the matadors a game is played without", () => {
        const view = resultView(table(2, { matadors: { mit: false, count: 2 }, game: "grand" }));

        expect(view.chips[0]).toEqual({ word: `${words["result.matadorsWithout"]} 2`, ticked: false });
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
            steps: [`${words["result.levelSpiel"]} +36`, `${words["result.listBonus"]} +50`, "= +86"],
            share: null,
        });
    });

    it("shows the doubling and what each opponent gets for a lost game", () => {
        const view = resultView(table(2, LOST_GAME));

        expect(view.doubled).toBe(true);
        expect(view.list).toEqual({
            side: words["result.sideYou"],
            steps: [`${words["result.levelSpiel"]} −72`, `${words["result.listBonus"]} −50`, "= −122"],
            share: `· ${words["result.sideThem"]} ${words["result.each"]} +40`,
        });
    });

    it.each([
        { viewer: "an opponent", mine: 1, side: "player 2", opponents: words["play.sideUs"] },
        { viewer: "a watcher", mine: NOBODY, side: "player 2", opponents: words["play.sideThem"] },
    ])("names the sides of the list line for $viewer", ({ mine, side, opponents }) => {
        const view = resultView(table(mine, LOST_GAME));

        expect(view.list.side).toBe(side);
        expect(view.list.share).toBe(`· ${opponents} ${words["result.each"]} +40`);
    });
});

describe("the missed announcement", () => {
    it.each([
        { announcement: "schneider", word: words["game.announcedSchneider"] },
        { announcement: "schwarz", word: words["game.announcedSchwarz"] },
    ] as const)("says that $word was not reached", ({ announcement, word }) => {
        const view = resultView(table(2, { ...LOST_GAME, announcement, announcement_missed: true }));

        expect(view.missed).toBe(`${word}, ${words["result.notReached"]}`);
    });

    it("says Schwarz was not reached for a lost ouvert game, which counts as announced Schwarz", () => {
        const view = resultView(
            table(2, { ...LOST_GAME, ouvert: true, game: "grand", announcement: "schwarz", announcement_missed: true }),
        );

        expect(view.missed).toBe(`${words["game.announcedSchwarz"]}, ${words["result.notReached"]}`);
        expect(view.gameLine).toBe(`${words["game.grand"]} ${words["game.ouvert"]}`);
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

describe("a Ramsch result", () => {
    const ramsch = (): Table => ({ ...table(1, null), result: { kind: "ramsch", ordinal: 4 } });

    it("is no declared result, so the page draws no card for it", () => {
        expect(declaredResult(ramsch())).toBeNull();
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

describe("withMinus", () => {
    it.each([
        [0, "0"],
        [160, "160"],
        [-46, "\u221246"],
    ])("reads the total %i as %s", (total, text) => {
        expect(withMinus(total)).toBe(text);
    });
});
