// @vitest-environment jsdom
import { mount, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { RamschView } from "#lib/result.ts";
import RamschResultCard from "#lib/ui/RamschResultCard.svelte";

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
});
