// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";
import { standingRow } from "#lib/series.ts";
import Standings from "#lib/ui/Standings.svelte";
import { words } from "#lib/words.ts";

const view = {
    heading: words["table.seriesEnded"],
    sub: words["table.seriesGames"](9),
    rows: [standingRow({ display_name: "Anna", seat: 1, kind: "person", total: 502, won: 3, lost: 0, place: 1 }, null)],
};

describe("the ranks of the series' end", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
    });

    function show(closed: boolean): void {
        mounted = mount(Standings, { target: document.body, props: { view, closed } });
        flushSync();
    }

    it("tell each account's won and lost games on the live table", () => {
        show(false);

        expect(document.querySelector(".rank small")?.textContent).toBe(view.rows[0]?.record);
    });

    it("draw the place, the name and the total only on the closed link", () => {
        show(true);

        expect(document.querySelector(".rank small")).toBeNull();
    });
});
