import { describe, expect, it } from "vitest";
import { RULE_SET_NAME_MAX, SWITCH_ON_OPTIONS } from "#lib/wire.ts";
import {
    OFFICIAL,
    QUESTIONS,
    TRIGGER_SWITCHES,
    differs,
    isOn,
    requestOf,
    suggestedName,
    switchRule,
    toggleTrigger,
    triggerOn,
    type Question,
    type RuleRow,
} from "./openingRules.ts";
import type { Options } from "./tables.ts";

type Ramsch = NonNullable<Options["ramsch"]>;

const ROWS: readonly RuleRow[] = ["points", "kontra", "ramsch", "pushing", "bock"];

// Every rule on with values that differ from the start values in each variant.
const OTHER_PUSHING = { rule: "no-doubling", grand_hand: "allowed" } as const;
const OTHER: Options = {
    show_running_points: true,
    kontra: { sayer: "any-opponent", reach: "kontra-re-standings", deadline: "own-card" },
    ramsch: {
        occasion: "passed-in",
        scoring: "skat-to-loser",
        jungfrau: "off",
        durchmarsch: "wins-120-flat",
        pushing: OTHER_PUSHING,
    },
    bock: { triggers: ["re", "schneider", "schwarz"], overlap: "multiply" },
};
const RAMSCH_ALONE: Options = { ...OFFICIAL, ramsch: { ...(OTHER.ramsch as Ramsch), pushing: null } };
const POINTS_ONLY: Options = { ...OFFICIAL, show_running_points: true };
const KONTRA_ONLY: Options = { ...OFFICIAL, kontra: OTHER.kontra };

// The sheet of a set holds its rules and the variants as the set answers them.
const SETS: [string, Options, Record<RuleRow, boolean>][] = [
    ["a set holding no rule", OFFICIAL, { points: false, kontra: false, ramsch: false, pushing: false, bock: false }],
    [
        "a set holding the points only",
        POINTS_ONLY,
        { points: true, kontra: false, ramsch: false, pushing: false, bock: false },
    ],
    [
        "a set holding Kontra only",
        KONTRA_ONLY,
        { points: false, kontra: true, ramsch: false, pushing: false, bock: false },
    ],
    [
        "a set holding Ramsch without Schieberamsch",
        RAMSCH_ALONE,
        { points: false, kontra: false, ramsch: true, pushing: false, bock: false },
    ],
    ["a set holding every rule", OTHER, { points: true, kontra: true, ramsch: true, pushing: true, bock: true }],
];

const START = SWITCH_ON_OPTIONS;
const startSheet: Options = { ...START, bock: { ...START.bock, triggers: [...START.bock.triggers] } };

describe("the official rules", () => {
    it("have every rule off and open with no options", () => {
        expect(ROWS.map((row) => isOn(OFFICIAL, row))).toEqual([false, false, false, false, false]);
        expect(requestOf(OFFICIAL)).toBeUndefined();
    });

    it("open with exactly the running points when only they are switched on", () => {
        expect(requestOf(switchRule(OFFICIAL, "points", true, OFFICIAL))).toEqual({ show_running_points: true });
    });
});

describe.each(SETS)("a picked %s", (_name, options, on) => {
    it("has its rules on exactly where the set holds them", () => {
        expect(Object.fromEntries(ROWS.map((row) => [row, isOn(options, row)]))).toEqual(on);
    });
});

describe("a set picked and left unchanged", () => {
    it.each([
        ["a set holding no rule", OFFICIAL, undefined],
        ["a set holding the points only", POINTS_ONLY, { show_running_points: true }],
        ["a set holding Kontra only", KONTRA_ONLY, { kontra: OTHER.kontra }],
        ["a set holding every rule", OTHER, OTHER],
    ])("opens with the options of %s as it answers them", (_name, options, request) => {
        expect(requestOf(options)).toEqual(request);
    });

    it("leaves the running points out of the request while they are off", () => {
        expect(requestOf(startSheet)).toEqual({ kontra: START.kontra, bock: START.bock, ramsch: START.ramsch });
        expect(requestOf(startSheet)).not.toHaveProperty("show_running_points");
    });
});

describe("switching a rule on", () => {
    // What the sheet holds for a rule, and the start values of that rule.
    const held: Record<RuleRow, (sheet: Options) => unknown> = {
        points: (sheet) => sheet.show_running_points,
        kontra: (sheet) => sheet.kontra,
        bock: (sheet) => sheet.bock,
        ramsch: (sheet) => sheet.ramsch,
        pushing: (sheet) => sheet.ramsch?.pushing,
    };
    const started: Record<RuleRow, unknown> = {
        points: true,
        kontra: START.kontra,
        bock: START.bock,
        ramsch: { ...START.ramsch, pushing: null },
        pushing: START.ramsch.pushing,
    };
    // A set holding every rule but this one.
    const without = (row: RuleRow): Options => {
        if (row === "points") return { ...OTHER, show_running_points: false };
        if (row === "pushing") return RAMSCH_ALONE;
        return { ...OTHER, [row]: null };
    };
    // The sheet this rule is switched on in: Schieberamsch needs a Ramsch beneath it.
    const sheetOf = (row: RuleRow): Options => (row === "pushing" ? RAMSCH_ALONE : OFFICIAL);

    it.each(ROWS)("starts %s with the start values on the official rules", (row) => {
        expect(held[row](switchRule(sheetOf(row), row, true, OFFICIAL))).toEqual(started[row]);
    });

    it.each(ROWS)("starts %s with the start values on a set without it", (row) => {
        expect(held[row](switchRule(sheetOf(row), row, true, without(row)))).toEqual(started[row]);
    });

    it.each([
        ["kontra", OTHER.kontra],
        ["bock", OTHER.bock],
        ["ramsch", OTHER.ramsch],
        ["pushing", OTHER_PUSHING],
    ] as [RuleRow, unknown][])(
        "starts %s with the values of the set holding it, Grand Hand included",
        (row, values) => {
            expect(held[row](switchRule(sheetOf(row), row, true, OTHER))).toEqual(values);
        },
    );

    it("leaves the sheet as it is for Schieberamsch while Ramsch is off", () => {
        expect(switchRule(OFFICIAL, "pushing", true, OTHER)).toEqual(OFFICIAL);
    });

    it("does not change the sheet it started from", () => {
        const before = structuredClone(OFFICIAL);

        switchRule(OFFICIAL, "bock", true, OFFICIAL);

        expect(OFFICIAL).toEqual(before);
    });
});

describe("switching a rule off", () => {
    it.each([
        ["points", {}],
        ["kontra", { kontra: OTHER.kontra }],
        ["bock", { bock: OTHER.bock }],
        ["ramsch", { ramsch: OTHER.ramsch }],
    ] as [RuleRow, Partial<Options>][])("leaves %s out of the request", (row) => {
        const request = requestOf(switchRule(OTHER, row, false, OTHER));

        expect(request).not.toHaveProperty(row === "points" ? "show_running_points" : row);
    });

    it("takes Schieberamsch with Ramsch", () => {
        const sheet = switchRule(OTHER, "ramsch", false, OTHER);

        expect(isOn(sheet, "pushing")).toBe(false);
        expect(requestOf(sheet)).not.toHaveProperty("ramsch");
    });

    it("keeps the Ramsch when only Schieberamsch goes", () => {
        const sheet = switchRule(OTHER, "pushing", false, OTHER);

        expect(requestOf(sheet)?.ramsch?.pushing).toBeNull();
        expect(requestOf(sheet)?.ramsch?.scoring).toBe("skat-to-loser");
    });

    it("starts a rule switched on again afresh by the picked set", () => {
        const changed = pill("kontraSayer", 1).apply(OTHER);
        const again = switchRule(switchRule(changed, "kontra", false, OTHER), "kontra", true, OTHER);

        expect(again.kontra).toEqual(OTHER.kontra);
    });
});

function question(id: string): Question {
    const found = QUESTIONS.find((each) => each.id === id);
    if (found === undefined) throw new Error(`no question ${id}`);
    return found;
}

function pill(id: string, index: number) {
    const found = question(id).pills[index];
    if (found === undefined) throw new Error(`no pill ${String(index)} of ${id}`);
    return found;
}

// Where the request carries each question's answer.
const ANSWERS: Record<string, (request: NonNullable<ReturnType<typeof requestOf>>) => string | undefined> = {
    kontraSayer: (request) => request.kontra?.sayer,
    kontraReach: (request) => request.kontra?.reach,
    ramschScoring: (request) => request.ramsch?.scoring,
    ramschJungfrau: (request) => request.ramsch?.jungfrau,
    ramschDurchmarsch: (request) => request.ramsch?.durchmarsch,
    pushingRule: (request) => request.ramsch?.pushing?.rule,
    pushingGrandHand: (request) => request.ramsch?.pushing?.grand_hand,
    bockOverlap: (request) => request.bock?.overlap,
};

describe("the questions of the rules", () => {
    const everyPill = QUESTIONS.flatMap((each) =>
        each.pills.map((pill, index) => [each.id, pill.token, index] as const),
    );

    it("are the eight the scenes draw", () => {
        expect(QUESTIONS.map((each) => each.id)).toEqual(Object.keys(ANSWERS));
    });

    it.each(everyPill)("%s sends %s when its pill is picked", (id, token, index) => {
        const sheet = pill(id, index).apply(OTHER);

        expect(question(id).picked(sheet)).toBe(token);
        expect(ANSWERS[id]?.(requestOf(sheet) ?? {})).toBe(token);
    });

    it("leave the other answers of the sheet as they were", () => {
        const sheet = pill("kontraReach", 0).apply(OTHER);

        expect(sheet).toEqual({ ...OTHER, kontra: { ...OTHER.kontra, reach: "kontra-re" } });
    });

    it.each(QUESTIONS.map((each) => [each.id] as const))(
        "%s has no answer and changes nothing on the official rules",
        (id) => {
            expect(question(id).picked(OFFICIAL)).toBeNull();
            expect(pill(id, 0).apply(OFFICIAL)).toBe(OFFICIAL);
        },
    );

    it.each(QUESTIONS.filter((each) => each.rule === "pushing").map((each) => [each.id] as const))(
        "%s has no answer and changes nothing while Schieberamsch is off",
        (id) => {
            expect(question(id).picked(RAMSCH_ALONE)).toBeNull();
            expect(pill(id, 0).apply(RAMSCH_ALONE)).toEqual(RAMSCH_ALONE);
        },
    );
});

describe("the triggers of the Bock rounds", () => {
    it("are the six the scenes draw", () => {
        expect(TRIGGER_SWITCHES.map((each) => each.token)).toEqual([
            "sixty-sixty",
            "won-grand-hand",
            "lost-after-kontra",
            "re",
            "passed-in",
            "schneider",
        ]);
    });

    it.each(TRIGGER_SWITCHES.map((each) => [each.token] as const))("%s is added and dropped by its switch", (token) => {
        const base = switchRule(OFFICIAL, "bock", true, OFFICIAL);
        const held = (START.bock.triggers as readonly string[]).includes(token);

        const flipped = toggleTrigger(base, token);

        expect(triggerOn(flipped, token)).toBe(!held);
        expect(triggerOn(toggleTrigger(flipped, token), token)).toBe(held);
    });

    it("keep the order of the answer whichever switch came first", () => {
        const sheet = toggleTrigger(
            toggleTrigger(switchRule(OFFICIAL, "bock", true, OFFICIAL), "schneider"),
            "passed-in",
        );

        expect(sheet.bock?.triggers).toEqual([
            "sixty-sixty",
            "won-grand-hand",
            "lost-after-kontra",
            "re",
            "passed-in",
            "schneider",
        ]);
    });

    it("keep a trigger the page draws no switch for, as the set holds it", () => {
        const sheet = toggleTrigger(OTHER, "re");

        expect(requestOf(sheet)?.bock?.triggers).toEqual(["schneider", "schwarz"]);
    });

    it("switch Bock off when the last trigger goes", () => {
        const only = { ...OFFICIAL, bock: { triggers: ["re"], overlap: "append" } } as Options;

        const sheet = toggleTrigger(only, "re");

        expect(isOn(sheet, "bock")).toBe(false);
        expect(requestOf(sheet)).toBeUndefined();
    });

    it("answer off while Bock is off", () => {
        expect(triggerOn(OFFICIAL, "re")).toBe(false);
        expect(toggleTrigger(OFFICIAL, "re")).toBe(OFFICIAL);
    });
});

describe("a sheet that differs from the picked set", () => {
    const changeSayer = (sheet: Options): Options =>
        QUESTIONS.find((each) => each.id === "kontraSayer")
            ?.pills.find((each) => each.token === "bidders-only")
            ?.apply(sheet) ?? sheet;

    it.each([
        ["as it was picked", OTHER, OTHER, false],
        ["with a rule switched on", OFFICIAL, switchRule(OFFICIAL, "kontra", true, OFFICIAL), true],
        ["with a rule switched off", OTHER, switchRule(OTHER, "points", false, OTHER), true],
        ["with a variant of a rule changed", OTHER, changeSayer(OTHER), true],
        [
            "with a rule switched on and off again",
            OFFICIAL,
            switchRule(switchRule(OFFICIAL, "bock", true, OFFICIAL), "bock", false, OFFICIAL),
            false,
        ],
        ["with a variant changed and changed back", OTHER, toggleTrigger(toggleTrigger(OTHER, "re"), "re"), false],
    ] as [string, Options, Options, boolean][])("is told %s", (_name, picked, sheet, expected) => {
        expect(differs(sheet, picked)).toBe(expected);
    });
});

describe("the name suggested for a sheet", () => {
    it.each([
        [
            "the rules switched on",
            "Offiziell",
            OFFICIAL,
            { ...OFFICIAL, kontra: OTHER.kontra, ramsch: OTHER.ramsch },
            "Offiziell, mit Kontra und Ramsch",
        ],
        ["one rule switched on", "Offiziell", OFFICIAL, POINTS_ONLY, "Offiziell, mit Augen"],
        [
            "four rules switched on",
            "Alt",
            OFFICIAL,
            { ...OTHER, ramsch: RAMSCH_ALONE.ramsch },
            "Alt, mit Augen, Kontra, Ramsch und Bock",
        ],
        [
            "a variant of a rule that is on in both changed",
            "Felix",
            OTHER,
            toggleTrigger(OTHER, "schneider"),
            "Felix, mit Bock",
        ],
        [
            "a variant of Schieberamsch changed",
            "Felix",
            OTHER,
            { ...OTHER, ramsch: { ...(OTHER.ramsch as Ramsch), pushing: { ...OTHER_PUSHING, grand_hand: "off" } } },
            "Felix, mit Ramsch",
        ],
        ["only rules switched off", "Felix", OTHER, KONTRA_ONLY, "Felix, angepasst"],
        ["a rule switched on and another off", "Felix", KONTRA_ONLY, POINTS_ONLY, "Felix, mit Augen"],
    ] as [string, string, Options, Options, string][])("reads with %s", (_name, set, picked, sheet, expected) => {
        expect(suggestedName(set, sheet, picked)).toBe(expected);
    });

    it("gives way to the adjusted form when the rules would exceed the name limit", () => {
        const sheet = { ...OTHER, ramsch: RAMSCH_ALONE.ramsch };
        const name = suggestedName("Offiziell", sheet, OFFICIAL);
        expect(name).toBe("Offiziell, angepasst");
        expect(Array.from(name).length).toBeLessThanOrEqual(RULE_SET_NAME_MAX);
    });

    it("gives way to the set's own name cut to the limit when that exceeds it too", () => {
        const setName = "x".repeat(RULE_SET_NAME_MAX + 5);
        expect(suggestedName(setName, POINTS_ONLY, OFFICIAL)).toBe("x".repeat(RULE_SET_NAME_MAX));
    });
});
