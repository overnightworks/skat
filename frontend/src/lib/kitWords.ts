import type { AccountMenuWords, AgentControlWords } from "overnightworks-design";
import { words } from "#lib/words.ts";

export const accountMenuWords: AccountMenuWords = {
    theme: words["account.theme"],
    followSystem: words["account.followSystem"],
    light: words["account.light"],
    dark: words["account.dark"],
    logOut: words["account.logOut"],
};

export const agentControlWords: AgentControlWords = {
    call: words["agents.call"],
    calling: words["agents.calling"],
    askToLeave: words["agents.askToLeave"],
    callLabel: (name) => words["agents.callLabel"]({ name }),
    askToLeaveLabel: (name) => words["agents.askToLeaveLabel"]({ name }),
    empty: words["agents.empty"],
    refusals: {
        "not-allowed": words["agents.refusalNotAllowed"],
        "owner-absent": words["agents.refusalOwnerAbsent"],
        "place-full": words["agents.refusalPlaceFull"],
        "agent-unavailable": words["agents.refusalAgentUnavailable"],
        "try-again": words["agents.refusalTryAgain"],
    },
};
