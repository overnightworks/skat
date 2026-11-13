// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";
import TableRules from "#lib/ui/TableRules.svelte";
import { words } from "#lib/words.ts";

const GAMES_LEFT = 3;

describe("the Bock chip", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(() => {
        if (mounted !== undefined) void unmount(mounted);
        mounted = undefined;
        document.body.innerHTML = "";
    });

    it("gives its count a name assistive technology reads", () => {
        mounted = mount(TableRules, {
            target: document.body,
            props: {
                options: {
                    show_running_points: false,
                    kontra: null,
                    ramsch: null,
                    bock: { triggers: ["sixty-sixty"], overlap: "append" },
                },
                bock: { games_left: GAMES_LEFT, factor: 2 },
            },
        });
        flushSync();

        const count = document.querySelector(".chips .n");

        expect(count?.getAttribute("role")).toBe("img");
        expect(count?.getAttribute("aria-label")).toBe(words["rules.bockLeft"]({ count: GAMES_LEFT }));
    });
});
