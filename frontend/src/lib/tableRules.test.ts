import { describe, expect, it } from "vitest";
import {
    BOCK_OVERLAP_TOKENS,
    BOCK_TRIGGER_TOKENS,
    DURCHMARSCH_TOKENS,
    GRAND_HAND_TOKENS,
    JUNGFRAU_TOKENS,
    KONTRA_DEADLINE_TOKENS,
    KONTRA_REACH_TOKENS,
    KONTRA_SAYER_TOKENS,
    PUSHING_RULE_TOKENS,
    RAMSCH_SCORING_TOKENS,
} from "#lib/wire.ts";
import { tableRules } from "#lib/tableRules.ts";
import type { Options } from "../routes/(start)/tables.ts";

const NOTHING: Options = { show_running_points: false, kontra: null, bock: null, ramsch: null };
const KONTRA: NonNullable<Options["kontra"]> = {
    sayer: "bidders-only",
    reach: "up-to-hirsch",
    deadline: "own-card",
};
const RAMSCH: NonNullable<Options["ramsch"]> = {
    scoring: "points",
    jungfrau: "doubles-loser",
    durchmarsch: "wins-120",
    pushing: null,
};
const BOCK: NonNullable<Options["bock"]> = { triggers: ["sixty-sixty"], overlap: "append" };

// Every rule on, with the settings the frozen picture draws.
const EVERYTHING: Options = {
    show_running_points: true,
    kontra: KONTRA,
    ramsch: { ...RAMSCH, pushing: { rule: "jacks-stay", grand_hand: "off" } },
    bock: { triggers: ["sixty-sixty", "schneider", "schwarz"], overlap: "append" },
};

const chipWords = (options: Options): string[] => tableRules(options).chips.map((chip) => chip.word);
const settingsOf = (options: Options, id: string): string[] =>
    tableRules(options).rows.find((row) => row.id === id)?.settings ?? [];

function settingsPerToken<Token extends string>(
    tokens: readonly Token[],
    build: (token: Token) => Options,
): string[][] {
    return tokens.map((token) => tableRules(build(token)).rows.flatMap((row) => row.settings));
}

const kontra = (patch: Partial<typeof KONTRA>): Options => ({ ...NOTHING, kontra: { ...KONTRA, ...patch } });
const ramsch = (patch: Partial<typeof RAMSCH>): Options => ({ ...NOTHING, ramsch: { ...RAMSCH, ...patch } });
const pushing = (patch: Partial<NonNullable<typeof RAMSCH.pushing>>): Options =>
    ramsch({ pushing: { rule: "jacks-stay", grand_hand: "off", ...patch } });

describe("the chips", () => {
    it("is the one chip Offiziell, with no rows, for a table without a rule on", () => {
        expect(chipWords(NOTHING)).toEqual(["Offiziell"]);
        expect(tableRules(NOTHING).rows).toEqual([]);
    });

    it("lists each rule that is on in the order Augen, Kontra, Ramsch, Bock", () => {
        expect(chipWords(EVERYTHING)).toEqual(["Augen", "Kontra", "Ramsch", "Bock"]);
        expect(chipWords({ ...NOTHING, bock: BOCK, show_running_points: true })).toEqual(["Augen", "Bock"]);
    });

    it("gives Schieberamsch a row and no chip", () => {
        const withPushing = pushing({ rule: "no-doubling" });

        expect(chipWords(withPushing)).toEqual(["Ramsch"]);
        expect(tableRules(withPushing).rows.map((row) => row.name)).toEqual(["Ramsch beim Einpassen", "Schieberamsch"]);
    });
});

describe("the rows", () => {
    it("read the words of the frozen picture for the operator's rules", () => {
        const rows = tableRules(EVERYTHING).rows;

        expect(rows.map((row) => [row.name, row.settings])).toEqual([
            ["Laufende Augen zeigen", ["Aus fertigen Stichen, nie in einer Null"]],
            ["Kontra und Re", ["Nur wer gereizt hat", "bis Hirsch", "bis zur eigenen Karte"]],
            ["Ramsch beim Einpassen", ["Meiste Augen minus", "Jungfrau ×2", "Durchmarsch +120"]],
            ["Schieberamsch", ["Ohne Buben, je doppelt"]],
            ["Bockrunden", ["Bei 60 zu 60, Schneider und Schwarz", "neue Runden hängen sich an"]],
        ]);
    });

    it("adds the Grand Hand to Schieberamsch only when it is allowed", () => {
        expect(settingsOf(pushing({ grand_hand: "allowed" }), "pushing")).toEqual([
            "Ohne Buben, je doppelt",
            "Grand Hand statt Ramsch",
        ]);
        expect(settingsOf(pushing({ grand_hand: "off" }), "pushing")).toEqual(["Ohne Buben, je doppelt"]);
    });

    it("lists Bock's triggers in the order the answer gives them", () => {
        const triggers = ["schwarz", "sixty-sixty"] as const;

        expect(settingsOf({ ...NOTHING, bock: { triggers: [...triggers], overlap: "append" } }, "bock")[0]).toBe(
            "Bei Schwarz und 60 zu 60",
        );
    });
});

describe("the words of the options", () => {
    it.each([
        ["Kontra's sayer", settingsPerToken(KONTRA_SAYER_TOKENS, (sayer) => kontra({ sayer }))],
        ["Kontra's reach", settingsPerToken(KONTRA_REACH_TOKENS, (reach) => kontra({ reach }))],
        ["Kontra's deadline", settingsPerToken(KONTRA_DEADLINE_TOKENS, (deadline) => kontra({ deadline }))],
        ["Ramsch's scoring", settingsPerToken(RAMSCH_SCORING_TOKENS, (scoring) => ramsch({ scoring }))],
        ["Ramsch's Jungfrau", settingsPerToken(JUNGFRAU_TOKENS, (jungfrau) => ramsch({ jungfrau }))],
        ["Ramsch's Durchmarsch", settingsPerToken(DURCHMARSCH_TOKENS, (durchmarsch) => ramsch({ durchmarsch }))],
        ["the pushing rule", settingsPerToken(PUSHING_RULE_TOKENS, (rule) => pushing({ rule }))],
        ["the Grand Hand", settingsPerToken(GRAND_HAND_TOKENS, (grand_hand) => pushing({ grand_hand }))],
        [
            "Bock's triggers",
            settingsPerToken(BOCK_TRIGGER_TOKENS, (trigger) => ({
                ...NOTHING,
                bock: { ...BOCK, triggers: [trigger] },
            })),
        ],
        [
            "Bock's overlap",
            settingsPerToken(BOCK_OVERLAP_TOKENS, (overlap) => ({ ...NOTHING, bock: { ...BOCK, overlap } })),
        ],
    ])("%s has a text for every token, each its own", (_setting, perToken) => {
        expect(perToken.flat().every((text) => typeof text === "string" && text !== "")).toBe(true);
        expect(new Set(perToken.map((texts) => texts.join("|"))).size).toBe(perToken.length);
    });
});
