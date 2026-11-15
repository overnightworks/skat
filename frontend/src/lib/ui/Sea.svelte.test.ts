// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { changeSetting } from "#lib/settings.svelte.ts";
import { armSound } from "#lib/tableSound.ts";
import { showTableStyle } from "#lib/tableStyle.svelte.ts";
import StyleScene from "#lib/ui/StyleScene.svelte";
import { stubAudioContext } from "../../testing/stubBrowser.ts";

describe("the sea under the table", () => {
    const { AudioContext, seaLevels } = stubAudioContext();
    let mounted: ReturnType<typeof mount> | undefined;

    // The page's sound is made at its first use and keeps the audio context it first meets, so one stand-in serves the file.
    // The device holds a record of the player's switches, which the settings read at that first use.
    beforeAll(() => {
        localStorage.setItem(
            "skat.settings",
            JSON.stringify({
                muted: false,
                replayMotion: false,
                voice: false,
                turnInBackground: false,
                vibration: false,
            }),
        );
        vi.stubGlobal("AudioContext", AudioContext);
        vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: vi.fn() }));
        armSound();
        window.dispatchEvent(new Event("pointerup"));
    });

    afterAll(() => {
        localStorage.clear();
        vi.unstubAllGlobals();
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        showTableStyle(null);
        changeSetting("muted", false);
    });

    const level = (): number | undefined => seaLevels.at(-1);

    function showScene(): void {
        mounted = mount(StyleScene, { target: document.body, props: { style: "strandbar" } });
        flushSync();
    }

    function hideWindow(hidden: boolean): void {
        Object.defineProperty(document, "hidden", { value: hidden, configurable: true });
        document.dispatchEvent(new Event("visibilitychange"));
        flushSync();
    }

    it("sounds under a table in the style Strandbar", () => {
        showScene();

        expect(level()).toBeGreaterThan(0);
    });

    it("follows the device's mute", () => {
        showScene();

        changeSetting("muted", true);
        flushSync();

        expect(level()).toBe(0);
    });

    it("fades while the window is hidden and returns when it is shown again", () => {
        showScene();
        const shown = level();

        hideWindow(true);
        const hidden = level();
        hideWindow(false);

        expect([hidden, level()]).toEqual([0, shown]);
    });

    it("is let go when the table's page goes", async () => {
        showScene();

        await unmount(mounted as ReturnType<typeof mount>);
        mounted = undefined;

        expect(level()).toBe(0);
    });
});
