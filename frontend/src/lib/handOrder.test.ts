import { describe, expect, it } from "vitest";
import { inDisplayOrder } from "#lib/handOrder.ts";
import type { Card } from "../routes/(start)/tables.ts";

const DISPLAY_ORDER: Card[] = [
    { suit: "kreuz", rank: "jack" },
    { suit: "pik", rank: "jack" },
    { suit: "herz", rank: "jack" },
    { suit: "karo", rank: "jack" },
    { suit: "kreuz", rank: "ace" },
    { suit: "kreuz", rank: "ten" },
    { suit: "kreuz", rank: "king" },
    { suit: "kreuz", rank: "queen" },
    { suit: "kreuz", rank: "nine" },
    { suit: "kreuz", rank: "eight" },
    { suit: "kreuz", rank: "seven" },
    { suit: "pik", rank: "ace" },
    { suit: "pik", rank: "ten" },
    { suit: "pik", rank: "king" },
    { suit: "pik", rank: "queen" },
    { suit: "pik", rank: "nine" },
    { suit: "pik", rank: "eight" },
    { suit: "pik", rank: "seven" },
    { suit: "herz", rank: "ace" },
    { suit: "herz", rank: "ten" },
    { suit: "herz", rank: "king" },
    { suit: "herz", rank: "queen" },
    { suit: "herz", rank: "nine" },
    { suit: "herz", rank: "eight" },
    { suit: "herz", rank: "seven" },
    { suit: "karo", rank: "ace" },
    { suit: "karo", rank: "ten" },
    { suit: "karo", rank: "king" },
    { suit: "karo", rank: "queen" },
    { suit: "karo", rank: "nine" },
    { suit: "karo", rank: "eight" },
    { suit: "karo", rank: "seven" },
];

function cards(...names: string[]): Card[] {
    return names.map((name) => {
        const [suit, rank] = name.split(" ") as [Card["suit"], Card["rank"]];
        return { suit, rank };
    });
}

const MIXED_HAND = cards(
    "karo eight",
    "herz jack",
    "kreuz seven",
    "pik ace",
    "herz ten",
    "kreuz ten",
    "karo king",
    "pik nine",
    "kreuz queen",
    "karo jack",
);

describe("inDisplayOrder", () => {
    it("puts all 32 cards in the fixed order when no game is known, however they arrive", () => {
        expect(inDisplayOrder([...DISPLAY_ORDER].reverse(), null)).toEqual(DISPLAY_ORDER);
    });

    it("keeps that order for the ten cards of one hand when no game is known", () => {
        expect(inDisplayOrder(MIXED_HAND, null)).toEqual(
            cards(
                "herz jack",
                "karo jack",
                "kreuz ten",
                "kreuz queen",
                "kreuz seven",
                "pik ace",
                "pik nine",
                "herz ten",
                "karo king",
                "karo eight",
            ),
        );
    });

    it("shows Grand as the order without a game", () => {
        expect(inDisplayOrder([...DISPLAY_ORDER].reverse(), "grand")).toEqual(DISPLAY_ORDER);
    });

    it.each(["kreuz", "pik", "herz", "karo"] as const)(
        "shows the jacks, then the %s trump suit, then the other suits in their order",
        (trump) => {
            const others = ["kreuz", "pik", "herz", "karo"].filter((suit) => suit !== trump);
            const ranks = ["ace", "ten", "king", "queen", "nine", "eight", "seven"];
            const expected = [
                ...["kreuz", "pik", "herz", "karo"].map((suit) => `${suit} jack`),
                ...[trump, ...others].flatMap((suit) => ranks.map((rank) => `${suit} ${rank}`)),
            ];

            expect(inDisplayOrder([...DISPLAY_ORDER].reverse(), trump)).toEqual(cards(...expected));
        },
    );

    it("puts the karo cards of a Karo game right after the jacks, as the operator saw them misplaced", () => {
        expect(inDisplayOrder(MIXED_HAND, "karo")).toEqual(
            cards(
                "herz jack",
                "karo jack",
                "karo king",
                "karo eight",
                "kreuz ten",
                "kreuz queen",
                "kreuz seven",
                "pik ace",
                "pik nine",
                "herz ten",
            ),
        );
    });

    it("shows Null by its own ranks with the jacks in their suit, the suits in their order", () => {
        const expected = ["kreuz", "pik", "herz", "karo"].flatMap((suit) =>
            ["ace", "king", "queen", "jack", "ten", "nine", "eight", "seven"].map((rank) => `${suit} ${rank}`),
        );
        const nullCards = cards(...expected);

        expect(inDisplayOrder([...nullCards].reverse(), "null")).toEqual(nullCards);
    });
});
