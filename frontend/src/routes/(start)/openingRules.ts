import { tableRules, type ChipId, type RuleId } from "#lib/tableRules.ts";
import { BOCK_TRIGGER_TOKENS, RULE_SET_NAME_MAX, SWITCH_ON_OPTIONS } from "#lib/wire.ts";
import { listFormat, words } from "#lib/words.ts";
import type { Options, OptionsRequest } from "./tables.ts";

// The sheet's rules are the options a table is opened with, a rule that is off null; a picked set is a sheet.
export type RuleRow = RuleId;
type Trigger = (typeof BOCK_TRIGGER_TOKENS)[number];

export const OFFICIAL: Options = { show_running_points: false, kontra: null, bock: null, ramsch: null };

// The values a rule starts with where the picked set does not hold it, from the one owner in Python.
const START: { [Rule in "kontra" | "bock" | "ramsch"]: NonNullable<Options[Rule]> } = {
    kontra: SWITCH_ON_OPTIONS.kontra,
    bock: { ...SWITCH_ON_OPTIONS.bock, triggers: [...SWITCH_ON_OPTIONS.bock.triggers] },
    ramsch: SWITCH_ON_OPTIONS.ramsch,
};
// Schieberamsch is a switch of its own beneath Ramsch, so a Ramsch starts without it.
const START_RAMSCH: NonNullable<Options["ramsch"]> = { ...START.ramsch, pushing: null };

export function isOn(sheet: Options, row: RuleRow): boolean {
    switch (row) {
        case "points":
            return sheet.show_running_points;
        case "pushing":
            return (sheet.ramsch?.pushing ?? null) !== null;
        default:
            return sheet[row] !== null;
    }
}

// A change to a rule that is on; a sheet where it is off stays as it is.
function amend<Rule extends "kontra" | "bock" | "ramsch">(
    sheet: Options,
    rule: Rule,
    change: (held: NonNullable<Options[Rule]>) => Options[Rule],
): Options {
    const held = sheet[rule];
    return held === null ? sheet : { ...sheet, [rule]: change(held) };
}

function amendPushing(
    sheet: Options,
    change: (held: NonNullable<NonNullable<Options["ramsch"]>["pushing"]>) => NonNullable<Options["ramsch"]>["pushing"],
): Options {
    return amend(sheet, "ramsch", (ramsch) => ({
        ...ramsch,
        pushing: ramsch.pushing === null ? null : change(ramsch.pushing),
    }));
}

// Switching a rule on starts it with the values of the picked set where the set holds it, with the start values else.
export function switchRule(sheet: Options, row: RuleRow, on: boolean, picked: Options): Options {
    switch (row) {
        case "points":
            return { ...sheet, show_running_points: on };
        case "kontra":
            return { ...sheet, kontra: on ? (picked.kontra ?? START.kontra) : null };
        case "bock":
            return { ...sheet, bock: on ? (picked.bock ?? START.bock) : null };
        case "ramsch":
            return { ...sheet, ramsch: on ? (picked.ramsch ?? START_RAMSCH) : null };
        case "pushing":
            return amend(sheet, "ramsch", (ramsch) => ({
                ...ramsch,
                pushing: on ? (picked.ramsch?.pushing ?? START.ramsch.pushing) : null,
            }));
    }
}

// One answer of a question: `apply` is the sheet with this answer picked.
type Pill = { token: string; word: string; apply: (sheet: Options) => Options };
// One short question of a rule with the answers it offers, in the order the scene draws them.
export type Question = {
    id: string;
    rule: RuleRow;
    text: string;
    pills: readonly Pill[];
    // The token picked on the sheet; null while the rule is off.
    picked: (sheet: Options) => string | null;
};

function question<Answer extends string>(spec: {
    id: string;
    rule: RuleRow;
    text: string;
    pills: readonly (readonly [Answer, string])[];
    read: (sheet: Options) => Answer | null;
    write: (sheet: Options, answer: Answer) => Options;
}): Question {
    return {
        id: spec.id,
        rule: spec.rule,
        text: spec.text,
        pills: spec.pills.map(([token, word]) => ({ token, word, apply: (sheet) => spec.write(sheet, token) })),
        picked: spec.read,
    };
}

const kontraQuestion = <Field extends "sayer" | "reach">(
    field: Field,
    text: string,
    pills: readonly (readonly [NonNullable<Options["kontra"]>[Field], string])[],
) =>
    question({
        id: `kontra${field === "sayer" ? "Sayer" : "Reach"}`,
        rule: "kontra",
        text,
        pills,
        read: (sheet) => sheet.kontra?.[field] ?? null,
        write: (sheet, answer) => amend(sheet, "kontra", (kontra) => ({ ...kontra, [field]: answer })),
    });

const ramschQuestion = <Field extends "scoring" | "jungfrau" | "durchmarsch">(
    field: Field,
    text: string,
    pills: readonly (readonly [NonNullable<Options["ramsch"]>[Field], string])[],
) =>
    question({
        id: `ramsch${field.charAt(0).toUpperCase()}${field.slice(1)}`,
        rule: "ramsch",
        text,
        pills,
        read: (sheet) => sheet.ramsch?.[field] ?? null,
        write: (sheet, answer) => amend(sheet, "ramsch", (ramsch) => ({ ...ramsch, [field]: answer })),
    });

const pushingQuestion = <Field extends "rule" | "grand_hand">(
    field: Field,
    id: string,
    text: string,
    pills: readonly (readonly [NonNullable<NonNullable<Options["ramsch"]>["pushing"]>[Field], string])[],
) =>
    question({
        id,
        rule: "pushing",
        text,
        pills,
        read: (sheet) => sheet.ramsch?.pushing?.[field] ?? null,
        write: (sheet, answer) => amendPushing(sheet, (pushing) => ({ ...pushing, [field]: answer })),
    });

export const QUESTIONS: readonly Question[] = [
    kontraQuestion("sayer", words["start.askKontraSayer"], [
        ["any-opponent", words["start.pillAnyOpponent"]],
        ["bidders-only", words["start.pillBiddersOnly"]],
    ]),
    kontraQuestion("reach", words["start.askKontraReach"], [
        ["kontra-re", words["start.pillKontraRe"]],
        ["kontra-re-standings", words["start.pillKontraReStandings"]],
        ["up-to-hirsch", words["start.pillUpToHirsch"]],
    ]),
    ramschQuestion("scoring", words["start.askRamschScoring"], [
        ["points", words["start.pillScoringPoints"]],
        ["points-by-ten", words["start.pillScoringPointsByTen"]],
        ["skat-to-loser", words["start.pillScoringSkatToLoser"]],
    ]),
    ramschQuestion("jungfrau", words["start.askJungfrau"], [
        ["doubles-loser", words["start.pillJungfrauDoublesLoser"]],
        ["off", words["start.pillJungfrauOff"]],
    ]),
    ramschQuestion("durchmarsch", words["start.askDurchmarsch"], [
        ["wins-120", words["start.pillDurchmarschWins120"]],
        ["wins-120-flat", words["start.pillDurchmarschWins120Flat"]],
        ["off", words["start.pillDurchmarschOff"]],
    ]),
    pushingQuestion("rule", "pushingRule", words["start.askPushingRule"], [
        ["jacks-stay", words["start.pillPushingJacksStay"]],
        ["jacks-may-go", words["start.pillPushingJacksMayGo"]],
        ["no-doubling", words["start.pillPushingNoDoubling"]],
    ]),
    pushingQuestion("grand_hand", "pushingGrandHand", words["start.askGrandHand"], [
        ["off", words["start.pillGrandHandOff"]],
        ["allowed", words["start.pillGrandHandAllowed"]],
    ]),
    question({
        id: "bockOverlap",
        rule: "bock",
        text: words["start.askBockOverlap"],
        pills: [
            ["append", words["start.pillOverlapAppend"]],
            ["multiply", words["start.pillOverlapMultiply"]],
            ["ignore", words["start.pillOverlapIgnore"]],
        ],
        read: (sheet) => sheet.bock?.overlap ?? null,
        write: (sheet, overlap) => amend(sheet, "bock", (bock) => ({ ...bock, overlap })),
    }),
];

// The triggers the page draws a switch for; one the picked set holds beyond them stays as it is and has no switch.
export const TRIGGER_SWITCHES: readonly { token: Trigger; word: string }[] = [
    { token: "sixty-sixty", word: words["start.flagSixtySixty"] },
    { token: "won-grand-hand", word: words["start.flagWonGrandHand"] },
    { token: "lost-after-kontra", word: words["start.flagLostAfterKontra"] },
    { token: "re", word: words["start.flagRe"] },
    { token: "passed-in", word: words["start.flagPassedIn"] },
    { token: "schneider", word: words["start.flagSchneider"] },
];

export function triggerOn(sheet: Options, trigger: Trigger): boolean {
    return sheet.bock?.triggers.includes(trigger) ?? false;
}

// The API needs one trigger at least, so Bock goes off with its last one.
export function toggleTrigger(sheet: Options, trigger: Trigger): Options {
    return amend(sheet, "bock", (bock) => {
        const triggers = BOCK_TRIGGER_TOKENS.filter((each) => bock.triggers.includes(each) !== (each === trigger));
        return triggers.length === 0 ? null : { ...bock, triggers };
    });
}

// Nothing when the sheet equals the official rules: a table opened without options plays them.
export function requestOf(sheet: Options): OptionsRequest | undefined {
    const request: OptionsRequest = {
        ...(sheet.show_running_points ? { show_running_points: true as const } : {}),
        ...(sheet.kontra === null ? {} : { kontra: sheet.kontra }),
        ...(sheet.bock === null ? {} : { bock: sheet.bock }),
        ...(sheet.ramsch === null ? {} : { ramsch: sheet.ramsch }),
    };
    return Object.keys(request).length === 0 ? undefined : request;
}

// Two sheets differ when a table opened with one plays other rules than a table opened with the other.
export function differs(sheet: Options, picked: Options): boolean {
    return JSON.stringify(requestOf(sheet)) !== JSON.stringify(requestOf(picked));
}

function held(options: Options, rule: Exclude<ChipId, "official">): unknown {
    return rule === "points" ? options.show_running_points : options[rule];
}

// The picked set's name with the rules that are on and changed after it; a sheet that only switched rules off is
// the set adjusted. Schieberamsch is part of Ramsch. A name the API refuses for its length gives way to the adjusted
// form, and that to the set's own name cut to the limit.
export function suggestedName(setName: string, sheet: Options, picked: Options): string {
    const changed = tableRules(sheet, null).chips.flatMap((chip) =>
        chip.id !== "official" && JSON.stringify(held(sheet, chip.id)) !== JSON.stringify(held(picked, chip.id))
            ? [chip.word]
            : [],
    );
    const adjusted = words["start.savedNameAdjusted"]({ set: setName });
    const candidates =
        changed.length === 0
            ? [adjusted]
            : [words["start.savedNameWith"]({ set: setName, rules: listFormat.format(changed) }), adjusted];
    return candidates.find(fits) ?? Array.from(setName).slice(0, RULE_SET_NAME_MAX).join("");
}

function fits(name: string): boolean {
    return Array.from(name).length <= RULE_SET_NAME_MAX;
}
