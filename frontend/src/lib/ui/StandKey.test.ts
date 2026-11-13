// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StandKey from "#lib/ui/StandKey.svelte";
import { words } from "#lib/words.ts";

describe("the stand-up key", () => {
    let mounted: ReturnType<typeof mount> | undefined;
    let stood = 0;

    beforeEach(() => {
        vi.useFakeTimers();
        stood = 0;
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        vi.useRealTimers();
    });

    function show(handRuns: boolean): HTMLButtonElement {
        mounted = mount(StandKey, {
            target: document.body,
            props: {
                handRuns,
                onstand: () => {
                    stood += 1;
                },
            },
        });
        flushSync();
        return document.querySelector("button.stand") as HTMLButtonElement;
    }

    function tap(key: HTMLButtonElement): void {
        key.click();
        flushSync();
    }

    it("stands up with one tap between hands and keeps its word without being round", () => {
        const key = show(false);

        tap(key);

        expect([stood, key.title, key.classList.contains("round")]).toEqual([1, words["table.standUp"], false]);
    });

    it("is round and names itself Aufstehen while a hand runs", () => {
        const key = show(true);

        expect([key.classList.contains("round"), key.title, key.querySelector(".label")?.textContent]).toEqual([
            true,
            words["table.standUp"],
            words["table.standUp"],
        ]);
    });

    it("arms on the first tap during a hand, asks again and runs its line out, and stands up on the second", () => {
        const key = show(true);

        tap(key);
        const armed = [stood, key.title, key.classList.contains("arm"), key.querySelector(".drain") !== null];
        tap(key);

        expect(armed).toEqual([0, words["table.standUpArmed"], true, true]);
        expect([stood, key.title, key.classList.contains("arm")]).toEqual([1, words["table.standUp"], false]);
    });

    it("falls back after three seconds so the next tap arms again", () => {
        const key = show(true);

        tap(key);
        vi.advanceTimersByTime(3000);
        flushSync();
        const fallen = [key.title, key.classList.contains("arm")];
        tap(key);

        expect(fallen).toEqual([words["table.standUp"], false]);
        expect([stood, key.classList.contains("arm")]).toEqual([0, true]);
    });

    it("falls back at a tap anywhere else but stays armed at a tap on itself", () => {
        const key = show(true);

        tap(key);
        key.dispatchEvent(new Event("pointerdown", { bubbles: true }));
        flushSync();
        const onItself = key.classList.contains("arm");
        document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
        flushSync();

        expect([onItself, key.classList.contains("arm")]).toEqual([true, false]);
    });
});
