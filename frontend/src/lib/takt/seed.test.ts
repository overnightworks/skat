import { describe, expect, it } from "vitest";
import { seriesAt, tableBetweenGames } from "#lib/series.fixtures.ts";
import { fork, seedOf } from "#lib/takt/seed.ts";

const SEED = seedOf(tableBetweenGames(1, seriesAt()));
const drawn = (seed: string, label: string, draws: number): number[] => {
    const stream = fork(seed, label);
    return Array.from({ length: draws }, () => stream.between(0, 1));
};

describe("the seed of a game", () => {
    it("is the same from every chair", () => {
        expect(seedOf(tableBetweenGames(2, seriesAt()))).toBe(SEED);
    });

    it.each([
        { name: "the next game", table: tableBetweenGames(1, seriesAt({ game_number: seriesAt().game_number + 1 })) },
        { name: "the next series", table: tableBetweenGames(1, seriesAt({ number: seriesAt().number + 1 })) },
        { name: "another table", table: { ...tableBetweenGames(1, seriesAt()), id: "b".repeat(32) } },
    ])("is another one for $name", ({ table }) => {
        expect(seedOf(table)).not.toBe(SEED);
    });

    it("counts a table without a series as its first series before the first deal", () => {
        expect(seedOf(tableBetweenGames(1, null))).toBe(
            seedOf(tableBetweenGames(1, seriesAt({ number: 1, game_number: 0 }))),
        );
    });
});

describe("a fork", () => {
    it("draws the same numbers again", () => {
        expect(drawn(SEED, "card/lie", 5)).toEqual(drawn(SEED, "card/lie", 5));
    });

    it("draws what it draws however much another fork drew before", () => {
        const alone = drawn(SEED, "card/lie", 5);

        const other = fork(SEED, "card/toss");
        const late = fork(SEED, "card/lie");
        for (let draw = 0; draw < 100; draw += 1) other.between(0, 1);

        expect(Array.from({ length: 5 }, () => late.between(0, 1))).toEqual(alone);
    });

    it.each([
        { name: "another label", seed: SEED, label: "card/toss" },
        { name: "another seed", seed: `${SEED}0`, label: "card/lie" },
    ])("draws other numbers under $name", ({ seed, label }) => {
        expect(drawn(seed, label, 5)).not.toEqual(drawn(SEED, "card/lie", 5));
    });

    it("draws between its bounds and all over them", () => {
        const stream = fork(SEED, "card/lie");
        const draws = Array.from({ length: 1000 }, () => stream.between(-3, 5));

        expect(Math.min(...draws)).toBeGreaterThanOrEqual(-3);
        expect(Math.max(...draws)).toBeLessThan(5);
        expect(Math.min(...draws)).toBeLessThan(-2.9);
        expect(Math.max(...draws)).toBeGreaterThan(4.9);
    });

    it("draws either sign about as often as the other", () => {
        const stream = fork(SEED, "card/toss");
        const signs = Array.from({ length: 1000 }, () => stream.sign());

        const up = signs.filter((sign) => sign === 1).length;
        expect(new Set(signs)).toEqual(new Set([-1, 1]));
        expect(up).toBeGreaterThan(400);
        expect(up).toBeLessThan(600);
    });
});
