import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ACCOUNT_PATH } from "#lib/wire.ts";
import { words } from "#lib/words.ts";

function answerWith(body: BodyInit | null, status = 200) {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status })));
}

// The name is module state, so each test reads a module of its own.
async function freshAccount() {
    vi.resetModules();
    return import("#lib/ui/account.svelte.ts");
}

describe("readAccount", () => {
    const reload = vi.fn();

    beforeEach(() => {
        reload.mockClear();
        vi.stubGlobal("location", { reload });
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("names the menu with the account's name, asking the account path", async () => {
        const { menuName, readAccount } = await freshAccount();
        answerWith(JSON.stringify({ name: "anna" }));

        await readAccount();

        expect(menuName()).toBe("anna");
        expect(fetch).toHaveBeenCalledWith(ACCOUNT_PATH);
    });

    it.each([
        ["an answer without a name", JSON.stringify({}), 200],
        ["a refusal other than a missing session", null, 500],
    ])("leaves the menu unnamed after %s", async (_case, body, status) => {
        const { menuName, readAccount } = await freshAccount();
        answerWith(body, status);

        await readAccount();

        expect(menuName()).toBe(words.account);
    });

    it("leaves the menu unnamed when the account cannot be reached", async () => {
        const { menuName, readAccount } = await freshAccount();
        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

        await readAccount();

        expect(menuName()).toBe(words.account);
    });

    it("goes through the sign-in again when the session has ended", async () => {
        const { readAccount } = await freshAccount();
        answerWith(null, 401);

        await readAccount();

        expect(reload).toHaveBeenCalledOnce();
    });
});
