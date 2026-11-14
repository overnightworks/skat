// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { runSea } from "#lib/tableSound.ts";
import { showTableStyle } from "#lib/tableStyle.svelte.ts";
import StyleKey from "#lib/ui/StyleKey.svelte";
import StyleScene from "#lib/ui/StyleScene.svelte";
import { TABLE_STYLE_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import { words } from "#lib/words.ts";

// The page's sound engine reads the browser's media queries at its first use; the sea's own tests are the engine's.
vi.mock("#lib/tableSound.ts", () => ({ runSea: vi.fn() }));

describe("the style key", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        showTableStyle(null);
        vi.unstubAllGlobals();
    });

    function show(): void {
        mounted = mount(StyleKey, { target: document.body, props: { id: TABLE_ID, note: "" } });
        flushSync();
    }

    const tile = (name: string): HTMLInputElement =>
        [...document.querySelectorAll<HTMLLabelElement>(".style-tile")]
            .find((label) => label.textContent.includes(name))
            ?.querySelector("input") as HTMLInputElement;

    it("offers both styles and marks the one the table has", () => {
        showTableStyle("strandbar");

        show();

        expect([tile(words["table.styleKlassik"]).checked, tile(words["table.styleStrandbar"]).checked]).toEqual([
            false,
            true,
        ]);
    });

    it("sends the other style to the table's style path and keeps the mark until the stream brings it", () => {
        const fetcher = vi.fn().mockResolvedValue(Response.json({}));
        vi.stubGlobal("fetch", fetcher);
        show();

        tile(words["table.styleStrandbar"]).click();

        const [path, init] = fetcher.mock.calls[0] as [string, RequestInit];
        expect([path, (JSON.parse(init.body as string) as { style: string }).style]).toEqual([
            `${TABLES_PATH}/${TABLE_ID}${TABLE_STYLE_SUFFIX}`,
            "strandbar",
        ]);
    });

    it("sends nothing for the style the table already has", () => {
        const fetcher = vi.fn();
        vi.stubGlobal("fetch", fetcher);
        showTableStyle("strandbar");
        show();

        tile(words["table.styleStrandbar"]).dispatchEvent(new Event("change", { bubbles: true }));

        expect(fetcher).not.toHaveBeenCalled();
    });

    it("says the style holds for everyone at the table", () => {
        show();

        expect(document.body.textContent).toContain(words["table.styleNote"]);
    });
});

describe("the scene behind the table", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        showTableStyle(null);
    });

    it.each([
        { style: "klassik" as const, beaches: 0 },
        { style: null, beaches: 0 },
        { style: "strandbar" as const, beaches: 2 },
    ])("draws $beaches beach frames for the style $style", ({ style, beaches }) => {
        mounted = mount(StyleScene, { target: document.body, props: { style } });
        flushSync();

        expect(document.querySelectorAll(".beach")).toHaveLength(beaches);
    });
});

describe("the sea under the table", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        showTableStyle(null);
        vi.mocked(runSea).mockClear();
    });

    it.each([
        { style: "strandbar" as const, wanted: true },
        { style: "klassik" as const, wanted: false },
    ])("is wanted by the table only in the style Strandbar: $style", ({ style, wanted }) => {
        mounted = mount(StyleScene, { target: document.body, props: { style } });
        flushSync();

        expect(vi.mocked(runSea).mock.calls.at(-1)).toEqual([wanted]);
    });

    it("is let go when the table's page goes", async () => {
        mounted = mount(StyleScene, { target: document.body, props: { style: "strandbar" } });
        flushSync();

        await unmount(mounted);
        mounted = undefined;

        expect(vi.mocked(runSea).mock.calls.at(-1)).toEqual([false]);
    });
});
