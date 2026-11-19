// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";
import StopKey from "#lib/ui/StopKey.svelte";
import { words } from "#lib/words.ts";

describe("the „Aufhören“ key", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
    });

    function show(sent: boolean, ontap: () => void): HTMLButtonElement {
        mounted = mount(StopKey, { target: document.body, props: { sent, ontap } });
        flushSync();
        return document.querySelector("button") as HTMLButtonElement;
    }

    it("says Aufhören and tells the page once when it is tapped", () => {
        let taps = 0;
        const key = show(false, () => {
            taps += 1;
        });

        key.click();

        expect([key.textContent.trim(), taps]).toEqual([words["table.stopPlaying"], 1]);
    });

    it("stays disabled while its tap is under way", () => {
        let taps = 0;
        const key = show(true, () => {
            taps += 1;
        });

        key.click();

        expect([key.disabled, taps]).toEqual([true, 0]);
    });
});
