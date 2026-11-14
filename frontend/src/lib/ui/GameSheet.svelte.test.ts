// @vitest-environment jsdom
import { mount, unmount } from "svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GameRow } from "#lib/series.ts";
import { RAMSCH_SHEET, SCHIEBERAMSCH_SHEET } from "#lib/series.fixtures.ts";
import GameSheet from "#lib/ui/GameSheet.svelte";
import { words } from "#lib/words.ts";
import { readGameSheet } from "../../routes/(start)/tables.ts";

vi.mock("../../routes/(start)/tables.ts", () => ({ readGameSheet: vi.fn() }));

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
    });

    async function opened(sheet: typeof RAMSCH_SHEET): Promise<HTMLElement[]> {
        vi.mocked(readGameSheet).mockResolvedValue(sheet);
        mounted = mount(GameSheet, { target: document.body, props: { id: "t", row: ROW, back: () => undefined } });
        await vi.waitFor(() => {
            expect(document.querySelector(".skatline")).not.toBeNull();
        });
        return [...document.querySelectorAll<HTMLElement>(".skatline .pair")];
    }

    const TAKER = words["table.sheetSkatTaker"]({ name: "Anna" });

    it("puts the dot of who got the skat beside the skat when it lay as dealt", async () => {
        const pairs = await opened(RAMSCH_SHEET);

        const withTaker = pairs.filter((pair) => pair.querySelector(`[aria-label="${TAKER}"]`) !== null);
        expect(withTaker.map((pair) => pair.querySelector("small")?.textContent)).toEqual([words["table.sheetSkat"]]);
    });

    it("puts the dot of who got the skat beside the skat as it lay at the end, not beside the skat as dealt", async () => {
        const pairs = await opened(SCHIEBERAMSCH_SHEET);

        const withTaker = pairs.filter((pair) => pair.querySelector(`[aria-label="${TAKER}"]`) !== null);
        expect(withTaker.map((pair) => pair.querySelector("small")?.textContent)).toEqual([
            words["table.sheetSkatLaid"],
        ]);
    });
});
