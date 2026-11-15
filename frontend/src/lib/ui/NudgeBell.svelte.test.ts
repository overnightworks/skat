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
        grumble: null as string | null,
    });

    function show(nudge: Nudge | null, grumble: string | null = null): void {
        props.version = VERSION;
        props.nudge = nudge;
        props.grumble = grumble;
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

    it("leaves nothing at a chair that was nudged and may not be nudged again, not even a tick", () => {
        show({ nudges: 2, may_nudge: false, by_name: null });

        pass(ASK_AGAIN_AFTER);

        expect([bell(), document.querySelector(".mark.bell i, .cowbell")]).toEqual([null, null]);
    });

    it("leaves nothing after a first nudge for a viewer who may nudge again and offers the bell once more a minute later", () => {
        show(mayNudge(1));
        const resting = bell();

        pass(ASK_AGAIN_AFTER);

        expect([resting, bell()?.tagName]).toEqual([null, "BUTTON"]);
    });

    it("swings the cowbell over the chair and shows the line it grumbles, named after the chair's person", () => {
        show({ nudges: 1, may_nudge: false, by_name: null }, "Hetz mich nicht!");

        expect([
            document.querySelector(".cowbell")?.getAttribute("aria-label"),
            document.querySelector(".bubble.grumble .said")?.textContent,
            document.querySelector(".bubble.grumble .dot")?.textContent,
        ]).toEqual([words["table.nudged"], "Hetz mich nicht!", NAME.slice(0, 1)]);
    });

    it("shows no cowbell and no grumble while the page was not told the nudge has just arrived", () => {
        show({ nudges: 1, may_nudge: false, by_name: "Anna" });

        expect([document.querySelector(".cowbell"), document.querySelector(".bubble")]).toEqual([null, null]);
    });

    it("lets the cowbell go when the grumble is over", () => {
        show({ nudges: 1, may_nudge: false, by_name: null }, "Hetz mich nicht!");

        props.grumble = null;
        flushSync();

        expect(document.querySelector(".cowbell")).toBeNull();
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

    it("starts its minute anew when the chair was nudged once more, and offers nothing until then", () => {
        show(mayNudge());
        pass(ASK_AGAIN_AFTER);

        props.nudge = mayNudge(1);
        flushSync();

        expect(bell()).toBeNull();
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
