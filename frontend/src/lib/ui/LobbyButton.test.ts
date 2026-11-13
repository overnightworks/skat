// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";
import { attentionMark } from "../../routes/(start)/tables.ts";
import LobbyButton from "#lib/ui/LobbyButton.svelte";
import { words } from "#lib/words.ts";

describe("the Lobby button", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
    });

    function show(attention: number) {
        mounted = mount(LobbyButton, { target: document.body, props: { attention } });
        flushSync();
        return document.querySelector("a.lobby");
    }

    it.each([
        [0, words["table.lobby"], null],
        [1, words["table.lobbyWaiting"](1), attentionMark(1)],
        [12, words["table.lobbyWaiting"](12), attentionMark(12)],
    ])("names itself and marks the badge for %i waiting tables", (attention, name, badge) => {
        const link = show(attention);

        expect([link?.getAttribute("aria-label"), link?.querySelector(".lobby-badge")?.textContent ?? null]).toEqual([
            name,
            badge,
        ]);
    });
});
