import { describe, expect, it } from "vitest";
import { awaitedNames, resultView, weiterBar } from "#lib/result.ts";
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
        hand: null,
        ...changes[seat],
    }));
}

function result(changes: Partial<Result> = {}): Result {
    return {
        ordinal: 3,
        declarer_seat: DECLARER_SEAT,
        game: "kreuz",
        won: true,
        overbid: false,
        bid: 18,
        game_value: 24,
        score: 36,
        declarer_points: 78,
        opponents_points: 42,
        gains: [
            { seat: 1, gain: 0 },
            { seat: 2, gain: 86 },
            { seat: 3, gain: 0 },
        ],
        ...changes,
    };
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
    };
}

describe("the card's words and sides for each viewer", () => {
    it.each([
        { viewer: "the declarer who won", mine: 2, won: true, word: words.resultWon, good: true },
        { viewer: "the declarer who lost", mine: 2, won: false, word: words.resultLost, good: false },
        { viewer: "an opponent when the declarer won", mine: 1, won: true, word: words.resultLost, good: false },
        { viewer: "an opponent when the declarer lost", mine: 1, won: false, word: words.resultWon, good: true },
        { viewer: "a watcher when the declarer won", mine: NOBODY, won: true, word: "player 2 gewinnt", good: true },
        {
            viewer: "a watcher when the declarer lost",
            mine: NOBODY,
            won: false,
            word: "player 2 verliert",
            good: false,
        },
    ])("gives $viewer the word $word", ({ mine, won, word, good }) => {
        const view = resultView(table(mine, { won }));

        expect(view.word).toBe(word);
        expect(view.good).toBe(good);
    });

    it.each([
        { viewer: "the declarer", mine: 2, sides: { declarer: words.sideYou, opponents: words.sideThem } },
        { viewer: "an opponent", mine: 1, sides: { declarer: "player 2", opponents: words.sideUs } },
        { viewer: "a watcher", mine: NOBODY, sides: { declarer: "player 2", opponents: words.sideThem } },
    ])("names the sides for $viewer", ({ mine, sides }) => {
        expect(resultView(table(mine, {})).sides).toEqual(sides);
    });

    it("carries the points of both sides as the server counted them", () => {
        expect(resultView(table(2, {})).points).toEqual({ declarer: 78, opponents: 42 });
    });

    it.each([
        { won: true, score: 36, text: "+36" },
        { won: false, score: -72, text: "−72" },
    ])("shows the declarer the signed score $text", ({ won, score, text }) => {
        expect(resultView(table(2, { won, score })).score).toBe(text);
    });

    it.each([
        { viewer: "an opponent", mine: 1 },
        { viewer: "a watcher", mine: NOBODY },
    ])("shows $viewer no score", ({ mine }) => {
        expect(resultView(table(mine, {})).score).toBeNull();
    });

    it.each([
        { viewer: "the declarer", mine: 2, byName: null },
        { viewer: "an opponent", mine: 1, byName: "player 2" },
        { viewer: "a watcher", mine: NOBODY, byName: null },
    ])("names the declarer on the game line for $viewer only when it is not their own game", ({ mine, byName }) => {
        const view = resultView(table(mine, {}));

        expect(view.game).toBe("kreuz");
        expect(view.byName).toBe(byName);
    });
});

describe("a declarer who has left", () => {
    it("leaves their name empty on the opponent's game line", () => {
        expect(resultView(table(1, {}, { 2: { occupant_name: null } })).byName).toBe("");
    });
});

describe("the overbid", () => {
    it("states the worth against the bid", () => {
        expect(resultView(table(2, { overbid: true, game_value: 18, bid: 20 })).miss).toBe(
            `${words.gameWorth} 18 < ${words.bidValue} 20`,
        );
    });

    it("states nothing when the game was not overbid", () => {
        expect(resultView(table(2, { overbid: false })).miss).toBeNull();
    });
});

describe("the reckoning row", () => {
    it("lists the own chair first and marks the declarer as the winner of a won game", () => {
        const rows = resultView(table(3, { won: true })).rows;

        expect(rows.map(({ seat }) => seat)).toEqual([3, 1, 2]);
        expect(rows.map(({ gain }) => gain)).toEqual([0, 0, 86]);
        expect(rows.map(({ winner }) => winner)).toEqual([false, false, true]);
        expect(rows.map(({ name }) => name)).toEqual(["player 3", "player 1", "player 2"]);
    });

    it("writes a loss with a minus sign and a gain without a plus", () => {
        const rows = resultView(
            table(2, {
                gains: [
                    { seat: 1, gain: -4 },
                    { seat: 2, gain: 86 },
                    { seat: 3, gain: 0 },
                ],
            }),
        ).rows;

        expect(rows.map(({ gainText }) => gainText)).toEqual(["86", "\u22124", "0"]);
    });

    it("marks both opponents as the winners of a lost game", () => {
        const rows = resultView(table(2, { won: false })).rows;

        expect(rows.map(({ seat, winner }) => [seat, winner])).toEqual([
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
