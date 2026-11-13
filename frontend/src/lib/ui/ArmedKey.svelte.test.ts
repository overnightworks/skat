// @vitest-environment jsdom
import { createRawSnippet, flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ArmedKey from "#lib/ui/ArmedKey.svelte";

const IDLE = "Idle word";
const ARMED = "Armed word";
const ICON = createRawSnippet(() => ({ render: () => '<svg class="mark"></svg>' }));

describe("the armed key", () => {
    let mounted: ReturnType<typeof mount> | undefined;
    let confirmed = 0;
    const props = $state<{ arms: boolean; disarmOnOtherTap: boolean; disabled: boolean }>({
        arms: true,
        disarmOnOtherTap: true,
        disabled: false,
    });

    beforeEach(() => {
        vi.useFakeTimers();
        confirmed = 0;
        Object.assign(props, { arms: true, disarmOnOtherTap: true, disabled: false });
        mounted = mount(ArmedKey, {
            target: document.body,
            props: {
                class: "copy probe",
                idle: IDLE,
                armedWord: ARMED,
                icon: ICON,
                onconfirm: () => {
                    confirmed += 1;
                },
                get arms() {
                    return props.arms;
                },
                get disarmOnOtherTap() {
                    return props.disarmOnOtherTap;
                },
                get disabled() {
                    return props.disabled;
                },
            },
        });
        flushSync();
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        vi.useRealTimers();
    });

    const key = (): HTMLButtonElement => document.querySelector("button.probe") as HTMLButtonElement;
    const isArmed = (): boolean => key().classList.contains("arm");

    function tap(): void {
        key().click();
        flushSync();
    }

    function tapElsewhere(): void {
        document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
        flushSync();
    }

    it("shows its idle word and its icon until it is tapped", () => {
        expect([
            key().title,
            key().querySelector(".label")?.textContent,
            key().querySelector(".mark") !== null,
        ]).toEqual([IDLE, IDLE, true]);
        expect([isArmed(), key().querySelector(".run-out")]).toEqual([false, null]);
    });

    it("arms on the first tap with its armed word and a line that runs out, and confirms on the second", () => {
        tap();
        const armed = [confirmed, key().title, isArmed(), key().querySelector(".run-out") !== null];
        tap();

        expect(armed).toEqual([0, ARMED, true, true]);
        expect([confirmed, key().title, isArmed(), key().querySelector(".run-out")]).toEqual([1, IDLE, false, null]);
    });

    it("falls back after three seconds and not before", () => {
        tap();

        vi.advanceTimersByTime(2999);
        flushSync();
        const before = isArmed();
        vi.advanceTimersByTime(1);
        flushSync();

        expect([before, isArmed(), confirmed]).toEqual([true, false, 0]);
    });

    it("counts its three seconds from the last arming", () => {
        tap();
        vi.advanceTimersByTime(3000);
        flushSync();
        tap();
        vi.advanceTimersByTime(2999);
        flushSync();

        expect(isArmed()).toBe(true);
    });

    it("falls back at a press anywhere else but stays armed at a press on itself", () => {
        tap();
        key().dispatchEvent(new Event("pointerdown", { bubbles: true }));
        flushSync();
        const onItself = isArmed();
        tapElsewhere();

        expect([onItself, isArmed()]).toEqual([true, false]);
    });

    it("keeps its arming at a press elsewhere when it is told only the time disarms it", () => {
        props.disarmOnOtherTap = false;
        flushSync();

        tap();
        tapElsewhere();

        expect(isArmed()).toBe(true);
    });

    it("confirms on the first tap when it does not arm", () => {
        props.arms = false;
        flushSync();

        tap();

        expect([confirmed, isArmed()]).toEqual([1, false]);
    });

    it("cannot be tapped while it is disabled", () => {
        props.disabled = true;
        flushSync();

        expect(key().disabled).toBe(true);
    });

    it("keeps its arming while nothing it watches changes", () => {
        tap();

        props.arms = true;
        flushSync();

        expect(isArmed()).toBe(true);
    });
});
