import type { Chair, GiveUp, Table, Word } from "../routes/(start)/tables.ts";

export const DECLARER = 2;
export const FIRST_OPPONENT = 1;
export const SECOND_OPPONENT = 3;
export const WATCHER = 0;

function chairs(mine: number): Chair[] {
    return [1, 2, 3].map((seat) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === mine,
        is_away: false,
        ready: false,
        total: null,
        hand: { position: "forehand", card_count: 9 },
        former_holder_name: null,
        is_mine_to_return: false,
    }));
}

// A declared game in play at which `request` stands, seen by the chair `mine` (0 is a watcher's).
export function tableWith(
    mine: number,
    request: GiveUp | null,
    changes: { waiting?: number; ramsch?: boolean; kontraWord?: Word; grandHandInRamsch?: boolean } = {},
): Table {
    return {
        id: "a".repeat(32),
        version: 7,
        chairs: chairs(mine),
        watchers: 0,
        result: null,
        passed_in: null,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
        hand: {
            dealer_seat: 3,
            own_cards: [],
            skat_count: 2,
            waiting_seat: changes.waiting ?? null,
            abort: null,
            abortable: changes.waiting !== undefined,
            ramsch: changes.ramsch === true || changes.grandHandInRamsch === true,
            pushing: null,
            pushes: 0,
            push_factor: 1,
            auction: {
                turn_seat: null,
                facing_seat: null,
                awaiting: null,
                standing: null,
                values: [],
                words: [],
                declared: null,
            },
            declaring:
                changes.ramsch === true
                    ? null
                    : {
                          declarer_seat: DECLARER,
                          stage: "declared",
                          declaration: { game: "kreuz", hand: false, ouvert: false, announcement: "none" },
                          open_cards: [],
                      },
            playing: {
                turn_seat: 1,
                current_trick: [],
                last_trick: null,
                legal_cards: [],
                running_points: null,
                give_up: request,
                kontra: changes.kontraWord ? { said: [], factor: 1, my_word: changes.kontraWord } : null,
            },
        },
    };
}
