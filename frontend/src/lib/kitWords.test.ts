import { describe, expect, it } from "vitest";
import { accountMenuWords } from "#lib/kitWords.ts";
import { words } from "#lib/words.ts";

describe("accountMenuWords", () => {
    it("gives the account menu every one of its words from the catalog", () => {
        expect(accountMenuWords).toEqual({
            theme: words.themeTitle,
            followSystem: words.themeFollowSystem,
            light: words.themeLight,
            dark: words.themeDark,
            logOut: words.logOut,
        });
    });
});
