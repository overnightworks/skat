import type { AccountMenuWords, AgentControlWords } from "overnightworks-design";
import { words } from "#lib/words.ts";

export const accountMenuWords: AccountMenuWords = {
    theme: words["account.theme"],
    followSystem: words["account.followSystem"],
    light: words["account.light"],
    dark: words["account.dark"],
    logOut: words["account.logOut"],
};

// The catalog's sentences hold their gap as `{name}`; the kit's labels are functions of the name.
export const fillName = (sentence: string, name: string): string => sentence.replace("{name}", name);

export const agentControlWords: AgentControlWords = {
    call: words["agents.call"],
    calling: words["agents.calling"],
    askToLeave: words["agents.askToLeave"],
    callLabel: (name) => fillName(words["agents.callLabel"], name),
    askToLeaveLabel: (name) => fillName(words["agents.askToLeaveLabel"], name),
    empty: words["agents.empty"],
    refusals: {
        "not-allowed": words["agents.refusalNotAllowed"],
        "owner-absent": words["agents.refusalOwnerAbsent"],
        "place-full": words["agents.refusalPlaceFull"],
        "agent-unavailable": words["agents.refusalAgentUnavailable"],
        "try-again": words["agents.refusalTryAgain"],
    },
};
