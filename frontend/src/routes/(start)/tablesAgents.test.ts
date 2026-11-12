import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { words } from "#lib/words.ts";
import { TABLE_AGENT_CALL_SUFFIX, TABLE_AGENTS_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import {
    agentSitsNote,
    callAgent,
    followAgents,
    readAgents,
    rereadAfterSeconds,
    type AgentRow,
    type AgentsControl,
    type Chair,
    type Table,
} from "./tables.ts";

const TABLE_ID = "a".repeat(32);

const nova = (state: "available" | "inviting", ends = 120): AgentRow =>
    state === "available"
        ? { key: "key-nova", name: "Nova", state, ends_in_seconds: null }
        : { key: "key-nova", name: "Nova", state, ends_in_seconds: ends };
const controlOf = (...rows: AgentRow[]): AgentsControl => ({ shown: true, rows });
const cutOff = () =>
    new ReadableStream({
        start: (stream) => {
            stream.error(new TypeError("the transfer broke off"));
        },
    });

describe("the control that calls agents", () => {
    const reload = vi.fn();
    const agentsPath = `${TABLES_PATH}/${TABLE_ID}${TABLE_AGENTS_SUFFIX}`;

    beforeEach(() => {
        reload.mockClear();
        vi.stubGlobal("location", { reload });
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.useRealTimers();
    });

    function answerWith(...responses: (Response | Error)[]) {
        const fetcher = vi.fn();
        for (const response of responses) {
            if (response instanceof Error) fetcher.mockRejectedValueOnce(response);
            else fetcher.mockResolvedValueOnce(response);
        }
        vi.stubGlobal("fetch", fetcher);
        return fetcher;
    }

    describe("reading the control", () => {
        it("returns the control the server answered, asking the table's agents path", async () => {
            const fetcher = answerWith(Response.json(controlOf(nova("available"))));

            expect(await readAgents(TABLE_ID)).toEqual({ kind: "control", control: controlOf(nova("available")) });
            expect(fetcher).toHaveBeenCalledWith(agentsPath, undefined);
        });

        it.each([
            ["a table that is not there", new Response(null, { status: 404 }), "missing"],
            ["any other refusal", new Response(null, { status: 500 }), "failed"],
            ["a server that cannot be reached", new TypeError("offline"), "failed"],
        ])("answers %s as %s", async (_case, response, kind) => {
            answerWith(response);

            expect(await readAgents(TABLE_ID)).toEqual({ kind });
        });

        it.each([
            ["a body that is cut off", new Response(cutOff())],
            ["a body that is no JSON", new Response("<html>")],
        ])("answers %s as failed", async (_case, response) => {
            answerWith(response);

            expect(await readAgents(TABLE_ID)).toEqual({ kind: "failed" });
        });

        it("leaves the sign-in again to the stream when the session has ended", async () => {
            answerWith(new Response(null, { status: 401 }));

            expect(await readAgents(TABLE_ID)).toEqual({ kind: "failed" });
            expect(reload).not.toHaveBeenCalled();
        });
    });

    describe("calling an agent", () => {
        it("posts to the row's call path with no body and answers the control afresh", async () => {
            const fetcher = answerWith(Response.json(controlOf(nova("inviting"))));

            const answer = await callAgent(TABLE_ID, "key-nova");

            expect(answer).toEqual({ kind: "control", control: controlOf(nova("inviting")) });
            expect(fetcher).toHaveBeenCalledWith(`${agentsPath}/key-nova${TABLE_AGENT_CALL_SUFFIX}`, {
                method: "POST",
            });
        });

        it.each(["not-allowed", "owner-absent", "place-full", "agent-unavailable", "try-again"])(
            "answers the refusal %s as the kit's reason",
            async (reason) => {
                answerWith(Response.json({ reason }, { status: 409 }));

                expect(await callAgent(TABLE_ID, "key-nova")).toEqual({ kind: "refused", reason });
            },
        );

        it.each([
            ["a reason the kit has no sentence for", Response.json({ reason: "boom" }, { status: 409 })],
            ["a conflict without a reason", Response.json({ other: 1 }, { status: 409 })],
            ["a conflict that is no object", Response.json("nope", { status: 409 })],
            ["a conflict that is no JSON", new Response("nope", { status: 409 })],
        ])("answers %s as failed", async (_case, response) => {
            answerWith(response);

            expect(await callAgent(TABLE_ID, "key-nova")).toEqual({ kind: "failed" });
        });

        it("answers a table that is not there as missing", async () => {
            answerWith(new Response(null, { status: 404 }));

            expect(await callAgent(TABLE_ID, "key-nova")).toEqual({ kind: "missing" });
        });

        it("goes through the sign-in again when the session has ended", async () => {
            answerWith(new Response(null, { status: 401 }));

            expect(await callAgent(TABLE_ID, "key-nova")).toEqual({ kind: "failed" });
            expect(reload).toHaveBeenCalledOnce();
        });
    });

    describe("how long until the next read", () => {
        it.each([
            ["a row that is only available", [nova("available")], null],
            ["no row at all", [], null],
            ["an inviting row, its own seconds", [nova("inviting", 90)], 90],
            ["an inviting row that ends in under a second", [nova("inviting", 0)], 1],
            ["the nearest of two inviting rows", [nova("inviting", 90), { ...nova("inviting", 30), key: "b" }], 30],
        ])("is %s", (_case, rows, seconds) => {
            expect(rereadAfterSeconds(controlOf(...rows))).toBe(seconds);
        });
    });

    describe("following the control", () => {
        const answers = (...controls: (AgentsControl | Error)[]) =>
            answerWith(...controls.map((control) => (control instanceof Error ? control : Response.json(control))));

        function follower() {
            const shown: AgentsControl[] = [];
            const refusals: (string | null)[] = [];
            const following = followAgents(
                TABLE_ID,
                (control) => shown.push(control),
                (reason) => refusals.push(reason),
            );
            return { following, shown, refusals };
        }

        it("shows what a read answers and reads nothing more while no row is inviting", async () => {
            vi.useFakeTimers();
            const fetcher = answers(controlOf(nova("available")));
            const { following, shown } = follower();

            await following.read();
            await vi.advanceTimersByTimeAsync(600_000);

            expect(shown).toEqual([controlOf(nova("available"))]);
            expect(fetcher).toHaveBeenCalledTimes(1);
        });

        it("reads again after an inviting row's own seconds, and again until no row is inviting", async () => {
            vi.useFakeTimers();
            const fetcher = answers(controlOf(nova("inviting", 30)), controlOf(nova("inviting", 0)), controlOf());
            const { following, shown } = follower();

            await following.read();
            await vi.advanceTimersByTimeAsync(29_999);
            const before = fetcher.mock.calls.length;
            await vi.advanceTimersByTimeAsync(1);
            const afterTheRowsSeconds = fetcher.mock.calls.length;
            await vi.advanceTimersByTimeAsync(1_000);

            expect([before, afterTheRowsSeconds, fetcher.mock.calls.length]).toEqual([1, 2, 3]);
            expect(shown.at(-1)).toEqual(controlOf());
            await vi.advanceTimersByTimeAsync(600_000);
            expect(fetcher).toHaveBeenCalledTimes(3);
        });

        it("starts the wait afresh at every answer, so a read that comes sooner never doubles the timer", async () => {
            vi.useFakeTimers();
            const fetcher = answers(controlOf(nova("inviting", 30)), controlOf(nova("inviting", 30)), controlOf());
            const { following } = follower();

            await following.read();
            await vi.advanceTimersByTimeAsync(10_000);
            await following.read();
            await vi.advanceTimersByTimeAsync(29_999);
            const beforeTheSecondWaitEnds = fetcher.mock.calls.length;
            await vi.advanceTimersByTimeAsync(1);

            expect([beforeTheSecondWaitEnds, fetcher.mock.calls.length]).toEqual([2, 3]);
        });

        it("asks again after a failed read while a row was inviting, and keeps what it showed", async () => {
            vi.useFakeTimers();
            const fetcher = answers(controlOf(nova("inviting", 1)), new TypeError("offline"), controlOf());
            const { following, shown } = follower();

            await following.read();
            await vi.advanceTimersByTimeAsync(1_000);
            await vi.advanceTimersByTimeAsync(5_000);

            expect(fetcher).toHaveBeenCalledTimes(3);
            expect(shown).toEqual([controlOf(nova("inviting", 1)), controlOf()]);
        });

        it("asks again when the answer of an expiry read could not be read to its end", async () => {
            vi.useFakeTimers();
            const fetcher = vi.fn();
            fetcher.mockResolvedValueOnce(Response.json(controlOf(nova("inviting", 1))));
            fetcher.mockResolvedValueOnce(new Response(cutOff()));
            fetcher.mockResolvedValueOnce(Response.json(controlOf()));
            vi.stubGlobal("fetch", fetcher);
            const { following, shown } = follower();

            await following.read();
            await vi.advanceTimersByTimeAsync(1_000);
            await vi.advanceTimersByTimeAsync(5_000);

            expect(fetcher).toHaveBeenCalledTimes(3);
            expect(shown).toEqual([controlOf(nova("inviting", 1)), controlOf()]);
        });

        it("does not ask again after a failed read when no row was inviting", async () => {
            vi.useFakeTimers();
            const fetcher = answers(new TypeError("offline"));
            const { following } = follower();

            await following.read();
            await vi.advanceTimersByTimeAsync(600_000);

            expect(fetcher).toHaveBeenCalledTimes(1);
        });

        it("shows the control a call answers, with no refusal, and reads again when that row is inviting", async () => {
            vi.useFakeTimers();
            const fetcher = answers(controlOf(nova("inviting", 20)), controlOf());
            const { following, shown, refusals } = follower();

            await following.call("key-nova");
            await vi.advanceTimersByTimeAsync(20_000);

            expect(refusals).toEqual([null]);
            expect(shown).toEqual([controlOf(nova("inviting", 20)), controlOf()]);
            expect(fetcher).toHaveBeenCalledTimes(2);
        });

        it("shows the refusal of a call and reads the control afresh", async () => {
            const fetcher = vi.fn();
            fetcher.mockResolvedValueOnce(Response.json({ reason: "place-full" }, { status: 409 }));
            fetcher.mockResolvedValueOnce(Response.json(controlOf()));
            vi.stubGlobal("fetch", fetcher);
            const { following, shown, refusals } = follower();

            await following.call("key-nova");

            expect(refusals).toEqual([null, "place-full"]);
            expect(shown).toEqual([controlOf()]);
        });

        it("shows a call that could not be made as the try-again refusal", async () => {
            answerWith(new TypeError("offline"), Response.json(controlOf(nova("available"))));
            const { following, refusals } = follower();

            await following.call("key-nova");

            expect(refusals).toEqual([null, "try-again"]);
        });

        it("clears the refusal at the next call", async () => {
            answerWith(Response.json({ reason: "owner-absent" }, { status: 409 }), Response.json(controlOf()));
            const { following, refusals } = follower();
            await following.call("key-nova");
            answerWith(Response.json(controlOf(nova("inviting"))));

            await following.call("key-nova");

            expect(refusals).toEqual([null, "owner-absent", null]);
        });

        it("leaves a call to a table that is not there alone", async () => {
            answerWith(new Response(null, { status: 404 }));
            const { following, shown, refusals } = follower();

            await following.call("key-nova");

            expect([shown, refusals]).toEqual([[], [null]]);
        });

        describe("when requests overlap", () => {
            type Pending = { method: string; settle: (response: Response) => void };

            // Every request waits until the test answers it, as the server's answers arrive in any order.
            function slowServer() {
                const pending: Pending[] = [];
                const fetcher = vi.fn(
                    (_path: string, init?: RequestInit) =>
                        new Promise<Response>((settle) => pending.push({ method: init?.method ?? "GET", settle })),
                );
                vi.stubGlobal("fetch", fetcher);
                return { pending, fetcher };
            }

            // Answers the newest request first until none is left, as a server that is slower for the older one.
            async function answerNewestFirst(pending: Pending[], control: (method: string) => AgentsControl) {
                await vi.advanceTimersByTimeAsync(0);
                while (pending.length > 0) {
                    const newest = pending.pop();
                    newest?.settle(Response.json(control(newest.method)));
                    await vi.advanceTimersByTimeAsync(0);
                }
            }

            it("shows the answer of the later request last, and a row that ended starts no timer again", async () => {
                vi.useFakeTimers();
                const { pending, fetcher } = slowServer();
                const { following, shown } = follower();

                const calling = following.call("key-nova");
                const reading = following.read();
                await answerNewestFirst(pending, (method) =>
                    method === "POST" ? controlOf(nova("inviting", 120)) : controlOf(),
                );
                await Promise.all([calling, reading]);
                await vi.advanceTimersByTimeAsync(600_000);

                expect(shown.at(-1)).toEqual(controlOf());
                expect(fetcher).toHaveBeenCalledTimes(2);
            });

            it("keeps the inviting row a call answered when an older read answers after it", async () => {
                vi.useFakeTimers();
                const { pending, fetcher } = slowServer();
                const { following, shown } = follower();

                const reading = following.read();
                const calling = following.call("key-nova");
                await answerNewestFirst(pending, (method) =>
                    method === "POST" ? controlOf(nova("inviting", 30)) : controlOf(nova("available")),
                );
                await Promise.all([calling, reading]);
                await vi.advanceTimersByTimeAsync(30_000);

                expect(shown.at(-1)).toEqual(controlOf(nova("inviting", 30)));
                expect(fetcher).toHaveBeenCalledTimes(3);
            });
        });

        it("answers the next request after one whose display threw", async () => {
            const fetcher = answers(controlOf(nova("available")), controlOf());
            const shown: AgentsControl[] = [];
            const following = followAgents(
                TABLE_ID,
                (control) => {
                    shown.push(control);
                    if (shown.length === 1) throw new Error("the display failed");
                },
                () => undefined,
            );

            await expect(following.read()).rejects.toThrow("the display failed");
            await following.read();

            expect(shown).toEqual([controlOf(nova("available")), controlOf()]);
            expect(fetcher).toHaveBeenCalledTimes(2);
        });

        it("shows nothing after it was stopped, and reads no more", async () => {
            vi.useFakeTimers();
            const fetcher = answers(controlOf(nova("inviting", 5)), controlOf(), controlOf());
            const { following, shown } = follower();
            await following.read();

            following.stop();
            await vi.advanceTimersByTimeAsync(60_000);
            await following.read();
            await following.call("key-nova");

            expect(shown).toEqual([controlOf(nova("inviting", 5))]);
            expect(fetcher).toHaveBeenCalledTimes(3);
        });
    });
});

describe("the agent that sat down", () => {
    const chairOf = (seat: number, occupant_name: string | null, occupant_kind: Chair["occupant_kind"]): Chair => ({
        seat,
        occupant_name,
        occupant_kind,
        is_mine: false,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
    });
    const tableOf = (...chairs: Chair[]): Table => ({
        id: TABLE_ID,
        version: 1,
        chairs,
        watchers: 0,
        hand: null,
        result: null,
        passed_in: null,
        options: null,
        ended: null,
    });

    it("is named when a chair that was free now holds an agent", () => {
        const before = tableOf(chairOf(1, "Felix", "person"), chairOf(2, null, null));
        const after = tableOf(chairOf(1, "Felix", "person"), chairOf(2, "Nova", "agent"));

        expect(agentSitsNote(before, after)).toBe(words["table.agentSits"]({ name: "Nova" }));
    });

    it.each([
        ["a person sat down", chairOf(2, "Anna", "person")],
        ["the chair is still free", chairOf(2, null, null)],
        ["the agent sat there before", chairOf(2, "Nova", "agent")],
    ])("is nobody when %s", (_case, now) => {
        const sitting = _case === "the agent sat there before";
        const before = tableOf(
            chairOf(1, "Felix", "person"),
            sitting ? chairOf(2, "Nova", "agent") : chairOf(2, null, null),
        );

        expect(agentSitsNote(before, tableOf(chairOf(1, "Felix", "person"), now))).toBeNull();
    });
});
