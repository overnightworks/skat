// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import KlassikDecor from "#lib/ui/KlassikDecor.svelte";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { showTableStyle } from "#lib/tableStyle.svelte.ts";
import { words } from "#lib/words.ts";

describe("what a person taps on the lamp of a Klassik table", () => {
    let mounted: ReturnType<typeof mount> | undefined;
    const fetching = vi.fn();

    beforeEach(() => {
        fetching.mockReset().mockResolvedValue(new Response(null, { status: 204 }));
        vi.stubGlobal("fetch", fetching);
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        showTableStyle(null);
        vi.unstubAllGlobals();
    });

    function show(): void {
        mounted = mount(KlassikDecor, { target: document.body, props: { id: TABLE_ID } });
        flushSync();
    }

    const posted = (): [string, unknown][] =>
        fetching.mock.calls.map(([path, init]) => [
            path as string,
            JSON.parse((init as RequestInit).body as string) as unknown,
        ]);

    it("makes the lamp of a Klassik table a button and leaves a Strandbar table without one", () => {
        showTableStyle("klassik");
        show();
        const lamp = document.querySelector<HTMLButtonElement>("button.decor.lamp");
        lamp?.click();
        const posts = posted().map(([, body]) => body);

        showTableStyle("strandbar");
        flushSync();

        expect([lamp?.getAttribute("aria-label"), posts, document.querySelector("button.decor.lamp")]).toEqual([
            words["table.objectLamp"],
            [{ reaction: "lamp" }],
            null,
        ]);
    });
});
