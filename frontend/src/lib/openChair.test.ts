import { describe, expect, it } from "vitest";
import { handWaits, lockedChairs, seatNotice, sitQuestionLine, standTap } from "#lib/openChair.ts";
import { words } from "#lib/words.ts";
import { declarerStage, type Chair, type Hand, type Table } from "../routes/(start)/tables.ts";

const OPEN_SEAT = 3;

function chairOf(seat: number, name: string | null, kind: Chair["occupant_kind"], former: string | null = null): Chair {
    return {
        seat,
        occupant_name: name,
        occupant_kind: name === null ? null : kind,
        is_mine: false,
        is_away: false,
        ready: false,
        total: null,
        hand: { position: "forehand", card_count: 10 },
        former_holder_name: former,
        is_mine_to_return: false,
    };
}

function handOf(waitingSeat: number | null): Hand {
    return {
        dealer_seat: 1,
        own_cards: [],
        skat_count: 2,
        waiting_seat: waitingSeat,
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
        playing: null,
    };
}

function tableOf(hand: Hand | null, ...chairs: Chair[]): Table {
    return {
        id: "a".repeat(32),
        version: 1,
        chairs,
        watchers: 0,
        hand,
        result: null,
        passed_in: null,
        bock: null,
        ended: null,
    };
}

const felix = chairOf(1, "Felix", "person");
const anna = chairOf(2, "Anna", "person");
const novaThere = chairOf(OPEN_SEAT, "Nova", "agent");
const openAfterNova = chairOf(OPEN_SEAT, null, null, "Nova");

describe("a hand that waits", () => {
    it.each([
        ["a hand with an open seat", handOf(OPEN_SEAT), true],
        ["a hand with every chair taken", handOf(null), false],
        ["no hand", null, false],
        ["no table yet", undefined, false],
    ])("%s: waits is %s", (_case, hand, waits) => {
        expect(handWaits(hand)).toBe(waits);
    });
});

describe("the line under the question before a sit", () => {
    it.each([
        ["Nova", "Du übernimmst Novas Karten."],
        ["Anna", "Du übernimmst Annas Karten."],
        ["Felix", "Du übernimmst Felix’ Karten."],
        ["Hans", "Du übernimmst Hans’ Karten."],
        ["Max", "Du übernimmst Max’ Karten."],
        ["Franz", "Du übernimmst Franz’ Karten."],
        ["Fritz", "Du übernimmst Fritz’ Karten."],
        ["Strauß", "Du übernimmst Strauß’ Karten."],
        ["Alice", "Du übernimmst Alice’ Karten."],
        ["Alex", "Du übernimmst Alex’ Karten."],
        ["FELIX", "Du übernimmst FELIX’ Karten."],
        ["Carlos", "Du übernimmst Carlos’ Karten."],
        ["Lena", "Du übernimmst Lenas Karten."],
    ])("names %s: %s", (name, line) => {
        expect(sitQuestionLine(name)).toBe(line);
    });

    it("names no one for a chair freed before its holder was written down", () => {
        expect(sitQuestionLine(null)).toBe("Du übernimmst die Karten dieses Platzes.");
    });
});

describe("the notice to the others about a chair of the running hand", () => {
    it("says an agent left when its chair opens in the running hand", () => {
        const before = tableOf(handOf(null), felix, anna, novaThere);
        const after = tableOf(handOf(OPEN_SEAT), felix, anna, openAfterNova);

        expect(seatNotice(before, after)).toEqual({ text: words["table.agentLeft"]({ name: "Nova" }), initial: null });
    });

    it("says a person stood up when their chair opens in the running hand", () => {
        const before = tableOf(handOf(null), felix, anna, chairOf(OPEN_SEAT, "Lena", "person"));
        const after = tableOf(handOf(OPEN_SEAT), felix, anna, chairOf(OPEN_SEAT, null, null, "Lena"));

        expect(seatNotice(before, after)).toEqual({
            text: words["table.standUpNotice"]({ name: "Lena" }),
            initial: "L",
        });
    });

    it("says nothing to the person who stood up herself", () => {
        const before = tableOf(handOf(null), felix, anna, { ...chairOf(OPEN_SEAT, "Lena", "person"), is_mine: true });
        const after = tableOf(handOf(OPEN_SEAT), felix, anna, chairOf(OPEN_SEAT, null, null, "Lena"));

        expect(seatNotice(before, after)).toBeNull();
    });

    it("says nothing when a person stands up between hands", () => {
        const before = tableOf(null, felix, anna, chairOf(OPEN_SEAT, "Lena", "person"));
        const after = tableOf(null, felix, anna, chairOf(OPEN_SEAT, null, null));

        expect(seatNotice(before, after)).toBeNull();
    });

    it("says nothing when an agent leaves between hands", () => {
        const before = tableOf(null, felix, anna, novaThere);
        const after = tableOf(null, felix, anna, chairOf(OPEN_SEAT, null, null));

        expect(seatNotice(before, after)).toBeNull();
    });

    it("says nothing while the chair stays open", () => {
        const before = tableOf(handOf(OPEN_SEAT), felix, anna, openAfterNova);

        expect(seatNotice(before, tableOf(handOf(OPEN_SEAT), felix, anna, openAfterNova))).toBeNull();
    });

    it.each([
        ["a person", chairOf(OPEN_SEAT, "Lena", "person"), "L"],
        ["an agent", chairOf(OPEN_SEAT, "Nova", "agent"), null],
    ])("says %s plays on when they take the open chair", (_who, taker, initial) => {
        const before = tableOf(handOf(OPEN_SEAT), felix, anna, openAfterNova);
        const after = tableOf(handOf(null), felix, anna, taker);

        expect(seatNotice(before, after)).toEqual({
            text: words["table.playsOn"]({ name: taker.occupant_name as string }),
            initial,
        });
    });

    it("says nothing to the person who took the open chair herself", () => {
        const before = tableOf(handOf(OPEN_SEAT), felix, anna, openAfterNova);
        const after = tableOf(handOf(null), felix, anna, { ...chairOf(OPEN_SEAT, "Lena", "person"), is_mine: true });

        expect(seatNotice(before, after)).toBeNull();
    });

    it("says nothing about a chair taken between hands, which the agent notice owns", () => {
        const before = tableOf(null, felix, anna, chairOf(OPEN_SEAT, null, null));
        const after = tableOf(null, felix, anna, novaThere);

        expect(seatNotice(before, after)).toBeNull();
    });
});

describe("the declarer's step", () => {
    const declaring = (waitingSeat: number | null): Table => ({
        ...tableOf({
            ...handOf(waitingSeat),
            declaring: { declarer_seat: 1, stage: "choosing", declaration: null, open_cards: [] },
        }),
        chairs: [{ ...felix, is_mine: true }, anna],
    });

    it("is the stage the declarer must act on while every chair is taken", () => {
        expect(declarerStage(declaring(null))).toBe("choosing");
    });

    it("is none while the hand waits for a sitter", () => {
        expect(declarerStage(declaring(OPEN_SEAT))).toBeNull();
    });
});

describe("the tap on the stand-up key", () => {
    it.each([
        ["a running hand, not armed", true, false, "arm"],
        ["a running hand, armed", true, true, "stand"],
        ["between hands, not armed", false, false, "stand"],
        ["between hands, armed", false, true, "stand"],
    ])("%s: the tap is %s", (_case, handRuns, armed, tap) => {
        expect(standTap(handRuns, armed)).toBe(tap);
    });
});

describe("the open chairs a stood-up person may not take", () => {
    const own = { ...chairOf(OPEN_SEAT, null, null, "Felix"), is_mine_to_return: true };
    const other = chairOf(2, null, null, "Nova");

    it("are every open chair but the one to return to", () => {
        expect(lockedChairs(tableOf(handOf(2), felix, other, own))).toEqual(new Set([2]));
    });

    it("are none for a watcher who held no chair of the hand", () => {
        expect(lockedChairs(tableOf(handOf(2), felix, other, chairOf(OPEN_SEAT, null, null)))).toEqual(new Set());
    });

    it("are every open chair once the chair to return to is taken", () => {
        const taken = { ...chairOf(OPEN_SEAT, "Lena", "person"), is_mine_to_return: true };

        expect(lockedChairs(tableOf(handOf(2), felix, other, taken))).toEqual(new Set([2]));
    });
});
