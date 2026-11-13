import { describe, expect, it } from "vitest";
import { mayPick, pushStage } from "#lib/pushView.ts";
import {
    type Card,
    type Picking,
    type Chair,
    type Hand,
    type Pushing,
    type Stage,
    type Table,
} from "../routes/(start)/tables.ts";

const FOREHAND = 1;
const MIDDLEHAND = 2;
const WATCHER = 0;
const CLUBS_JACK: Card = { suit: "kreuz", rank: "jack" };
const CLUBS_SEVEN: Card = { suit: "kreuz", rank: "seven" };

function chairs(mine: number): Chair[] {
    return [FOREHAND, MIDDLEHAND, 3].map((seat) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === mine,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
        former_holder_name: null,
    }));
}

function table(mine: number, stage: Stage, changes: Partial<Hand> = {}): Table {
    const pushing: Pushing = {
        turn_seat: FOREHAND,
        stage,
        moves: [],
        factor: 1,
        put_back_cards: stage === "discarding" ? [CLUBS_SEVEN] : [],
    };
    return {
        id: "a".repeat(32),
        version: 1,
        chairs: chairs(mine),
        watchers: 0,
        result: null,
        passed_in: null,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
        hand: {
            dealer_seat: 3,
            own_cards: [],
            skat_count: 2,
            waiting_seat: null,
            abort: null,
            abortable: false,
            auction: {
                turn_seat: null,
                facing_seat: null,
                awaiting: null,
                standing: null,
                values: [],
                words: [],
                declared: null,
            },
            declaring: null,
            playing: null,
            ramsch: true,
            pushing,
            pushes: 0,
            push_factor: 1,
            ...changes,
        },
    };
}

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
