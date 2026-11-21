import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Place } from "#lib/takt/timeline.ts";
import type { Card } from "../../routes/(start)/tables.ts";

const ACE: Card = { suit: "kreuz", rank: "ace" };
const KING: Card = { suit: "herz", rank: "king" };
const PLACE: Place = { x: 195, y: 700, width: 84, turn: -6 };

describe("the card the own hand let go", () => {
    let hand: typeof import("#lib/takt/letGo.ts");

    beforeEach(async () => {
        vi.resetModules();
        hand = await import("#lib/takt/letGo.ts");
    });

    it("has its place told once", () => {
        hand.cardLetGo(ACE, PLACE);

        expect(hand.letGoPlaceOf({ ...ACE })).toEqual(PLACE);
        expect(hand.letGoPlaceOf(ACE)).toBeUndefined();
    });

    it("keeps its place while another card is asked for", () => {
        hand.cardLetGo(ACE, PLACE);

        expect(hand.letGoPlaceOf(KING)).toBeUndefined();
        expect(hand.letGoPlaceOf(ACE)).toEqual(PLACE);
    });

    it("is none before a hand let a card go", () => {
        expect(hand.letGoPlaceOf(ACE)).toBeUndefined();
    });
});
