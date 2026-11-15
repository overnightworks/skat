// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { showTableStyle } from "#lib/tableStyle.svelte.ts";
import StyleKey from "#lib/ui/StyleKey.svelte";
import StyleScene from "#lib/ui/StyleScene.svelte";
import { TABLE_STYLE_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import { words } from "#lib/words.ts";

describe("the style key", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        showTableStyle(null);
        vi.unstubAllGlobals();
    });

    // The note the key hands its parent, as a bound prop does.
    let note = "";

    function show(): void {
        note = "";
        mounted = mount(StyleKey, {
            target: document.body,
            props: {
                id: TABLE_ID,
                get note() {
                    return note;
                },
                set note(value: string) {
                    note = value;
                },
            },
        });
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

    it("sets the row's label over the two tiles", () => {
        show();

        const row = document.querySelector(".style-row") as HTMLElement;
        expect(row.firstElementChild?.textContent).toBe(words["table.style"]);
    });

    it("names the tiles' group after the row's visible label", () => {
        show();

        const group = document.querySelector<HTMLElement>("[role=radiogroup]") as HTMLElement;
        const label = document.getElementById(group.getAttribute("aria-labelledby") ?? "");
        expect([label?.textContent, group.hasAttribute("aria-label")]).toEqual([words["table.style"], false]);
    });

    it("sends the other style to the table's style path and keeps the mark until the stream brings it", async () => {
        const fetcher = vi.fn().mockResolvedValue(Response.json({}));
        vi.stubGlobal("fetch", fetcher);
        show();

        tile(words["table.styleStrandbar"]).click();
        await vi.waitFor(() => {
            expect(fetcher).toHaveBeenCalled();
        });
        await Promise.resolve();
        flushSync();

        const [path, init] = fetcher.mock.calls[0] as [string, RequestInit];
        expect([path, (JSON.parse(init.body as string) as { style: string }).style]).toEqual([
            `${TABLES_PATH}/${TABLE_ID}${TABLE_STYLE_SUFFIX}`,
            "strandbar",
        ]);
        expect(tile(words["table.styleStrandbar"]).checked).toBe(true);
    });

    it("gives the table's style back and says so when the request is refused", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({}, { status: 403 })));
        showTableStyle("klassik");
        show();

        tile(words["table.styleStrandbar"]).click();
        await vi.waitFor(() => {
            expect(note).toBe(words["table.commandFailed"]);
        });
        flushSync();

        expect([tile(words["table.styleKlassik"]).checked, tile(words["table.styleStrandbar"]).checked]).toEqual([
            true,
            false,
        ]);
    });

    it("says the style holds for everyone at the table", () => {
        show();

        expect(document.body.textContent).toContain(words["table.styleNote"]);
    });
});

describe("the scene behind the table", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    // The scene's sea starts the page's sound, which reads the device's media queries at its first use; jsdom has none.
    beforeEach(() => {
        vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: vi.fn() }));
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        showTableStyle(null);
        vi.unstubAllGlobals();
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
