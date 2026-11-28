// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import type { KitWords } from "overnightworks-design";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DECLARER, FIRST_OPPONENT, WATCHER, tableWith } from "#lib/giveUp.fixtures.ts";
import TableMenu from "#lib/ui/TableMenu.svelte";
import { words } from "#lib/words.ts";
import type { Table } from "../../routes/(start)/tables.ts";

describe("the table menu", () => {
    let mounted: ReturnType<typeof mount> | undefined;
    let copied = 0;
    let stood = 0;
    let ruled = 0;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        vi.unstubAllGlobals();
    });

    function show(
        table: Table,
        own: { callMode?: boolean; seated?: boolean; styleOffered?: boolean; count?: string | null } = {},
    ): void {
        copied = 0;
        stood = 0;
        ruled = 0;
        mounted = mount(TableMenu, {
            target: document.body,
            props: {
                id: table.id,
                table,
                note: "",
                place: own.callMode === true ? "strip" : "bar",
                callMode: own.callMode ?? false,
                seated: own.seated ?? true,
                styleOffered: own.styleOffered ?? true,
                oncopy: () => {
                    copied += 1;
                },
                onrules: () => {
                    ruled += 1;
                },
                onseries: () => {},
                count: own.count ?? null,
                onstand: () => {
                    stood += 1;
                },
                streamedVersion: null,
                seatedAgents: "",
                watchers: 0,
                kitWords: {} as KitWords,
            },
        });
        flushSync();
    }

    const key = (): HTMLButtonElement | null => document.querySelector("button.menu-key");
    const sections = (): string[] => [...document.querySelectorAll(".menu-section")].map((each) => each.textContent);
    const rows = (): string[] =>
        [...document.querySelectorAll(".table-menu .row")].map(
            (each) => each.querySelector(".label")?.textContent ?? "",
        );

    it("holds the link, the style, the rules, the stand-up, the shortening and the give-up of a seated person at a running game, in two sections, and the account under them", () => {
        show(tableWith(DECLARER, null));

        expect([key()?.getAttribute("aria-label"), sections(), rows()]).toEqual([
            words["table.menu"],
            [words["table.menuTable"], words["table.menuGame"]],
            [
                words["table.copyLink"],
                words["table.style"],
                words["rules.title"],
                words["table.standUp"],
                words["table.shorten"],
                words["table.giveUp"],
                words["account.title"],
            ],
        ]);
    });

    it("offers an opponent the open play before the give-up", () => {
        show(tableWith(FIRST_OPPONENT, null));

        expect(rows().slice(-3, -1)).toEqual([words["table.playOpen"], words["table.giveUp"]]);
    });

    it("holds only the link, the rules and the account for a watcher and has no game section", () => {
        show(tableWith(WATCHER, null), { seated: false, styleOffered: false });

        expect([sections(), rows()]).toEqual([
            [words["table.menuTable"]],
            [words["table.copyLink"], words["rules.title"], words["account.title"]],
        ]);
    });

    it("tells the page when the link row is tapped", () => {
        show(tableWith(DECLARER, null));

        (document.querySelector(".row.link") as HTMLButtonElement).click();

        expect(copied).toBe(1);
    });

    it("tells the page when the rules row is tapped", () => {
        show(tableWith(DECLARER, null));

        (document.querySelector(".row.rules") as HTMLButtonElement).click();

        expect(ruled).toBe(1);
    });

    it("stands up from the menu on the second tap during a hand", () => {
        show(tableWith(DECLARER, null));
        const row = document.querySelector(".row.stand") as HTMLButtonElement;

        row.click();
        flushSync();
        const asked = stood;
        row.click();

        expect([asked, stood]).toEqual([0, 1]);
    });

    it("stands in the strip in a call, without the link, and holds the rules and the game count", () => {
        show(tableWith(DECLARER, null), { callMode: true, count: "Spiel 2 von 36" });

        expect([key()?.classList.contains("strip"), rows()]).toEqual([
            true,
            [
                words["table.style"],
                words["rules.title"],
                "Spiel 2 von 36",
                words["table.standUp"],
                words["table.shorten"],
                words["table.giveUp"],
                words["account.title"],
            ],
        ]);
    });

    it("offers a watcher in a call the link and the rules as outside a call", () => {
        show(tableWith(WATCHER, null), { callMode: true, seated: false, styleOffered: false });

        expect([key()?.classList.contains("strip"), sections(), rows()]).toEqual([
            true,
            [words["table.menuTable"]],
            [words["table.copyLink"], words["rules.title"], words["account.title"]],
        ]);
    });
});
