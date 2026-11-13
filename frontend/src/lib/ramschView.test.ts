import { describe, expect, it } from "vitest";
import { ramschMarks, ramschPlaque, ramschTrick, type RamschMarks } from "#lib/ramschView.ts";
import { words } from "#lib/words.ts";
import type { Hand, Playing, Pushing, Table } from "../routes/(start)/tables.ts";

const ANNA = 1;
const FELIX = 2;
const NOVA = 3;
const WATCHER = 0;
const QUIET: RamschMarks = { turn: false, thinks: false, pushed: false };

function chairs(mine: number): Table["chairs"] {
    const people = [
        { seat: ANNA, name: "Anna", kind: "person" },
        { seat: FELIX, name: "Felix", kind: "person" },
        { seat: NOVA, name: "Nova", kind: "agent" },
    ] as const;
    return people.map(({ seat, name, kind }) => ({
        seat,
        occupant_name: name,
        occupant_kind: kind,
        is_mine: seat === mine,
        is_away: false,
        ready: false,
        total: null,
        hand: { position: "forehand", card_count: 10 },
        former_holder_name: null,
        is_mine_to_return: false,
    }));
}

const PLAYING: Playing = {
    turn_seat: ANNA,
    current_trick: [],
    last_trick: null,
    legal_cards: [],
    give_up: null,
    kontra: null,
    running_points: null,
};

function stage(changes: Partial<Pushing>): Pushing {
    return { turn_seat: ANNA, stage: "choosing", moves: [], factor: 1, put_back_cards: [], ...changes };
}

function ramsch(mine: number, changes: Partial<Hand>): Table {
    return {
        id: "a".repeat(32),
        version: 7,
        chairs: chairs(mine),
        watchers: 0,
        result: null,
        passed_in: null,
        options: null,
        bock: null,
        ended: null,
        hand: {
            dealer_seat: NOVA,
            own_cards: [],
            skat_count: 2,
            waiting_seat: null,
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
            pushing: stage({}),
            pushes: 0,
            push_factor: 1,
            ...changes,
        },
    };
}

describe("the plaque of a Ramsch", () => {
    it("is none outside a Ramsch", () => {
        expect(ramschPlaque(ramsch(FELIX, { ramsch: false }))).toBeNull();
        expect(ramschPlaque({ ...ramsch(FELIX, {}), hand: null })).toBeNull();
    });

    it("names who chooses to everyone but the seat on turn, and the waiting dots go with it", () => {
        const plaque = ramschPlaque(ramsch(FELIX, {}));

        expect(plaque).toEqual({
            pushes: null,
            factor: null,
            acting: `Anna ${words["table.chooses"]}`,
            waiting: false,
        });
        expect(ramschPlaque(ramsch(WATCHER, {}))?.acting).toBe(`Anna ${words["table.chooses"]}`);
    });

    it("names who discards once the seat on turn took the skat", () => {
        const plaque = ramschPlaque(ramsch(FELIX, { pushing: stage({ stage: "discarding" }) }));

        expect(plaque?.acting).toBe(`Anna ${words["table.discards"]}`);
    });

    it("names nobody to the seat on turn itself", () => {
        expect(ramschPlaque(ramsch(ANNA, {}))?.acting).toBeNull();
    });

    it.each([
        { pushes: 1, factor: 2, line: "1× geschoben", doubled: "×2" },
        { pushes: 2, factor: 4, line: "2× geschoben", doubled: "×4" },
        { pushes: 3, factor: 8, line: "3× geschoben", doubled: "×8" },
    ])("counts $pushes pushes with the factor the answer sends", ({ pushes, factor, line, doubled }) => {
        const plaque = ramschPlaque(ramsch(FELIX, { pushes, push_factor: factor }));

        expect(plaque?.pushes).toBe(line);
        expect(plaque?.factor).toBe(doubled);
    });

    it("counts the pushes without a factor where the table does not double", () => {
        const plaque = ramschPlaque(ramsch(FELIX, { pushes: 2, push_factor: 1 }));

        expect(plaque).toMatchObject({ pushes: "2× geschoben", factor: null });
    });

    it("keeps the count through the play and names nobody then", () => {
        const plaque = ramschPlaque(ramsch(FELIX, { pushing: null, playing: PLAYING, pushes: 2, push_factor: 4 }));

        expect(plaque).toEqual({ pushes: "2× geschoben", factor: "×4", acting: null, waiting: false });
    });

    it("says only Ramsch where nothing was pushed and no stage runs", () => {
        const plaque = ramschPlaque(ramsch(FELIX, { pushing: null, playing: PLAYING }));

        expect(plaque).toEqual({ pushes: null, factor: null, acting: null, waiting: false });
    });

    it("waits for a player instead of naming who acts while a chair is open", () => {
        const plaque = ramschPlaque(ramsch(FELIX, { waiting_seat: NOVA, pushes: 1, push_factor: 2 }));

        expect(plaque).toEqual({ pushes: "1× geschoben", factor: "×2", acting: null, waiting: true });
    });
});

describe("the marks of a chair in a Ramsch", () => {
    it("puts the turn mark on the seat the stage waits for", () => {
        const table = ramsch(FELIX, { pushing: stage({ turn_seat: FELIX }) });

        expect(ramschMarks(table, FELIX)).toEqual({ ...QUIET, turn: true });
        expect(ramschMarks(table, ANNA)).toEqual(QUIET);
    });

    it("makes an agent on turn think and a person not", () => {
        expect(ramschMarks(ramsch(FELIX, { pushing: stage({ turn_seat: NOVA }) }), NOVA)).toEqual({
            ...QUIET,
            turn: true,
            thinks: true,
        });
        expect(ramschMarks(ramsch(FELIX, {}), ANNA).thinks).toBe(false);
    });

    it("puts the bubble on each seat that pushed and none on one that took", () => {
        const moves: Pushing["moves"] = [
            { seat: ANNA, action: "pushed" },
            { seat: FELIX, action: "took" },
        ];
        const table = ramsch(WATCHER, { pushing: stage({ turn_seat: NOVA, moves }) });

        expect(ramschMarks(table, ANNA).pushed).toBe(true);
        expect(ramschMarks(table, FELIX).pushed).toBe(false);
        expect(ramschMarks(table, NOVA).pushed).toBe(false);
    });

    it("leaves nobody on turn while a chair is open", () => {
        const table = ramsch(FELIX, { waiting_seat: NOVA, pushing: stage({ turn_seat: NOVA }) });

        expect(ramschMarks(table, NOVA)).toEqual(QUIET);
    });

    it("puts the turn mark on the seat on turn to play, with no bubble and no thinking", () => {
        const table = ramsch(FELIX, { pushing: null, playing: { ...PLAYING, turn_seat: NOVA } });

        expect(ramschMarks(table, NOVA)).toEqual({ ...QUIET, turn: true });
        expect(ramschMarks(table, ANNA)).toEqual(QUIET);
    });

    it("marks nothing outside a Ramsch or between its stage and its play", () => {
        expect(ramschMarks(ramsch(FELIX, { ramsch: false }), ANNA)).toEqual(QUIET);
        expect(ramschMarks(ramsch(FELIX, { pushing: null }), ANNA)).toEqual(QUIET);
        expect(ramschMarks({ ...ramsch(FELIX, {}), hand: null }, ANNA)).toEqual(QUIET);
    });
});

describe("the trick of a Ramsch", () => {
    it("is the play of a Ramsch and none of a stage or a declared game", () => {
        expect(ramschTrick(ramsch(FELIX, { pushing: null, playing: PLAYING }))).toBe(PLAYING);
        expect(ramschTrick(ramsch(FELIX, {}))).toBeNull();
        expect(ramschTrick(ramsch(FELIX, { ramsch: false, playing: PLAYING }))).toBeNull();
        expect(ramschTrick({ ...ramsch(FELIX, {}), hand: null })).toBeNull();
    });
});
