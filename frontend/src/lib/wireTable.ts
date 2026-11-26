import type { Auction, Hand, Series, Table } from "../routes/(start)/tables.ts";

// A series as the release before this one answers it: its proposal names the seat that accepted and has no instant, and
// it names no refusals. Both releases serve streams while one rolls out, so a table is read in either shape.
type WireProposal = {
    proposer_seat: number;
    agreed_seats?: number[];
    accepter_seat?: number | null;
    answer_by?: string | null;
};
type WireSeries = Omit<Series, "end_proposal" | "end_refused_seats" | "new_series_answer_by" | "next_settings"> & {
    end_proposal: WireProposal | null;
    end_refused_seats?: number[];
    new_series_answer_by?: string | null;
    next_settings?: Series["next_settings"];
};
// An auction as the release before answers it: it tells no steps, no plan and no hand values.
type OwnAuctionFields = "steps" | "plan" | "hand_values";
type WireAuction = Omit<Auction, OwnAuctionFields> & Partial<Pick<Auction, OwnAuctionFields>>;
type WireHand = Omit<Hand, "auction"> & { auction: WireAuction };
export type WireTable = Omit<Table, "series" | "hand"> & { series: WireSeries | null; hand: WireHand | null };

function agreedSeatsOf(proposal: WireProposal): number[] {
    if (proposal.agreed_seats !== undefined) return proposal.agreed_seats;
    const accepter = proposal.accepter_seat;
    return accepter === undefined || accepter === null ? [proposal.proposer_seat] : [proposal.proposer_seat, accepter];
}

function handOfWire(hand: WireHand | null): Hand | null {
    if (hand === null) return null;
    const { auction } = hand;
    return {
        ...hand,
        auction: {
            ...auction,
            steps: auction.steps ?? [],
            plan: auction.plan ?? null,
            hand_values: auction.hand_values ?? [],
        },
    };
}

export function tableOfWire(wire: WireTable): Table {
    const series = wire.series;
    const hand = handOfWire(wire.hand);
    if (series === null) return { ...wire, hand, series: null };
    const proposal = series.end_proposal;
    return {
        ...wire,
        hand,
        series: {
            ...series,
            end_proposal:
                proposal === null
                    ? null
                    : {
                          proposer_seat: proposal.proposer_seat,
                          agreed_seats: agreedSeatsOf(proposal),
                          answer_by: (proposal.answer_by ?? null) as string,
                      },
            end_refused_seats: series.end_refused_seats ?? [],
            new_series_answer_by: series.new_series_answer_by ?? null,
            next_settings: series.next_settings ?? null,
        },
    };
}
