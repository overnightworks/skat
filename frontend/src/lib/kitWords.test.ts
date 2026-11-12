import { describe, expect, it } from "vitest";
import { accountMenuWords, agentControlWords } from "#lib/kitWords.ts";
import { words } from "#lib/words.ts";

describe("accountMenuWords", () => {
    it("gives the account menu every one of its words from the catalog", () => {
        expect(accountMenuWords).toEqual({
            theme: words["account.theme"],
            followSystem: words["account.followSystem"],
            light: words["account.light"],
            dark: words["account.dark"],
            logOut: words["account.logOut"],
        });
    });
});

describe("agentControlWords", () => {
    it("gives the agent control every one of its words, whole, from the catalog", () => {
        const { callLabel, askToLeaveLabel, ...plain } = agentControlWords;

        expect(plain).toEqual({
            call: words["agents.call"],
            calling: words["agents.calling"],
            askToLeave: words["agents.askToLeave"],
            empty: words["agents.empty"],
            refusals: {
                "not-allowed": words["agents.refusalNotAllowed"],
                "owner-absent": words["agents.refusalOwnerAbsent"],
                "place-full": words["agents.refusalPlaceFull"],
                "agent-unavailable": words["agents.refusalAgentUnavailable"],
                "try-again": words["agents.refusalTryAgain"],
            },
        });
        expect([typeof callLabel, typeof askToLeaveLabel]).toEqual(["function", "function"]);
    });

    it("names the agent in the accessible names of its two buttons", () => {
        expect(agentControlWords.callLabel("Nova")).toBe(words["agents.callLabel"]({ name: "Nova" }));
        expect(agentControlWords.askToLeaveLabel("Nova")).toBe(words["agents.askToLeaveLabel"]({ name: "Nova" }));
        expect(agentControlWords.callLabel("Nova")).toContain("Nova");
    });
});
