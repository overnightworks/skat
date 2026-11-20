// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AnswerClock from "#lib/ui/AnswerClock.svelte";
import { words } from "#lib/words.ts";

describe("the minute left to answer", () => {
    let mounted: ReturnType<typeof mount> | undefined;
    const NOW = Date.parse("2026-11-19T12:00:00Z");
    const UNTIL = "2026-11-19T12:00:42Z";

    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(NOW);
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        vi.useRealTimers();
    });

    function lineOf(ends: boolean): string | undefined {
        mounted = mount(AnswerClock, { target: document.body, props: { until: UNTIL, ends } });
        flushSync();
        return document.querySelector(".clockline span")?.textContent;
    }

    it("says that no answer counts as no", () => {
        expect(lineOf(false)).toBe(words["table.answerClock"]({ time: "0:42" }));
    });

    it("says that no answer ends the table when the silence does", () => {
        expect(lineOf(true)).toBe(words["table.answerClockEnds"]({ time: "0:42" }));
    });
});
