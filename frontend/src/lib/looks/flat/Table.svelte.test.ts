// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { tableIntents } from "#lib/table/intents.ts";
import type { Reaction, TableStyle } from "#lib/table/scene.ts";
import { words } from "#lib/words.ts";
import { lookOf } from "../registry.ts";

describe("the furniture the flat table draws for each style", () => {
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
        vi.unstubAllGlobals();
    });

    function show(style: TableStyle, taps: Partial<Record<Reaction, number>>): HTMLButtonElement[] {
        const look = lookOf(style);
        mounted = mount(look.renderer, {
            target: document.body,
            props: { look, scene: { taps }, intents: tableIntents(TABLE_ID) },
        });
        flushSync();
        return [...document.querySelectorAll<HTMLButtonElement>("button.decor")];
    }

    const posted = (): unknown[] =>
        fetching.mock.calls.map(([, init]) => JSON.parse((init as RequestInit).body as string) as unknown);

    it.each([
        {
            style: "klassik" as const,
            taps: { lamp: 1 },
            drawn: [{ name: "table.objectLamp", object: "lamp", beat: "odd" }],
        },
        {
            style: "strandbar" as const,
            taps: { shell: 2 },
            drawn: [
                { name: "table.objectCocktail", object: "cocktail", beat: null },
                { name: "table.objectShell", object: "shell", beat: "even" },
            ],
        },
    ])("draws only the $style table's own objects, each throwing its own reaction", ({ style, taps, drawn }) => {
        const buttons = show(style, taps);

        for (const button of buttons) button.click();

        expect([
            buttons.map((button) => [button.getAttribute("aria-label"), button.dataset.beat ?? null]),
            posted(),
        ]).toEqual([
            drawn.map(({ name, beat }) => [words[name as keyof typeof words], beat]),
            drawn.map(({ object }) => ({ reaction: object })),
        ]);
    });
});
