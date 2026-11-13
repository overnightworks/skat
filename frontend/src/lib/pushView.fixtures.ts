import type { Card, Chair, Hand, Options, Pushing, Stage, Table } from "../routes/(start)/tables.ts";

type GrandHand = NonNullable<NonNullable<NonNullable<Options["ramsch"]>["pushing"]>["grand_hand"]>;

export const FOREHAND = 1;
export const MIDDLEHAND = 2;
export const WATCHER = 0;
export const CLUBS_JACK: Card = { suit: "kreuz", rank: "jack" };
export const CLUBS_SEVEN: Card = { suit: "kreuz", rank: "seven" };

function chairs(mine: number): Chair[] {
    return [FOREHAND, MIDDLEHAND, 3].map((seat) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === mine,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
        former_holder_name: null,
        is_mine_to_return: false,
    }));
}

export function table(
    mine: number,
    stage: Stage,
    changes: Partial<Hand> = {},
    grandHand: GrandHand | null = null,
): Table {
    const pushing: Pushing = {
        turn_seat: FOREHAND,
        stage,
        moves: [],
        factor: 1,
        put_back_cards: stage === "discarding" ? [CLUBS_SEVEN] : [],
    };
    return {
        id: "a".repeat(32),
        version: 1,
        chairs: chairs(mine),
        watchers: 0,
        opened_by_me: false,
        result: null,
        passed_in: null,
        series: null,
        aborted: null,
        bock: null,
        ended: null,
        options: {
            show_running_points: false,
            kontra: null,
            bock: null,
            ramsch:
                grandHand === null
                    ? null
                    : {
                          scoring: "points",
                          jungfrau: "doubles-loser",
                          durchmarsch: "wins-120",
                          pushing: { rule: "jacks-stay", grand_hand: grandHand },
                      },
        },
        hand: {
            dealer_seat: 3,
            own_cards: [],
            skat_count: 2,
            waiting_seat: null,
            abort: null,
            abortable: false,
            auction: {
                turn_seat: null,
                facing_seat: null,
                awaiting: null,
                standing: null,
                values: [],
                words: [],
                declared: null,
            },
            declaring: null,
            playing: null,
            ramsch: true,
            pushing,
            pushes: 0,
            push_factor: 1,
            ...changes,
        },
    };
}
