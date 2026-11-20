import type { Series, Table } from "../routes/(start)/tables.ts";

// A series as the release before this one answers it: its proposal names the seat that accepted and has no instant, and
// it names no refusals. Both releases serve streams while one rolls out, so a table is read in either shape.
type WireProposal = {
    proposer_seat: number;
    agreed_seats?: number[];
    accepter_seat?: number | null;
    answer_by?: string | null;
};
type WireSeries = Omit<Series, "end_proposal" | "end_refused_seats" | "new_series_answer_by"> & {
    end_proposal: WireProposal | null;
    end_refused_seats?: number[];
    new_series_answer_by?: string | null;
};
export type WireTable = Omit<Table, "series"> & { series: WireSeries | null };

function agreedSeatsOf(proposal: WireProposal): number[] {
    if (proposal.agreed_seats !== undefined) return proposal.agreed_seats;
    const accepter = proposal.accepter_seat;
    return accepter === undefined || accepter === null ? [proposal.proposer_seat] : [proposal.proposer_seat, accepter];
}

export function tableOfWire(wire: WireTable): Table {
    const series = wire.series;
    if (series === null) return { ...wire, series: null };
    const proposal = series.end_proposal;
    return {
        ...wire,
        series: {
            ...series,
            end_proposal:
                proposal === null
                    ? null
                    : {
                          proposer_seat: proposal.proposer_seat,
                          agreed_seats: agreedSeatsOf(proposal),
                          answer_by: proposal.answer_by ?? null,
                      },
            end_refused_seats: series.end_refused_seats ?? [],
            new_series_answer_by: series.new_series_answer_by ?? null,
        },
    };
}
