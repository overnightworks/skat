// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { NextSeriesLine } from "#lib/series.ts";
import NextSeriesLineView from "#lib/ui/NextSeriesLine.svelte";
import { words } from "#lib/words.ts";

describe("the line of the next series' settings", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
    });

    it("names the next series, its length and each rule that is on", () => {
        const line: NextSeriesLine = {
            length: words["table.seriesGames"](12),
            chips: [
                { id: "kontra", word: words["rules.chipKontra"], count: null },
                { id: "ramsch", word: words["rules.chipRamsch"], count: null },
            ],
        };
        mounted = mount(NextSeriesLineView, { target: document.body, props: { line } });
        flushSync();

        expect([
            document.querySelector(".lbl")?.textContent,
            Array.from(document.querySelectorAll(".chip")).map((chip) => chip.textContent.trim()),
        ]).toEqual([words["table.nextSeries"], [line.length, words["rules.chipKontra"], words["rules.chipRamsch"]]]);
    });

    it("offers „Ändern“ only to a caller that may change the settings, and tells it when tapped", () => {
        const line: NextSeriesLine = { length: words["table.seriesGames"](12), chips: [] };
        let changed = 0;
        mounted = mount(NextSeriesLineView, {
            target: document.body,
            props: {
                line,
                onchange: () => {
                    changed += 1;
                },
            },
        });
        flushSync();

        document.querySelector<HTMLButtonElement>("button.change")?.click();

        expect([document.querySelector("button.change")?.textContent.trim(), changed]).toEqual([
            words["table.nextSeriesChange"],
            1,
        ]);
    });

    it("draws no „Ändern“ for a watcher", () => {
        const line: NextSeriesLine = { length: words["table.seriesGames"](12), chips: [] };
        mounted = mount(NextSeriesLineView, { target: document.body, props: { line } });
        flushSync();

        expect(document.querySelector("button.change")).toBeNull();
    });

    it("marks the chip of the official rules", () => {
        const line: NextSeriesLine = {
            length: words["table.seriesGames"](12),
            chips: [{ id: "official", word: words["rules.chipOfficial"], count: null }],
        };
        mounted = mount(NextSeriesLineView, { target: document.body, props: { line } });
        flushSync();

        expect(document.querySelector(".chip.official")?.textContent.trim()).toBe(words["rules.chipOfficial"]);
    });
});
