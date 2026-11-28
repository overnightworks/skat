// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { loadKitWords, type KitWords } from "overnightworks-design/words";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import AgentsList from "#lib/ui/AgentsList.svelte";
import { TABLE_AGENT_CALL_SUFFIX, TABLE_AGENT_SEND_AWAY_SUFFIX, TABLE_AGENTS_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import { language, words } from "#lib/words.ts";

const TABLE_ID = "b".repeat(32);
const CONTROL_PATH = `${TABLES_PATH}/${TABLE_ID}${TABLE_AGENTS_SUFFIX}`;
const row = { key: "key-nova", name: "Nova", state: "available", outcome: null, ends_in_seconds: null };
// How long the kit shows a call's outcome before it draws the row as it would any other.
const OUTCOME_MILLISECONDS = 4000;

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
const list = () => document.querySelector(".agents-list");

describe("the agents' list in the table menu", () => {
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

    // The page's facts the list follows, which a test moves like the stream and the menu do; `shown` is what the list
    // tells the menu.
    const table = $state<{
        streamedVersion: number | null;
        seatedAgents: string;
        watchers: number;
        open: boolean;
        shown: boolean;
    }>({ streamedVersion: null, seatedAgents: "", watchers: 0, open: false, shown: false });

    async function show(streamedVersion: number | null, open = false) {
        Object.assign(table, { streamedVersion, seatedAgents: "", watchers: 0, open, shown: false });
        mounted = mount(AgentsList, {
            target: document.body,
            props: {
                tableId: TABLE_ID,
                kitWords,
                get streamedVersion() {
                    return table.streamedVersion;
                },
                get seatedAgents() {
                    return table.seatedAgents;
                },
                get watchers() {
                    return table.watchers;
                },
                get open() {
                    return table.open;
                },
                get shown() {
                    return table.shown;
                },
                set shown(value: boolean) {
                    table.shown = value;
                },
            },
        });
        await settle();
        flushSync();
    }

    async function openMenu() {
        table.open = true;
        await settle();
        flushSync();
    }

    async function closeMenu() {
        table.open = false;
        await settle();
        flushSync();
    }

    const callKey = () => list()?.querySelector<HTMLButtonElement>(".act");

    it("reads nothing before the stream's first table and shows nothing", async () => {
        const fetcher = server({ control: { shown: true, rows: [row] } });
        await show(null);

        expect([list(), table.shown, fetcher.mock.calls.length]).toEqual([null, false, 0]);
    });

    it("shows nothing to a viewer the control is not shown to", async () => {
        const fetcher = server({ control: { shown: false, rows: [] } });

        await show(1);

        expect([list(), table.shown, fetcher.mock.calls.length]).toEqual([null, false, 1]);
        expect(fetcher).toHaveBeenCalledWith(CONTROL_PATH, undefined);
    });

    it("shows the kit's list with a row per agent and tells the menu it has rows", async () => {
        server({ control: { shown: true, rows: [row] } });

        await show(1);

        expect(list()?.textContent).toContain("Nova");
        expect(callKey()?.getAttribute("aria-label")).toBe(kitWords["agent.callLabel"]({ name: "Nova" }));
        expect(table.shown).toBe(true);
    });

    it("reads again when an agent sits, which shows the list to an owner who had none", async () => {
        const fetcher = server({ control: { shown: false, rows: [] } });
        await show(1);
        fetcher.mockImplementation(() => Promise.resolve(Response.json({ shown: true, rows: [row] })));

        table.streamedVersion = 2;
        table.seatedAgents = "2:Nova";
        await settle();
        flushSync();

        expect([fetcher.mock.calls.length, list() === null]).toEqual([2, false]);
    });

    it("reads again when one agent leaves and another sits in a single wake, so the count stays the same", async () => {
        const fetcher = server({ control: { shown: false, rows: [] } });
        await show(1);
        table.seatedAgents = "2:Luna";
        table.streamedVersion = 2;
        await settle();
        flushSync();
        fetcher.mockImplementation(() => Promise.resolve(Response.json({ shown: true, rows: [row] })));

        table.streamedVersion = 3;
        table.seatedAgents = "3:Nova";
        await settle();
        flushSync();

        expect([fetcher.mock.calls.length, list() === null]).toEqual([3, false]);
    });

    it("takes the list away when the control stops being shown and brings it back when it is shown again", async () => {
        const fetcher = server({ control: { shown: true, rows: [row] } });
        await show(1);
        fetcher.mockImplementation(() => Promise.resolve(Response.json({ shown: false, rows: [] })));
        table.streamedVersion = 2;
        table.seatedAgents = "2:Nova";
        await settle();
        flushSync();
        const whileHidden = [list(), table.shown];
        fetcher.mockImplementation(() => Promise.resolve(Response.json({ shown: true, rows: [row] })));

        table.streamedVersion = 3;
        table.seatedAgents = "";
        await settle();
        flushSync();

        expect([whileHidden, list() === null]).toEqual([[null, false], false]);
    });

    it("reads nothing for a later table that seats no other agent while the menu is closed", async () => {
        const fetcher = server({ control: { shown: true, rows: [row] } });
        await show(1);

        table.streamedVersion = 2;
        await settle();
        flushSync();

        expect(fetcher.mock.calls).toHaveLength(1);
    });

    it("reads again when the menu opens", async () => {
        const fetcher = server({ control: { shown: true, rows: [row] } });
        await show(1);

        await openMenu();

        expect(fetcher.mock.calls).toHaveLength(2);
    });

    it("reads again when the people who watch change while the menu is open, which lists an agent whose owner just came", async () => {
        const fetcher = server({ control: { shown: true, rows: [] } });
        await show(1, true);
        fetcher.mockImplementation(() => Promise.resolve(Response.json({ shown: true, rows: [row] })));

        table.watchers = 1;
        await settle();
        flushSync();

        expect(list()?.textContent).toContain("Nova");
    });

    it("reads nothing for a change of the people who watch while the menu is closed", async () => {
        const fetcher = server({ control: { shown: true, rows: [row] } });
        await show(1);

        table.watchers = 1;
        await settle();
        flushSync();

        expect(fetcher.mock.calls).toHaveLength(1);
    });

    describe("when the read of the agents fails", () => {
        const failing = () => Promise.resolve(new Response(null, { status: 503 }));
        const failedLine = () => list()?.querySelector("[role=alert]")?.textContent;

        it("leaves no call or send-away key and says the list cannot load, then brings the rows back with the next good read", async () => {
            const here = { ...row, key: "key-luna", name: "Luna", state: "here" };
            const fetcher = server({ control: { shown: true, rows: [row, here] } });
            await show(1, true);
            const rowsBefore = list()?.querySelectorAll(".act").length;
            fetcher.mockImplementation(failing);

            table.watchers = 1;
            await settle();
            flushSync();
            const whileFailed = [list()?.querySelectorAll(".act").length, failedLine(), table.shown];
            fetcher.mockImplementation(() => Promise.resolve(Response.json({ shown: true, rows: [row, here] })));
            table.watchers = 2;
            await settle();
            flushSync();

            expect(rowsBefore).toBe(2);
            expect(whileFailed).toEqual([0, words["table.seriesListFailed"], true]);
            expect([list()?.querySelectorAll(".act").length, failedLine()]).toEqual([2, undefined]);
        });

        it("shows the line and no key when the first read fails", async () => {
            const fetcher = server({ control: { shown: true, rows: [row] } });
            fetcher.mockImplementation(failing);

            await show(1, true);

            expect([callKey(), failedLine()]).toEqual([null, words["table.seriesListFailed"]]);
        });
    });

    it("says that nobody is reachable when the list is empty", async () => {
        server({ control: { shown: true, rows: [] } });

        await show(1, true);

        expect(list()?.textContent).toContain(kitWords["agent.empty"]);
    });

    it("says that the place is full, not that nobody is reachable, when the control is full", async () => {
        server({ control: { shown: true, full: true, rows: [] } });

        await show(1, true);

        expect(list()?.textContent).toContain(kitWords["agent.placeFull"]);
        expect(list()?.textContent).not.toContain(kitWords["agent.empty"]);
    });

    it("calls the row's agent with a tap on Rufen and shows the row calling", async () => {
        const inviting = { ...row, state: "inviting", ends_in_seconds: 120 };
        const fetcher = server({
            control: { shown: true, rows: [row] },
            call: Response.json({ shown: true, rows: [inviting] }),
        });
        await show(1, true);

        callKey()?.click();
        await settle();
        flushSync();

        expect(fetcher).toHaveBeenCalledWith(`${CONTROL_PATH}/key-nova${TABLE_AGENT_CALL_SUFFIX}`, { method: "POST" });
        expect(list()?.textContent).toContain(kitWords["agent.calling"]);
    });

    it.each([
        ["no-answer", "agent.noAnswer"],
        ["busy", "agent.busy"],
        ["owner-absent", "agent.ownerAbsent"],
    ] as const)(
        "tells the caller a call that ended %s in the kit's words in place of the call key",
        async (outcome, wording) => {
            const ended = { ...row, state: "ended", outcome };
            server({ control: { shown: true, rows: [ended] } });

            await show(1, true);

            expect(list()?.textContent).toContain(kitWords[wording]);
            expect(callKey()).toBeNull();
        },
    );

    describe("a call that ended and whose outcome has been read", () => {
        const ended = { ...row, state: "ended", outcome: "owner-absent", may_call_again: false };

        beforeEach(() => {
            vi.useFakeTimers({ shouldAdvanceTime: true });
        });

        afterEach(() => {
            vi.useRealTimers();
        });

        async function readOutcome() {
            await vi.advanceTimersByTimeAsync(OUTCOME_MILLISECONDS);
            flushSync();
        }

        it("leaves the list when its agent may not be called again, and stays away across a read of the same row", async () => {
            const fetcher = server({ control: { shown: true, rows: [ended] } });
            await show(1, true);
            expect(list()?.textContent).toContain(kitWords["agent.ownerAbsent"]);

            await readOutcome();
            expect(list()?.textContent).not.toContain("Nova");

            await closeMenu();
            await openMenu();
            expect([fetcher.mock.calls.length > 2, list()?.textContent.includes("Nova")]).toEqual([true, false]);
        });

        it("returns once the row changes", async () => {
            const fetcher = server({ control: { shown: true, rows: [ended] } });
            await show(1, true);
            await readOutcome();
            fetcher.mockImplementation(() =>
                Promise.resolve(Response.json({ shown: true, rows: [{ ...ended, outcome: "busy" }] })),
            );

            await closeMenu();
            await openMenu();

            expect(list()?.textContent).toContain(kitWords["agent.busy"]);
        });

        it.each([
            ["turns into another state", [row]],
            ["leaves the answer", []],
        ])("shows the outcome of the same ending again after the row %s", async (_case, between) => {
            const fetcher = server({ control: { shown: true, rows: [ended] } });
            await show(1, true);
            await readOutcome();
            const answerWith = (rows: object[]) =>
                fetcher.mockImplementation(() => Promise.resolve(Response.json({ shown: true, rows })));

            answerWith(between);
            await closeMenu();
            await openMenu();
            answerWith([ended]);
            await closeMenu();
            await openMenu();

            expect(list()?.textContent).toContain(kitWords["agent.ownerAbsent"]);
        });

        it("turns into its call key when its agent may be called again", async () => {
            server({ control: { shown: true, rows: [{ ...ended, outcome: "no-answer", may_call_again: true }] } });
            await show(1, true);
            expect(callKey()).toBeNull();

            await readOutcome();

            expect(callKey()?.getAttribute("aria-label")).toBe(kitWords["agent.callLabel"]({ name: "Nova" }));
        });
    });

    it("asks a here row's agent to leave with a tap on Bitten zu gehen and shows the row available again", async () => {
        const here = { ...row, state: "here" };
        const fetcher = server({
            control: { shown: true, rows: [here] },
            call: Response.json({ shown: true, rows: [row] }),
        });
        await show(1, true);
        const button = callKey();

        button?.click();
        await settle();
        flushSync();

        expect(button?.getAttribute("aria-label")).toBe(kitWords["agent.askToLeaveLabel"]({ name: "Nova" }));
        const [path, init] = fetcher.mock.calls.at(-1) ?? [];
        expect([path, init?.method]).toEqual([`${CONTROL_PATH}/key-nova${TABLE_AGENT_SEND_AWAY_SUFFIX}`, "POST"]);
        expect(callKey()?.getAttribute("aria-label")).toBe(kitWords["agent.callLabel"]({ name: "Nova" }));
    });

    it("shows the refusal above the rows until the menu closes", async () => {
        server({
            control: { shown: true, rows: [row] },
            call: Response.json({ reason: "place-full" }, { status: 409 }),
        });
        await show(1, true);

        callKey()?.click();
        await settle();
        flushSync();
        const shown = list()?.querySelector("[role=alert]")?.textContent;
        await closeMenu();

        expect(shown).toContain(kitWords["agent.placeFull"]);
        expect(list()?.querySelector("[role=alert]")).toBeNull();
    });

    it("keeps the list and the refusal while the read after it no longer shows the control, and takes both when the menu closes", async () => {
        const here = { ...row, state: "here" };
        const fetcher = server({ control: { shown: true, rows: [here] } });
        await show(1, true);
        fetcher.mockImplementation((_path: string, init?: RequestInit) =>
            Promise.resolve(
                init?.method === "POST"
                    ? Response.json({ reason: "not-allowed" }, { status: 409 })
                    : Response.json({ shown: false, rows: [] }),
            ),
        );

        callKey()?.click();
        await settle();
        flushSync();
        const shown = [list()?.querySelector("[role=alert]")?.textContent, list()?.querySelectorAll(".act").length];
        await closeMenu();

        expect(shown[0]).toContain(kitWords["agent.notAllowed"]);
        expect(shown[1]).toBe(1);
        expect([list(), table.shown]).toEqual([null, false]);
    });
});
