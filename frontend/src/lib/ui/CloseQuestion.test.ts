// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CloseQuestion from "#lib/ui/CloseQuestion.svelte";
import { words } from "#lib/words.ts";
import { TABLE_CLOSE_SUFFIX, TABLES_PATH } from "#lib/wire.ts";

const TABLE_ID = "0123456789abcdef0123456789abcdef";

describe("the question before a table closes", () => {
    let mounted: ReturnType<typeof mount> | undefined;
    let answered = 0;

    beforeEach(() => {
        answered = 0;
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ id: TABLE_ID })));
        mounted = mount(CloseQuestion, {
            target: document.body,
            props: {
                id: TABLE_ID,
                note: "",
                onanswered: () => {
                    answered += 1;
                },
            },
        });
        flushSync();
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        vi.unstubAllGlobals();
    });

    const dialog = (): Element | null => document.querySelector("[role=dialog]");
    const press = (name: string): void => {
        const button = Array.from(document.querySelectorAll("[role=dialog] button")).find((each) =>
            each.textContent.includes(name),
        ) as HTMLButtonElement;
        button.click();
        flushSync();
    };

    it("asks for all at the table and sends nothing until it is answered", () => {
        expect([dialog()?.getAttribute("aria-label"), vi.mocked(fetch).mock.calls.length]).toEqual([
            words["table.closeQuestion"],
            0,
        ]);
    });

    it("sends nothing and hands the page back on Abbrechen", () => {
        press(words["table.closeCancel"]);

        expect([answered, vi.mocked(fetch).mock.calls.length]).toEqual([1, 0]);
    });

    it("says the close failed and keeps the table when the answer is no table", async () => {
        let note = "";
        await unmount(mounted as ReturnType<typeof mount>);
        vi.mocked(fetch).mockResolvedValue(Response.json({ reason: "not-allowed" }, { status: 409 }));
        mounted = mount(CloseQuestion, {
            target: document.body,
            props: {
                id: TABLE_ID,
                onanswered: () => undefined,
                get note() {
                    return note;
                },
                set note(value: string) {
                    note = value;
                },
            },
        });
        flushSync();

        press(words["table.closeConfirm"]);
        await vi.waitFor(() => {
            expect(note).toBe(words["table.commandFailed"]);
        });
    });

    it("sends the close once on Schließen and hands the page back", async () => {
        press(words["table.closeConfirm"]);
        await vi.waitFor(() => {
            expect(fetch).toHaveBeenCalledTimes(1);
        });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect([path, (init as { method: string }).method, answered]).toEqual([
            `${TABLES_PATH}/${TABLE_ID}${TABLE_CLOSE_SUFFIX}`,
            "POST",
            1,
        ]);
        expect(Object.keys(JSON.parse((init as { body: string }).body) as object)).toEqual(["command_id"]);
    });
});
