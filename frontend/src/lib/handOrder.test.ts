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

describe("inDisplayOrder", () => {
    it("puts all 32 cards in the fixed order, however they arrive", () => {
        expect(inDisplayOrder([...DISPLAY_ORDER].reverse())).toEqual(DISPLAY_ORDER);
    });

    it("keeps that order for the ten cards of one hand", () => {
        const hand: Card[] = [
            { suit: "karo", rank: "eight" },
            { suit: "herz", rank: "jack" },
            { suit: "kreuz", rank: "seven" },
            { suit: "pik", rank: "ace" },
            { suit: "herz", rank: "ten" },
            { suit: "kreuz", rank: "ten" },
            { suit: "karo", rank: "king" },
            { suit: "pik", rank: "nine" },
            { suit: "kreuz", rank: "queen" },
            { suit: "herz", rank: "ace" },
        ];

        expect(inDisplayOrder(hand)).toEqual([
            { suit: "herz", rank: "jack" },
            { suit: "kreuz", rank: "ten" },
            { suit: "kreuz", rank: "queen" },
            { suit: "kreuz", rank: "seven" },
            { suit: "pik", rank: "ace" },
            { suit: "pik", rank: "nine" },
            { suit: "herz", rank: "ace" },
            { suit: "herz", rank: "ten" },
            { suit: "karo", rank: "king" },
            { suit: "karo", rank: "eight" },
        ]);
    });
});
