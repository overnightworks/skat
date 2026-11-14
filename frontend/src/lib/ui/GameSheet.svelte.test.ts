// @vitest-environment jsdom
import { mount, unmount } from "svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GameRow } from "#lib/series.ts";
import { RAMSCH_SHEET, SCHIEBERAMSCH_SHEET } from "#lib/series.fixtures.ts";
import GameSheet from "#lib/ui/GameSheet.svelte";
import { words } from "#lib/words.ts";

const ROW: GameRow = {
    number: 5,
    name: "Cleo",
    subjectSeat: 3,
    initial: "C",
    line: null,
    value: "88",
    gain: "−88",
    lost: true,
    nullGame: false,
};

describe("the skat line of an opened Ramsch", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        vi.unstubAllGlobals();
    });

    async function opened(sheet: typeof RAMSCH_SHEET): Promise<HTMLElement[]> {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(sheet)));
        mounted = mount(GameSheet, { target: document.body, props: { id: "t", row: ROW, back: () => undefined } });
        await vi.waitFor(() => {
            expect(document.querySelector(".skatline")).not.toBeNull();
        });
        return [...document.querySelectorAll<HTMLElement>(".skatline .pair")];
    }

    const TAKER = words["table.sheetSkatTaker"]({ name: "Anna" });

    function shown(pair: HTMLElement | undefined): {
        label: string | null | undefined;
        cards: string | undefined;
        dot: boolean;
    } {
        return {
            label: pair?.querySelector("small")?.textContent,
            cards: pair?.querySelector(".mini .index")?.textContent,
            dot: pair?.querySelector(`[aria-label="${TAKER}"]`) != null,
        };
    }

    it("puts the dot of who got the skat beside the skat when it lay as dealt", async () => {
        const pairs = await opened(RAMSCH_SHEET);

        expect(shown(pairs[0])).toEqual({ label: words["table.sheetSkat"], cards: "10", dot: true });
        expect(pairs.slice(1).some((pair) => shown(pair).dot)).toBe(false);
    });

    it("puts the dot of who got the skat beside the skat as it lay at the end, not beside the skat as dealt", async () => {
        const pairs = await opened(SCHIEBERAMSCH_SHEET);

        const laid = pairs.find((pair) => shown(pair).label === words["table.sheetSkatLaid"]);
        expect(shown(pairs[0])).toEqual({ label: words["table.sheetSkat"], cards: "7", dot: false });
        expect(shown(laid)).toEqual({ label: words["table.sheetSkatLaid"], cards: "10", dot: true });
        expect(pairs.filter((pair) => shown(pair).dot)).toEqual([laid]);
    });
});
