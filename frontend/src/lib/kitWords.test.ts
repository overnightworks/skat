import { describe, expect, it } from "vitest";
import { accountMenuWords } from "#lib/kitWords.ts";
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
