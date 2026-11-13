import { describe, expect, it } from "vitest";
import { keyWord, plaqueLine, stampBetween } from "#lib/kontra.ts";
import { words } from "#lib/words.ts";
import type { Chair, Hand, Kontra, Table, Word } from "../routes/(start)/tables.ts";

const OPPONENT = 1;
const DECLARER = 2;
const AGENT = 3;

const OCCUPANTS: [number, string, Chair["occupant_kind"]][] = [
    [OPPONENT, "Felix", "person"],
    [DECLARER, "Anna", "person"],
    [AGENT, "Nova", "agent"],
];

function chairs(): Chair[] {
    return OCCUPANTS.map(([seat, name, kind]) => ({
        seat,
        occupant_name: name,
        occupant_kind: kind,
        former_holder_name: null,
        is_mine_to_return: false,
        is_mine: seat === OPPONENT,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
    }));
}

function kontra(said: Kontra["said"], myWord: Word | null = null): Kontra {
    return { said, factor: 2 ** said.length, my_word: myWord };
}

function table(version: number, playingKontra: Kontra | null | "no hand"): Table {
    const hand: Hand = {
        dealer_seat: 3,
        own_cards: [],
        skat_count: 2,
        waiting_seat: null,
        abort: null,
        abortable: false,
        ramsch: false,
        pushing: null,
        pushes: 0,
        push_factor: 1,
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
        playing: {
            turn_seat: OPPONENT,
            current_trick: [],
            last_trick: null,
            legal_cards: [],
            running_points: null,
            give_up: null,
            kontra: playingKontra === "no hand" ? null : playingKontra,
        },
    };
    return {
        id: "a".repeat(32),
        version,
        chairs: chairs(),
        watchers: 0,
        hand: playingKontra === "no hand" ? null : hand,
        result: null,
        passed_in: null,
        aborted: null,
        ended: null,
        options: null,
        bock: null,
    };
}

const SAID_KONTRA = { seat: OPPONENT, word: "kontra" } as const;
const SAID_RE = { seat: DECLARER, word: "re" } as const;

describe("the key of a seat", () => {
    it.each([
        ["the word the seat may say", kontra([], "kontra"), "kontra"],
        ["no word when the seat has none open", kontra([SAID_KONTRA], null), null],
        ["no word at a table without Kontra", null, null],
        ["no word between hands", "no hand" as const, null],
    ])("is %s", (_name, playingKontra, expected) => {
        expect(keyWord(table(5, playingKontra))).toBe(expected);
    });
});

const STAMP_OF_FELIX = {
    text: words["kontra.stamp"]({ word: words["kontra.kontra"] }),
    label: words["kontra.saidBy"]({ name: "Felix", word: words["kontra.kontra"] }),
    initial: "F",
    agent: false,
};

describe("the stamp an update brings", () => {
    it("carries the word said between the two versions with its mark and the sayer's face", () => {
        const before = table(5, kontra([]));
        const after = table(6, kontra([SAID_KONTRA]));

        expect(stampBetween(before, after)).toEqual(STAMP_OF_FELIX);
    });

    it("is the stamp of the last of two words said at once", () => {
        const stamp = stampBetween(table(5, kontra([])), table(7, kontra([SAID_KONTRA, SAID_RE])));

        expect(stamp).toMatchObject({ text: words["kontra.stamp"]({ word: words["kontra.re"] }), initial: "A" });
    });

    it("is the stamp of a hand's first word, as the table before it had no hand", () => {
        expect(stampBetween(table(5, "no hand"), table(6, kontra([SAID_KONTRA])))).toEqual(STAMP_OF_FELIX);
    });

    it("shows an agent's word with the agent's mark", () => {
        const said = { seat: AGENT, word: "kontra" } as const;

        expect(stampBetween(table(5, kontra([])), table(6, kontra([said])))).toMatchObject({
            initial: "N",
            agent: true,
        });
    });

    it("has no initial for a chair that has since been left", () => {
        const left = table(6, kontra([SAID_KONTRA]));
        (left.chairs[0] as Chair).occupant_name = null;

        expect(stampBetween(table(5, kontra([])), left)?.initial).toBe("");
    });

    it.each([
        ["a page that has no table before it", undefined, table(6, kontra([SAID_KONTRA]))],
        ["a table that is not newer", table(6, kontra([])), table(6, kontra([SAID_KONTRA]))],
        ["the same words again", table(5, kontra([SAID_KONTRA])), table(6, kontra([SAID_KONTRA]))],
        ["words of another hand", table(5, kontra([SAID_KONTRA, SAID_RE])), table(6, kontra([]))],
        ["a table without Kontra", table(5, null), table(6, null)],
        ["a hand that has just ended", table(5, kontra([SAID_KONTRA])), table(6, "no hand")],
    ])("is none for %s", (_name, before, after) => {
        expect(stampBetween(before, after)).toBeNull();
    });
});

describe("the plaque's line", () => {
    it.each([
        { said: ["kontra"], word: "kontra", factor: 2 },
        { said: ["kontra", "re"], word: "re", factor: 4 },
        { said: ["kontra", "re", "supra"], word: "supra", factor: 8 },
        { said: ["kontra", "re", "supra", "hirsch"], word: "hirsch", factor: 16 },
    ] as const)("names the last word $word with the table's factor $factor", ({ said, word, factor }) => {
        const line = plaqueLine({ said: said.map((each) => ({ seat: OPPONENT, word: each })), factor, my_word: null });

        expect(line).toEqual({ word: words[`kontra.${word}`], factor: `×${String(factor)}` });
    });

    it.each([
        ["a table without Kontra", null],
        ["a hand without a word", kontra([])],
    ])("is none for %s", (_name, value) => {
        expect(plaqueLine(value)).toBeNull();
    });
});
