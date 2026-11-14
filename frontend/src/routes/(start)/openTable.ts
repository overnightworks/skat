// Opening a table: the request that opens it with a visibility and the rule sets a person saves to open it with.

import { RULE_SETS_PATH, TABLES_PATH, type VISIBILITY_TOKENS } from "#lib/wire.ts";
import {
    ask,
    CONFLICT_STATUS,
    fetchSigningInAgain,
    type Options,
    type OptionsRequest,
    type Outcome,
} from "./tables.ts";

export type Visibility = (typeof VISIBILITY_TOKENS)[number];
// A rule set the person saved: the options a table opens with when it is picked.
export type RuleSet = { id: string; name: string; options: Options };
// The person's own sets in the order the server answers them; a set that cannot be read is its own outcome.
export type RuleSetsOutcome = { kind: "sets"; sets: RuleSet[] } | { kind: "failed" };
// A name the person already holds with other options is refused and saves nothing.
export type SaveRuleSetOutcome = { kind: "saved"; set: RuleSet } | { kind: "taken" } | { kind: "failed" };

function isNameTaken(body: unknown): boolean {
    return typeof body === "object" && body !== null && "reason" in body && body.reason === "name-taken";
}

// The command id is the retry key: asking again with the same one, the same length, the same options and the same
// visibility returns the table the first ask opened. A table opened without options plays the official rules, and one
// opened without a visibility is open.
export function createTable(
    commandId: string,
    seriesLength: number,
    options?: OptionsRequest,
    visibility?: Visibility,
): Promise<Outcome> {
    return ask(TABLES_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command_id: commandId, series_length: seriesLength, options, visibility }),
    });
}

export async function readRuleSets(): Promise<RuleSetsOutcome> {
    const answer = await fetchSigningInAgain(RULE_SETS_PATH);
    if (!answer?.ok) return { kind: "failed" };
    try {
        const body = (await answer.json()) as { sets?: RuleSet[] };
        return Array.isArray(body.sets) ? { kind: "sets", sets: body.sets } : { kind: "failed" };
    } catch {
        return { kind: "failed" };
    }
}

// Saving a name the person holds with the same options answers that set again.
export async function saveRuleSet(name: string, options: OptionsRequest | undefined): Promise<SaveRuleSetOutcome> {
    const answer = await fetchSigningInAgain(RULE_SETS_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, options: options ?? {} }),
    });
    if (answer === null) return { kind: "failed" };
    try {
        const body: unknown = await answer.json();
        if (answer.ok) return { kind: "saved", set: body as RuleSet };
        return answer.status === CONFLICT_STATUS && isNameTaken(body) ? { kind: "taken" } : { kind: "failed" };
    } catch {
        return { kind: "failed" };
    }
}
