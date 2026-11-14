import { afterEach, describe, expect, it, vi } from "vitest";
import { RULE_SETS_PATH, SWITCH_ON_OPTIONS, TABLES_PATH, VISIBILITY_TOKENS } from "#lib/wire.ts";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { createTable, readRuleSets, saveRuleSet } from "./openTable.ts";
import type { OptionsRequest } from "./tables.ts";

describe("opening a table", () => {
    const table = {
        id: TABLE_ID,
        version: 1,
        chairs: [],
        watchers: 0,
        hand: null,
        passed_in: null,
        series: null,
        aborted: null,
        options: null,
        ended: null,
    };

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    function answerWith(response: Response | Error) {
        vi.stubGlobal(
            "fetch",
            response instanceof Error ? vi.fn().mockRejectedValue(response) : vi.fn().mockResolvedValue(response),
        );
    }

    it("sends the command id and the series length when creating a table", async () => {
        answerWith(Response.json(table));
        await createTable("command-1", 30);

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(TABLES_PATH);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-1", series_length: 30 });
    });

    it("sends the options only when they are given", async () => {
        answerWith(Response.json(table));
        await createTable("command-1", 30, { show_running_points: true });

        const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(JSON.parse((init as { body: string }).body)).toEqual({
            command_id: "command-1",
            series_length: 30,
            options: { show_running_points: true },
        });
    });

    it.each(VISIBILITY_TOKENS)("sends the %s visibility the person chose when creating a table", async (visibility) => {
        answerWith(Response.json(table));

        await createTable("command-1", 30, undefined, visibility);

        const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(JSON.parse((init as { body: string }).body)).toEqual({
            command_id: "command-1",
            series_length: 30,
            visibility,
        });
    });

    it("sends the request object as given when creating a table", async () => {
        answerWith(Response.json(table));
        const options: OptionsRequest = {
            kontra: { sayer: "any-opponent", reach: "kontra-re", deadline: "own-card" },
            bock: { triggers: ["sixty-sixty", "schneider"], overlap: "multiply" },
        };

        await createTable("command-1", 30, options);

        const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(JSON.parse((init as { body: string }).body)).toEqual({
            command_id: "command-1",
            series_length: 30,
            options,
        });
    });

    it("answers the sets of the person as the server lists them", async () => {
        const sets = [{ id: "set-1", name: "Felix", options: SWITCH_ON_OPTIONS }];
        answerWith(Response.json({ sets }));

        expect(await readRuleSets()).toEqual({ kind: "sets", sets });
        expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe(RULE_SETS_PATH);
    });

    it.each([
        ["a refusal", () => Response.json({}, { status: 500 })],
        ["an answer that is not JSON", () => new Response("<html>", { status: 200 })],
        ["an answer without a list", () => Response.json({})],
        ["no answer", () => new TypeError("offline")],
    ])("answers %s as failed, never as an empty list", async (_name, answer) => {
        answerWith(answer());

        expect(await readRuleSets()).toEqual({ kind: "failed" });
    });

    it("sends the name and the options of the sheet when saving a rule set and answers the saved set", async () => {
        const options: OptionsRequest = { show_running_points: true };
        const set = { id: "set-1", name: "Abend", options: { ...SWITCH_ON_OPTIONS, show_running_points: true } };
        answerWith(Response.json(set));

        expect(await saveRuleSet("Abend", options)).toEqual({ kind: "saved", set });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(RULE_SETS_PATH);
        expect((init as { method: string }).method).toBe("POST");
        expect(JSON.parse((init as { body: string }).body)).toEqual({ name: "Abend", options });
    });

    it("sends no options as the official rules when saving a rule set", async () => {
        answerWith(Response.json({ id: "set-1", name: "Abend", options: SWITCH_ON_OPTIONS }));

        await saveRuleSet("Abend", undefined);

        const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(JSON.parse((init as { body: string }).body)).toEqual({ name: "Abend", options: {} });
    });

    it.each([
        ["a name that holds other options", () => Response.json({ reason: "name-taken" }, { status: 409 }), "taken"],
        ["a refusal", () => Response.json({}, { status: 422 }), "failed"],
        ["a conflict of another reason", () => Response.json({ reason: "other" }, { status: 409 }), "failed"],
        ["an answer that is not JSON", () => new Response("<html>", { status: 200 }), "failed"],
        ["no answer", () => new TypeError("offline"), "failed"],
    ])("answers %s when saving a rule set", async (_name, answer, kind) => {
        answerWith(answer());

        expect(await saveRuleSet("Abend", undefined)).toEqual({ kind });
    });
});
