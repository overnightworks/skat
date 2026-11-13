// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DECLARER, FIRST_OPPONENT, WATCHER, tableWith } from "#lib/giveUp.fixtures.ts";
import GiveUpKey from "#lib/ui/GiveUpKey.svelte";
import { words } from "#lib/words.ts";
import { TABLE_GIVE_UP_SUFFIX, TABLES_PATH } from "#lib/wire.ts";

describe("the give-up key", () => {
    let mounted: ReturnType<typeof mount> | undefined;
    const props = $state({ table: tableWith(DECLARER, null), note: "" });
    const answer = vi.fn<(path: string, init: RequestInit) => Promise<Response>>();

    beforeEach(() => {
        vi.useFakeTimers();
        props.table = tableWith(DECLARER, null);
        props.note = "";
        answer.mockReset().mockImplementation(() => Promise.resolve(Response.json(props.table)));
        vi.stubGlobal("fetch", answer);
        mounted = mount(GiveUpKey, {
            target: document.body,
            props: {
                id: props.table.id,
                get table() {
                    return props.table;
                },
                get note() {
                    return props.note;
                },
                set note(text: string) {
                    props.note = text;
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
        vi.unstubAllGlobals();
    });

    const key = (): HTMLButtonElement | null => document.querySelector("button.give-up");

    async function tap(): Promise<void> {
        (key() as HTMLButtonElement).click();
        await vi.advanceTimersByTimeAsync(0);
        flushSync();
    }

    it("names itself Aufgeben and arms on the first tap without sending anything", async () => {
        const idle = key()?.title;

        await tap();

        expect([idle, key()?.title, key()?.classList.contains("arm"), answer.mock.calls.length]).toEqual([
            words["table.giveUp"],
            words["table.giveUpSure"],
            true,
            0,
        ]);
    });

    it("sends the give-up for the version shown on the second tap within the time", async () => {
        await tap();
        await tap();

        const [path, init] = answer.mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${props.table.id}${TABLE_GIVE_UP_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toMatchObject({ version: props.table.version });
        expect(answer).toHaveBeenCalledTimes(1);
        expect([key()?.disabled, key()?.classList.contains("arm"), props.note]).toEqual([true, false, ""]);
    });

    it("sends nothing when the time has run out between the taps", async () => {
        await tap();
        await vi.advanceTimersByTimeAsync(3000);
        flushSync();
        const fallen = key()?.classList.contains("arm");
        await tap();

        expect([fallen, key()?.classList.contains("arm"), answer.mock.calls.length]).toEqual([false, true, 0]);
    });

    it("falls back when a newer version of the table comes", async () => {
        await tap();

        props.table = { ...props.table, version: props.table.version + 1 };
        flushSync();

        expect([key()?.classList.contains("arm"), key()?.title]).toEqual([false, words["table.giveUp"]]);
    });

    it("shows the failure note and is tappable again when the table refuses", async () => {
        answer.mockImplementation(() => Promise.resolve(Response.json({ reason: "not-declarer" }, { status: 409 })));

        await tap();
        await tap();

        expect([props.note, key()?.disabled]).toEqual([words["table.commandFailed"], false]);
    });

    it("is round while Kontra is offered", () => {
        props.table = tableWith(DECLARER, null, { kontraWord: "kontra" });
        flushSync();

        expect(key()?.classList.contains("round")).toBe(true);
    });

    it.each([
        { name: "a watcher looks on", table: tableWith(WATCHER, null) },
        { name: "a chair is open", table: tableWith(FIRST_OPPONENT, null, { waiting: 3 }) },
    ])("is missing when $name", ({ table }) => {
        props.table = table;
        flushSync();

        expect(key()).toBeNull();
    });
});
