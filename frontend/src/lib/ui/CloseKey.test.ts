// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CloseKey from "#lib/ui/CloseKey.svelte";
import { words } from "#lib/words.ts";
import { TABLE_CLOSE_SUFFIX, TABLES_PATH } from "#lib/wire.ts";

const TABLE_ID = "0123456789abcdef0123456789abcdef";

describe("the opener's close key", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    beforeEach(() => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ id: TABLE_ID })));
        mounted = mount(CloseKey, { target: document.body, props: { id: TABLE_ID, note: "" } });
        flushSync();
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        vi.unstubAllGlobals();
    });

    const key = (): HTMLButtonElement => document.querySelector("button.close") as HTMLButtonElement;
    const dialog = (): Element | null => document.querySelector("[role=dialog]");
    const press = (name: string): void => {
        const button = Array.from(document.querySelectorAll("[role=dialog] button")).find((each) =>
            each.textContent.includes(name),
        ) as HTMLButtonElement;
        button.click();
        flushSync();
    };

    it("names itself Tisch schließen and asks nothing until it is tapped", () => {
        expect([key().title, key().querySelector(".label")?.textContent, dialog()]).toEqual([
            words["table.close"],
            words["table.close"],
            null,
        ]);
    });

    it("opens the dialog on a tap and sends nothing yet", () => {
        key().click();
        flushSync();

        expect([dialog()?.getAttribute("aria-label"), vi.mocked(fetch).mock.calls.length]).toEqual([
            words["table.closeQuestion"],
            0,
        ]);
    });

    it("sends nothing and closes the dialog on Abbrechen", () => {
        key().click();
        flushSync();

        press(words["table.closeCancel"]);

        expect([dialog(), vi.mocked(fetch).mock.calls.length]).toEqual([null, 0]);
    });

    it("says the close failed and keeps the table when the answer is no table", async () => {
        let note = "";
        await unmount(mounted as ReturnType<typeof mount>);
        vi.mocked(fetch).mockResolvedValue(Response.json({ reason: "not-allowed" }, { status: 409 }));
        mounted = mount(CloseKey, {
            target: document.body,
            props: {
                id: TABLE_ID,
                get note() {
                    return note;
                },
                set note(value: string) {
                    note = value;
                },
            },
        });
        flushSync();
        key().click();
        flushSync();

        press(words["table.closeConfirm"]);
        await vi.waitFor(() => {
            expect(note).toBe(words["table.commandFailed"]);
        });
    });

    it("sends the close once on Schließen and closes the dialog", async () => {
        key().click();
        flushSync();

        press(words["table.closeConfirm"]);
        await vi.waitFor(() => {
            expect(fetch).toHaveBeenCalledTimes(1);
        });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect([path, (init as { method: string }).method, dialog()]).toEqual([
            `${TABLES_PATH}/${TABLE_ID}${TABLE_CLOSE_SUFFIX}`,
            "POST",
            null,
        ]);
        expect(Object.keys(JSON.parse((init as { body: string }).body) as object)).toEqual(["command_id"]);
    });
});
