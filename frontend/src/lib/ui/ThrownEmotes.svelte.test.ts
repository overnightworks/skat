// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ThrownEmotes from "#lib/ui/ThrownEmotes.svelte";
import { receiveReactions, resetReactions } from "#lib/tableReactions.svelte.ts";
import type { Chair } from "../../routes/(start)/tables.ts";
import type { Thrown } from "../../routes/(start)/reaction.ts";

vi.mock("#lib/tableSound.ts", () => ({ soundForReaction: () => undefined }));

const chair = (seat: number, isMine: boolean): Chair => ({
    seat,
    occupant_name: `Person ${String(seat)}`,
    occupant_kind: "person",
    is_mine: isMine,
    is_away: false,
    ready: true,
    total: null,
    hand: null,
    former_holder_name: null,
    is_mine_to_return: false,
    nudge: null,
    turn_state: null,
});

describe("what a thrown emote shows on the felt", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
        resetReactions();
        vi.useRealTimers();
    });

    function throwEmote(by_seat: number | null, by_name: string | null, reaction: Thrown["reaction"] = "fire"): void {
        const thrown: Thrown = { number: 1, reaction, by_seat, by_name };
        mounted = mount(ThrownEmotes, {
            target: document.body,
            props: { chairs: [chair(1, false), chair(2, true), chair(3, false)] },
        });
        receiveReactions([thrown]);
        flushSync();
    }

    it("draws a dashed trail of the arc beside the emote", () => {
        throwEmote(1, "Anna");

        const path = document.querySelector(".emote-trail path")?.getAttribute("d") ?? "";

        expect(path.startsWith("M")).toBe(true);
        expect(path.split("L")).toHaveLength(8);
    });

    it("tells the stylesheet where the emote starts and where it lands", () => {
        throwEmote(1, "Anna");

        const emote = document.querySelector<HTMLElement>(".emote");

        for (const property of ["--ox", "--oy", "--lx", "--ly"]) {
            expect(emote?.style.getPropertyValue(property)).toMatch(/^\d+$/);
        }
    });

    it("marks the thrower's initial with the colour of the thrower's seat", () => {
        throwEmote(3, "Ben");

        const from = document.querySelector(".emote .from");

        expect(from?.textContent).toBe("B");
        expect(from?.classList.contains("seat-3")).toBe(true);
    });

    it("shows a watcher's emote with no name badge, as a watcher has no name at the table", () => {
        throwEmote(null, null);

        const emote = document.querySelector(".emote");

        expect(emote?.textContent).toContain("\u{1F525}");
        expect(emote?.querySelector(".from")).toBeNull();
    });

    it("lets a knock land where it is thrown from, with two rings and no trail", () => {
        throwEmote(1, "Anna", "knock");

        const fist = document.querySelector<HTMLElement>(".emote.knocked");
        const ring = document.querySelector<HTMLElement>(".knock-ring");

        expect(fist?.textContent).toContain("\u{1F44A}");
        expect(document.querySelector(".emote-trail")).toBeNull();
        expect(fist?.style.getPropertyValue("--ox")).toBe(fist?.style.getPropertyValue("--lx"));
        expect(fist?.style.getPropertyValue("--oy")).toBe(fist?.style.getPropertyValue("--ly"));
        expect(ring?.style.getPropertyValue("--lx")).toBe(fist?.style.getPropertyValue("--lx"));
        expect(ring?.style.getPropertyValue("--ly")).toBe(fist?.style.getPropertyValue("--ly"));
    });

    it("draws no ring for an emote that flies", () => {
        throwEmote(1, "Anna", "fire");

        expect(document.querySelector(".knock-ring")).toBeNull();
        expect(document.querySelector(".emote.knocked")).toBeNull();
    });
});
