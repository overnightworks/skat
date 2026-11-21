// @vitest-environment jsdom
import { mount, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { RamschView } from "#lib/result.ts";
import RamschResultCard from "#lib/ui/RamschResultCard.svelte";
import { words } from "#lib/words.ts";

function cardView(chips: string[]): RamschView {
    return {
        word: "Verloren",
        mark: "cross",
        lost: true,
        eyes: "86 Augen",
        chips,
        score: "−344",
        loss: true,
        counts: [],
        rows: [],
    };
}

describe("the Ramsch result card's factor chips", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
    });

    it("draws a check mark in front of every chip", () => {
        const chips = ["2× geschoben ×4", "Jungfrau ×2"];
        mounted = mount(RamschResultCard, { target: document.body, props: { view: cardView(chips) } });

        const drawn = [...document.querySelectorAll(".ladder > [role='listitem']")];
        expect(drawn.map((chip) => chip.textContent.trim())).toEqual(chips);
        expect(drawn.map((chip) => chip.querySelectorAll(":scope > svg").length)).toEqual([1, 1]);
    });

    it("marks a gone player's row", () => {
        const row = { initial: "x", gain: 0, gainText: "0", won: false };
        const view = {
            ...cardView([]),
            rows: [
                { ...row, seat: 0, name: "Ben", gone: true },
                { ...row, seat: 1, name: "Ana", gone: false },
                { ...row, seat: 2, name: "Cleo", gone: false },
            ],
        };
        mounted = mount(RamschResultCard, { target: document.body, props: { view } });

        const names = [...document.querySelectorAll(".reck .nm")];
        expect(names.map((name) => name.textContent.trim())).toEqual([
            `Ben${words["table.seriesGone"]}`,
            "Ana",
            "Cleo",
        ]);
    });
});
