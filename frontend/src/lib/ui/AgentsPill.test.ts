// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { loadKitWords, type KitWords } from "overnightworks-design/words";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import AgentsPill from "#lib/ui/AgentsPill.svelte";
import { TABLE_AGENT_CALL_SUFFIX, TABLE_AGENTS_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import { language, words } from "#lib/words.ts";

const TABLE_ID = "b".repeat(32);
const CONTROL_PATH = `${TABLES_PATH}/${TABLE_ID}${TABLE_AGENTS_SUFFIX}`;
const row = { key: "key-nova", name: "Nova", state: "available", ends_in_seconds: null };

type Answer = { control: object; call?: Response };

// The server's answers by path: the control for a read, whatever `call` is for the POST of a row's call.
function server({ control, call }: Answer) {
    const fetcher = vi.fn((path: string, init?: RequestInit) =>
        Promise.resolve(init?.method === "POST" && call !== undefined ? call.clone() : Response.json(control)),
    );
    vi.stubGlobal("fetch", fetcher);
    return fetcher;
}

const settle = () => new Promise((resolve) => setTimeout(resolve));
const pill = () => document.querySelector<HTMLButtonElement>("button.agents");
const popover = () => document.querySelector(".agents-pop");

describe("the Agenten pill", () => {
    let mounted: ReturnType<typeof mount> | undefined;
    let kitWords: KitWords;

    beforeAll(async () => {
        kitWords = await loadKitWords(language);
    });

    beforeEach(() => {
        vi.stubGlobal("location", { reload: vi.fn() });
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        vi.unstubAllGlobals();
    });

    async function show(streamedVersion: number | null) {
        mounted = mount(AgentsPill, { target: document.body, props: { tableId: TABLE_ID, streamedVersion, kitWords } });
        await settle();
        flushSync();
    }

    it("reads nothing before the stream's first table and shows nothing", async () => {
        const fetcher = server({ control: { shown: true, rows: [row] } });

        await show(null);

        expect([pill(), fetcher.mock.calls.length]).toEqual([null, 0]);
    });

    it("shows nothing to a viewer the control is not shown to", async () => {
        const fetcher = server({ control: { shown: false, rows: [] } });

        await show(1);

        expect([pill(), fetcher.mock.calls.length]).toEqual([null, 1]);
        expect(fetcher).toHaveBeenCalledWith(CONTROL_PATH, undefined);
    });

    it("shows the pill with the mark and the word, named Agenten", async () => {
        server({ control: { shown: true, rows: [row] } });

        await show(1);

        expect(pill()?.getAttribute("aria-label")).toBe(words["agents.pill"]);
        expect(pill()?.textContent).toContain("AI");
        expect(pill()?.textContent).toContain(words["agents.pill"]);
        expect(popover()).toBeNull();
    });

    it("opens the kit's list on a tap, with a row per agent, and closes it with the next tap", async () => {
        server({ control: { shown: true, rows: [row] } });
        await show(1);

        pill()?.click();
        await settle();
        flushSync();

        expect(pill()?.getAttribute("aria-expanded")).toBe("true");
        expect(popover()?.textContent).toContain("Nova");
        expect(popover()?.querySelector(".act")?.getAttribute("aria-label")).toBe(
            kitWords["agent.callLabel"]({ name: "Nova" }),
        );

        pill()?.click();
        flushSync();

        expect(popover()).toBeNull();
    });

    it("says that nobody is reachable when the list is empty and keeps the pill", async () => {
        server({ control: { shown: true, rows: [] } });
        await show(1);

        pill()?.click();
        await settle();
        flushSync();

        expect(popover()?.textContent).toContain(kitWords["agent.empty"]);
    });

    it("calls the row's agent with a tap on Rufen and shows the row calling", async () => {
        const inviting = { ...row, state: "inviting", ends_in_seconds: 120 };
        const fetcher = server({
            control: { shown: true, rows: [row] },
            call: Response.json({ shown: true, rows: [inviting] }),
        });
        await show(1);
        pill()?.click();
        await settle();
        flushSync();

        popover()?.querySelector<HTMLButtonElement>(".act")?.click();
        await settle();
        flushSync();

        expect(fetcher).toHaveBeenCalledWith(`${CONTROL_PATH}/key-nova${TABLE_AGENT_CALL_SUFFIX}`, { method: "POST" });
        expect(popover()?.textContent).toContain(kitWords["agent.calling"]);
    });

    it("shows the refusal above the rows until the list closes", async () => {
        server({
            control: { shown: true, rows: [row] },
            call: Response.json({ reason: "place-full" }, { status: 409 }),
        });
        await show(1);
        pill()?.click();
        await settle();
        flushSync();

        popover()?.querySelector<HTMLButtonElement>(".act")?.click();
        await settle();
        flushSync();
        const shown = popover()?.querySelector("[role=alert]")?.textContent;
        pill()?.click();
        flushSync();
        pill()?.click();
        await settle();
        flushSync();

        expect(shown).toContain(kitWords["agent.placeFull"]);
        expect(popover()?.querySelector("[role=alert]")).toBeNull();
    });

    it("closes on a tap outside the pill and its list, and not on a tap inside", async () => {
        server({ control: { shown: true, rows: [row] } });
        await show(1);
        pill()?.click();
        await settle();
        flushSync();

        popover()?.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
        flushSync();
        const afterInside = popover() !== null;
        document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
        flushSync();

        expect([afterInside, popover()]).toEqual([true, null]);
    });

    it("hangs the list over the pill inside the margin of both edges", async () => {
        server({ control: { shown: true, rows: [row] } });
        await show(1);
        vi.stubGlobal("innerWidth", 360);

        pill()?.click();
        await settle();
        flushSync();

        const style = (popover() as HTMLElement).style;
        expect([style.width, style.left.endsWith("px"), style.getPropertyValue("--caret").endsWith("px")]).toEqual([
            "300px",
            true,
            true,
        ]);
    });
});
