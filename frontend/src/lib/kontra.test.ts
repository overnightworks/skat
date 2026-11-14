import { describe, expect, it } from "vitest";
import { declinableWord, firstCardWait, keyWord, plaqueLine } from "#lib/kontra.ts";
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
        nudge: null,
        is_mine: seat === OPPONENT,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
    }));
}

function kontra(
    said: Kontra["said"],
    myWord: Word | null = null,
    firstCard: { waitsOn: number[]; declined: number[] } = { waitsOn: [], declined: [] },
): Kontra {
    return {
        said,
        factor: 2 ** said.length,
        my_word: myWord,
        first_card_waits_on: firstCard.waitsOn,
        first_card_declined: firstCard.declined,
    };
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
            taken: [
                { seat: 1, tricks: 0 },
                { seat: 2, tricks: 0 },
                { seat: 3, tricks: 0 },
            ],
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
        opened_by_me: false,
        hand: playingKontra === "no hand" ? null : hand,
        result: null,
        passed_in: null,
        series: null,
        aborted: null,
        ended: null,
        options: null,
        bock: null,
    };
}

const SAID_KONTRA = { seat: OPPONENT, word: "kontra" } as const;

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

describe("the first card waiting on a word", () => {
    const waiting = (waitsOn: number[], declined: number[] = [], myWord: Word | null = "kontra") =>
        table(5, kontra([], myWord, { waitsOn, declined }));

    it("is none while the first card waits on no one", () => {
        expect(firstCardWait(waiting([]))).toBeNull();
        expect(firstCardWait(table(5, null))).toBeNull();
    });

    it("names the viewer as you and another seat by its name, and marks the seats that said no", () => {
        const wait = firstCardWait(waiting([OPPONENT, AGENT], [DECLARER])) as NonNullable<
            ReturnType<typeof firstCardWait>
        >;

        expect(wait.text).toContain(words["kontra.you"]);
        expect(wait.text).toContain("Nova");
        expect(wait.initials).toEqual(["F", "N"]);
        expect([OPPONENT, AGENT, DECLARER].map((seat) => wait.owes(seat))).toEqual([true, true, false]);
        expect(wait.marks.get(DECLARER)).toBe("declined");
    });

    it("holds back the cards of the seat that leads", () => {
        const wait = firstCardWait(waiting([DECLARER])) as NonNullable<ReturnType<typeof firstCardWait>>;

        expect([OPPONENT, DECLARER, undefined].map((seat) => wait.held(seat))).toEqual([true, false, false]);
    });

    it.each([
        ["the viewer owes a word", waiting([OPPONENT]), "kontra"],
        ["another seat owes a word", waiting([DECLARER]), null],
        ["the first card waits on no one", waiting([]), null],
        ["the viewer's seat is awaited with no word open", waiting([OPPONENT], [], null), null],
    ])("offers the decline of a word when %s", (_name, value, expected) => {
        expect(declinableWord(value)).toBe(expected);
    });
});

describe("the plaque's line", () => {
    it.each([
        { said: ["kontra"], word: "kontra", factor: 2 },
        { said: ["kontra", "re"], word: "re", factor: 4 },
        { said: ["kontra", "re", "supra"], word: "supra", factor: 8 },
        { said: ["kontra", "re", "supra", "hirsch"], word: "hirsch", factor: 16 },
    ] as const)("names the last word $word with the table's factor $factor", ({ said, word, factor }) => {
        const line = plaqueLine({
            said: said.map((each) => ({ seat: OPPONENT, word: each })),
            factor,
            my_word: null,
            first_card_waits_on: [],
            first_card_declined: [],
        });

        expect(line).toEqual(words["kontra.plaque"]({ word: words[`kontra.${word}`], factor: String(factor) }));
    });

    it.each([
        ["a table without Kontra", null],
        ["a hand without a word", kontra([])],
    ])("is none for %s", (_name, value) => {
        expect(plaqueLine(value)).toBeNull();
    });
});
