import { describe, expect, it } from "vitest";
import { tableOfWire, type WireTable } from "#lib/wireTable.ts";
import { EVERY_HAND_DEALT, table as dealtTable } from "#lib/cues.fixtures.ts";
import { seriesAt, tableBetweenGames } from "#lib/series.fixtures.ts";

const ANSWER_BY = "2026-11-19T12:01:00Z";

// The table the release before sends: its series has no refusals and its proposal an accepter instead of the yes list.
function olderTable(proposal: { proposer_seat: number; accepter_seat: number | null } | null): WireTable {
    const series = { number: 1, game_number: 8, game_count: 36, over: false, standings: null, end_proposal: proposal };
    return { ...tableBetweenGames(1, null), series };
}

describe("tableOfWire", () => {
    it("keeps a table of this release as it is", () => {
        const table = tableBetweenGames(
            1,
            seriesAt({ end_proposal: { proposer_seat: 1, agreed_seats: [1, 2], answer_by: ANSWER_BY } }),
        );

        expect(tableOfWire(table)).toEqual(table);
    });

    it("keeps a table without a series", () => {
        expect(tableOfWire(tableBetweenGames(1, null)).series).toBeNull();
    });

    it("keeps a dealt table of this release as it is", () => {
        const table = dealtTable(1, EVERY_HAND_DEALT, { spoken: [{ seat: 2, action: "bid", value: 18 }] });

        expect(tableOfWire(table)).toEqual(table);
    });

    it("reads an auction of the release before as one that tells no steps, no plan and no hand values", () => {
        const table = dealtTable(1, EVERY_HAND_DEALT);
        const older = { ...table.hand?.auction, steps: undefined, plan: undefined, hand_values: undefined };
        const sent = JSON.parse(JSON.stringify({ ...table, hand: { ...table.hand, auction: older } })) as WireTable;

        expect(tableOfWire(sent)).toEqual(table);
    });

    it("reads a series of the release before without a proposal as one with no refusals and no minute running", () => {
        const series = tableOfWire(olderTable(null)).series;

        expect([
            series?.end_proposal,
            series?.end_refused_seats,
            series?.new_series_answer_by,
            series?.next_settings,
        ]).toEqual([null, [], null, null]);
    });

    it.each([
        { name: "the proposer alone", accepter_seat: null, agreed: [1] },
        { name: "the proposer and the one who accepted", accepter_seat: 3, agreed: [1, 3] },
    ])(
        "reads a proposal of the release before with $name as a proposal with no minute",
        ({ accepter_seat, agreed }) => {
            const series = tableOfWire(olderTable({ proposer_seat: 1, accepter_seat })).series;

            expect(series?.end_proposal).toEqual({ proposer_seat: 1, agreed_seats: agreed, answer_by: null });
        },
    );
});
