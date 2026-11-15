// @vitest-environment jsdom
import { flushSync, mount, unmount, type Component } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import KlassikDecor from "#lib/ui/KlassikDecor.svelte";
import StrandDecor from "#lib/ui/StrandDecor.svelte";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { showTableStyle } from "#lib/tableStyle.svelte.ts";
import { words } from "#lib/words.ts";

describe("what a person at the table taps on the table's objects", () => {
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

    function show(component: Component<{ id: string }>): void {
        mounted = mount(component, { target: document.body, props: { id: TABLE_ID } });
        flushSync();
    }

    const posted = (): [string, unknown][] =>
        fetching.mock.calls.map(([path, init]) => [
            path as string,
            JSON.parse((init as RequestInit).body as string) as unknown,
        ]);

    it("makes the cocktail and the shell of a Strandbar table buttons that throw their own reaction", () => {
        showTableStyle("strandbar");
        show(StrandDecor);
        const buttons = [...document.querySelectorAll<HTMLButtonElement>("button.decor")];

        for (const button of buttons) button.click();

        expect([buttons.map((button) => button.getAttribute("aria-label")), posted().map(([, body]) => body)]).toEqual([
            [words["table.objectCocktail"], words["table.objectShell"]],
            [{ reaction: "cocktail" }, { reaction: "shell" }],
        ]);
    });

    it("makes the lamp of a Klassik table a button and leaves a Strandbar table without one", () => {
        showTableStyle("klassik");
        show(KlassikDecor);
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
