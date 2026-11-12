// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";
import LobbyButton from "#lib/ui/LobbyButton.svelte";

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
        [0, "Lobby", null],
        [1, "Lobby, 1 Tisch wartet auf dich", "1"],
        [12, "Lobby, 12 Tische warten auf dich", "9+"],
    ])("names itself and marks the badge for %i waiting tables", (attention, name, badge) => {
        const link = show(attention);

        expect([link?.getAttribute("aria-label"), link?.querySelector(".lobby-badge")?.textContent ?? null]).toEqual([
            name,
            badge,
        ]);
    });
});
