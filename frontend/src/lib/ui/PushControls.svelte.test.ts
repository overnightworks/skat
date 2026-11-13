// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FOREHAND, table } from "#lib/pushView.fixtures.ts";
import PushControls from "#lib/ui/PushControls.svelte";
import { words } from "#lib/words.ts";

const ARMED_FOR = 3000;

describe("the armed key of the Grand Hand", () => {
    let mounted: ReturnType<typeof mount> | undefined;
    const props = $state({ table: table(FOREHAND, "choosing", {}, "allowed") });

    beforeEach(() => {
        vi.useFakeTimers();
        props.table = table(FOREHAND, "choosing", {}, "allowed");
        mounted = mount(PushControls, {
            target: document.body,
            props: {
                id: "a".repeat(32),
                note: "",
                get table() {
                    return props.table;
                },
            },
        });
        flushSync();
    });

    afterEach(async () => {
        vi.useRealTimers();
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
    });

    const key = (): HTMLButtonElement => document.querySelector("button.grand") as HTMLButtonElement;

    const tapKey = (): void => {
        key().click();
        flushSync();
    };

    it("is armed by the first tap and says what the second tap does", () => {
        expect(key().textContent).toContain(words["push.grandHand"]);

        tapKey();

        expect([key().classList.contains("armed"), key().textContent]).toEqual([
            true,
            expect.stringContaining(words["push.grandHandAsk"]) as unknown,
        ]);
    });

    it("disarms by itself once the time is up and not before", () => {
        tapKey();

        vi.advanceTimersByTime(ARMED_FOR - 1);
        flushSync();
        expect(key().classList.contains("armed")).toBe(true);

        vi.advanceTimersByTime(1);
        flushSync();
        expect(key().classList.contains("armed")).toBe(false);
        expect(key().textContent).toContain(words["push.grandHand"]);
    });

    it("disarms on a tap anywhere but the key", () => {
        tapKey();

        document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
        flushSync();

        expect(key().classList.contains("armed")).toBe(false);
    });

    it("is not armed when the table offers the key again after it was withdrawn", () => {
        tapKey();

        props.table = table(FOREHAND, "choosing", {}, "off");
        flushSync();
        expect(document.querySelector("button.grand")).toBeNull();

        props.table = table(FOREHAND, "choosing", {}, "allowed");
        flushSync();
        expect(key().classList.contains("armed")).toBe(false);
    });
});
