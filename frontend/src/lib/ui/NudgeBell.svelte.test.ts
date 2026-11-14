// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NudgeBell from "#lib/ui/NudgeBell.svelte";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { ASK_AGAIN_AFTER, TABLE_NUDGE_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import { words } from "#lib/words.ts";
import type { Nudge } from "../../routes/(start)/nudge.ts";

const MILLISECONDS_PER_SECOND = 1000;
const VERSION = 7;
const AWAITED_SEAT = 3;
const NAME = "Nova";

describe("the bell at the chair the table waits for", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    beforeEach(() => {
        vi.useFakeTimers();
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({})));
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    const props = $state({
        id: TABLE_ID,
        version: VERSION,
        seat: AWAITED_SEAT,
        name: NAME,
        nudge: null as Nudge | null,
        shaking: false,
    });

    function show(nudge: Nudge | null, shaking = false): void {
        props.version = VERSION;
        props.nudge = nudge;
        props.shaking = shaking;
        mounted = mount(NudgeBell, { target: document.body, props });
        flushSync();
    }

    function pass(seconds: number): void {
        vi.advanceTimersByTime(seconds * MILLISECONDS_PER_SECOND);
        flushSync();
    }

    const bell = (): HTMLElement | null => document.querySelector(".mark.bell");
    const mayNudge = (nudges = 0): Nudge => ({ nudges, may_nudge: true, by_name: null });

    it("shows nothing before the minute and a button named after the chair's person when it has passed", () => {
        show(mayNudge());
        const before = bell();

        pass(ASK_AGAIN_AFTER);

        expect([before, bell()?.tagName, bell()?.getAttribute("aria-label")]).toEqual([
            null,
            "BUTTON",
            `${NAME} ${words["table.nudge"]}`,
        ]);
    });

    it("is not offered one second before the minute is over", () => {
        show(mayNudge());

        pass(ASK_AGAIN_AFTER - 1);

        expect(bell()).toBeNull();
    });

    it("sends the version, the seat and the nudges it saw when it is tapped", () => {
        show(mayNudge());
        pass(ASK_AGAIN_AFTER);

        (bell() as HTMLButtonElement).click();

        const [path, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
        expect([path, JSON.parse(init.body as string)]).toEqual([
            `${TABLES_PATH}/${TABLE_ID}${TABLE_NUDGE_SUFFIX}`,
            { version: VERSION, seat: AWAITED_SEAT, nudges: 0 },
        ]);
    });

    it("never offers a person who may not nudge, and shows nothing while nobody nudged", () => {
        show({ nudges: 0, may_nudge: false, by_name: null });

        pass(ASK_AGAIN_AFTER);

        expect(bell()).toBeNull();
    });

    it("rests with its tick for a viewer who may not nudge again, and stays at rest after the minute", () => {
        show({ nudges: 2, may_nudge: false, by_name: null });
        const resting = [bell()?.classList.contains("belled"), bell()?.querySelector("i") !== null];

        pass(ASK_AGAIN_AFTER);

        expect([resting, bell()?.tagName, bell()?.getAttribute("aria-label")]).toEqual([
            [true, true],
            "SPAN",
            words["table.nudged"],
        ]);
    });

    it("rests after a first nudge for a viewer who may nudge again and is offered once more a minute later", () => {
        show(mayNudge(1));
        const resting = bell()?.tagName;

        pass(ASK_AGAIN_AFTER);

        expect([resting, bell()?.tagName]).toEqual(["SPAN", "BUTTON"]);
    });

    it("shakes only when the page is told the nudge has just arrived", () => {
        show({ nudges: 1, may_nudge: false, by_name: "Anna" }, true);
        const shaking = bell()?.classList.contains("shaken");
        void unmount(mounted as ReturnType<typeof mount>);
        show({ nudges: 1, may_nudge: false, by_name: "Anna" });

        expect([shaking, bell()?.classList.contains("shaken")]).toEqual([true, false]);
    });

    it("starts its minute anew when the table moves on to a newer version", () => {
        show(mayNudge());
        pass(ASK_AGAIN_AFTER - 1);

        props.version = VERSION + 1;
        flushSync();
        pass(ASK_AGAIN_AFTER - 1);
        const before = bell();
        pass(1);

        expect([before, bell()?.tagName]).toEqual([null, "BUTTON"]);
    });

    it("starts its minute anew when the chair was nudged once more, and rests until then", () => {
        show(mayNudge());
        pass(ASK_AGAIN_AFTER);

        props.nudge = mayNudge(1);
        flushSync();

        expect(bell()?.tagName).toBe("SPAN");
    });

    it("shows nothing at a chair that has no nudge and offers its bell a minute after the nudge appears", () => {
        show(null);
        pass(ASK_AGAIN_AFTER);
        const without = bell();

        props.nudge = mayNudge();
        flushSync();
        const appeared = bell();
        pass(ASK_AGAIN_AFTER);

        expect([without, appeared, bell()?.tagName]).toEqual([null, null, "BUTTON"]);
    });
});
