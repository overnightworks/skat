import { afterEach, describe, expect, it, vi } from "vitest";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { words } from "#lib/words.ts";
import { TABLE_NUDGE_SUFFIX, TABLES_PATH } from "#lib/wire.ts";
import { nudgedNote, nudgeSeat, type Chair, type Nudge, type Table } from "./tables.ts";

const OWN_SEAT = 1;
const AWAITED_SEAT = 2;

const chairOf = (seat: number, nudge: Nudge | null): Chair => ({
    seat,
    occupant_name: seat === OWN_SEAT ? "Felix" : "Nova",
    occupant_kind: "person",
    is_mine: seat === OWN_SEAT,
    is_away: false,
    ready: false,
    total: null,
    hand: null,
    former_holder_name: null,
    is_mine_to_return: false,
    nudge,
});
const tableAt = (version: number, ownNudge: Nudge | null): Table => ({
    id: TABLE_ID,
    version,
    chairs: [chairOf(OWN_SEAT, ownNudge), chairOf(AWAITED_SEAT, null)],
    watchers: 0,
    opened_by_me: false,
    hand: null,
    result: null,
    passed_in: null,
    series: null,
    aborted: null,
    options: null,
    bock: null,
    ended: null,
});
const nudgedBy = (name: string, nudges = 1): Nudge => ({ nudges, may_nudge: false, by_name: name });

describe("a nudge sent from the page", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("posts the version, the seat and the nudges the page saw to the table's nudge path", async () => {
        const fetcher = vi.fn().mockResolvedValue(Response.json(tableAt(4, null)));
        vi.stubGlobal("fetch", fetcher);

        await nudgeSeat(TABLE_ID, 4, AWAITED_SEAT, 1);

        const [path, init] = fetcher.mock.calls[0] as [string, RequestInit];
        expect([path, init.method, JSON.parse(init.body as string)]).toEqual([
            `${TABLES_PATH}/${TABLE_ID}${TABLE_NUDGE_SUFFIX}`,
            "POST",
            { version: 4, seat: AWAITED_SEAT, nudges: 1 },
        ]);
    });

    it("is answered as a failure, never as a note, when the server refuses it as too early", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ reason: "too-early" }, { status: 409 })));

        expect(await nudgeSeat(TABLE_ID, 4, AWAITED_SEAT, 0)).toEqual({ kind: "failed" });
    });
});

describe("the note of a nudge of the viewer's own chair", () => {
    const stroke = (name: string) => ({
        text: `${name} ${words["table.nudgesYou"]}`,
        initials: [name.slice(0, 1)],
        seat: null,
        occupied: false,
    });

    it.each([
        ["the first nudge arrives", tableAt(4, null), tableAt(4, nudgedBy("Anna")), "Anna"],
        ["a second nudge arrives", tableAt(4, nudgedBy("Anna")), tableAt(4, nudgedBy("Ben", 2)), "Ben"],
        ["a nudge arrives at the next version", tableAt(4, nudgedBy("Anna")), tableAt(5, nudgedBy("Ben")), "Ben"],
    ])("names the nudger when %s", (_case, before, after, name) => {
        expect(nudgedNote(before, after)).toEqual(stroke(name));
    });

    it.each([
        ["nobody nudged", tableAt(4, null), tableAt(4, null)],
        ["the nudge was already seen", tableAt(4, nudgedBy("Anna")), tableAt(5, null)],
        ["the table moved without a nudge", tableAt(4, nudgedBy("Anna")), tableAt(4, nudgedBy("Anna"))],
    ])("is nothing when %s", (_case, before, after) => {
        expect(nudgedNote(before, after)).toBeNull();
    });
});
