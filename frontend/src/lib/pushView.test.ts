import { describe, expect, it } from "vitest";
import { mayDeclareGrandHand, mayPick, pushStage } from "#lib/pushView.ts";
import { CLUBS_JACK, CLUBS_SEVEN, FOREHAND, MIDDLEHAND, WATCHER, table } from "#lib/pushView.fixtures.ts";
import type { Picking, Stage, Table } from "../routes/(start)/tables.ts";

describe("what the stage before a Ramsch asks of this viewer", () => {
    it.each<Stage>(["choosing", "discarding"])("asks the seat on turn to act at %s", (stage) => {
        expect(pushStage(table(FOREHAND, stage))).toBe(stage);
    });

    it("asks nothing of a seat that is not on turn", () => {
        expect(pushStage(table(MIDDLEHAND, "choosing"))).toBeNull();
    });

    it("asks nothing of a person with no chair", () => {
        expect(pushStage(table(WATCHER, "choosing"))).toBeNull();
    });

    it("asks nothing while a chair is open", () => {
        expect(pushStage(table(FOREHAND, "choosing", { waiting_seat: 3 }))).toBeNull();
    });

    it.each<Stage>(["picked", "declared"])("asks nothing at %s, a step of the declarer's stage", (stage) => {
        expect(pushStage(table(FOREHAND, stage))).toBeNull();
    });

    it("asks nothing once the stage is over", () => {
        expect(pushStage(table(FOREHAND, "choosing", { pushing: null }))).toBeNull();
    });
});

describe("whether the seat on turn may declare a Grand Hand instead", () => {
    it("may at a table that allows it, as the seat on turn choosing", () => {
        expect(mayDeclareGrandHand(table(FOREHAND, "choosing", {}, "allowed"))).toBe(true);
    });

    it.each<[string, Table]>([
        ["the table does not allow it", table(FOREHAND, "choosing", {}, "off")],
        ["the table has no Ramsch with pushing", table(FOREHAND, "choosing")],
        ["the seat is not on turn", table(MIDDLEHAND, "choosing", {}, "allowed")],
        ["the viewer has no chair", table(WATCHER, "choosing", {}, "allowed")],
        ["the stage is past choosing", table(FOREHAND, "discarding", {}, "allowed")],
        ["a chair is open", table(FOREHAND, "choosing", { waiting_seat: 3 }, "allowed")],
    ])("may not when %s", (_reason, shown) => {
        expect(mayDeclareGrandHand(shown)).toBe(false);
    });
});

describe("the cards the hand lets a seat pick", () => {
    const picking = (changes: Partial<Picking>): Picking => ({
        picked: [],
        disabled: false,
        toggle: () => undefined,
        ...changes,
    });

    it.each([
        { card: CLUBS_SEVEN, may: true },
        { card: CLUBS_JACK, may: false },
    ])("lets $card.rank pick: $may when the answer names only the seven", ({ card, may }) => {
        expect(mayPick(picking({ allowed: [CLUBS_SEVEN] }), card)).toBe(may);
    });

    it("lets every card pick when no card is ruled out", () => {
        expect(mayPick(picking({}), CLUBS_JACK)).toBe(true);
    });
});
