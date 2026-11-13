import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { TABLE_KONTRA_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import { sayKontra } from "./tables.ts";

describe("saying a word at the table", () => {
    const table = {
        id: TABLE_ID,
        version: 1,
        chairs: [],
        watchers: 0,
        hand: null,
        passed_in: null,
        series: null,
        ended: null,
    };

    beforeEach(() => {
        vi.stubGlobal("location", { reload: vi.fn(), href: `https://skat.test/t/${TABLE_ID}` });
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(table)));
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("sends the version shown, a command id and the word", async () => {
        expect(await sayKontra(TABLE_ID, 7, "command-6", "re")).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${TABLE_KONTRA_SUFFIX}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({
            command_id: "command-6",
            version: 7,
            word: "re",
        });
    });
});
