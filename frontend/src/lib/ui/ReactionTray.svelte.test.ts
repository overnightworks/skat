// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ReactionKey from "#lib/ui/ReactionKey.svelte";
import ReactionTray from "#lib/ui/ReactionTray.svelte";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { resetReactions } from "#lib/tableReactions.svelte.ts";
import { showTableStyle } from "#lib/tableStyle.svelte.ts";
import { TABLE_REACTION_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import { words } from "#lib/words.ts";
import { EMOTES, reactionMark, reactionName } from "../../routes/(start)/reaction.ts";

describe("what a person at the table taps to throw an emote", () => {
    let mounted: ReturnType<typeof mount>[] = [];
    const fetching = vi.fn();
    const PHONE_WIDTH = 390;
    const DESKTOP_WIDTH = 1280;
    const widthOfTheWindow = (width: number): void => {
        Object.defineProperty(window, "innerWidth", { value: width, configurable: true });
    };

    beforeEach(() => {
        fetching.mockReset().mockResolvedValue(new Response(null, { status: 204 }));
        vi.stubGlobal("fetch", fetching);
        widthOfTheWindow(PHONE_WIDTH);
    });

    afterEach(async () => {
        for (const each of mounted) await unmount(each);
        mounted = [];
        resetReactions();
        document.body.replaceChildren();
        showTableStyle(null);
        vi.unstubAllGlobals();
    });

    function show(): void {
        mounted = [
            mount(ReactionKey, { target: document.body }),
            mount(ReactionTray, { target: document.body, props: { id: TABLE_ID } }),
        ];
        flushSync();
    }

    const posted = (): [string, unknown][] =>
        fetching.mock.calls.map(([path, init]) => [
            path as string,
            JSON.parse((init as RequestInit).body as string) as unknown,
        ]);

    it("offers each emote as a button named in the catalog, which throws it and closes the tray", () => {
        show();
        const key = document.querySelector<HTMLButtonElement>(".reaction-key");
        key?.click();
        flushSync();
        const opened = document.querySelector(".tray")?.classList.contains("open");
        const buttons = [...document.querySelectorAll<HTMLButtonElement>(".tray button")];

        buttons[0]?.click();
        flushSync();

        expect([
            opened,
            buttons.map((button) => button.getAttribute("aria-label")),
            buttons.map((button) => button.textContent.trim()),
            document.querySelector(".tray")?.classList.contains("open"),
            posted(),
        ]).toEqual([
            true,
            EMOTES.map((reaction) => words[reactionName(reaction)]),
            EMOTES.map((reaction) => words[reactionMark(reaction) as "table.reactionClapMark"]),
            false,
            [[`${TABLES_PATH}/${TABLE_ID}${TABLE_REACTION_SUFFIX}`, { reaction: EMOTES[0] }]],
        ]);
    });

    it("has no key on a wide screen, where the tray always stands", () => {
        widthOfTheWindow(DESKTOP_WIDTH);

        show();

        expect([document.querySelector(".reaction-key"), document.querySelector(".tray") !== null]).toEqual([
            null,
            true,
        ]);
    });
});
