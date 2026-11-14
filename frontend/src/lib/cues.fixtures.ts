import type {
    Auction,
    AuctionWord,
    Chair,
    Declaring,
    GiveUp,
    Kontra,
    Playing,
    Position,
    SeatedCard,
    Table,
} from "../routes/(start)/tables.ts";

export const FOREHAND = 1;
export const MIDDLEHAND = 2;
export const REARHAND = 3;

export const EVERY_HAND_DEALT: [number, number, number] = [10, 10, 10];

export function auction(spoken: AuctionWord[] = []): Auction {
    return {
        turn_seat: null,
        facing_seat: null,
        awaiting: null,
        standing: null,
        values: [],
        words: spoken,
        declared: null,
    };
}

export function declaringAt(stage: Declaring["stage"]): Declaring {
    return { declarer_seat: MIDDLEHAND, stage, declaration: null, open_cards: [] };
}

const POSITIONS: Record<number, Position> = { 1: "forehand", 2: "middlehand", 3: "rearhand" };

export function chairsWithCards(cards: [number, number, number]): Chair[] {
    return [FOREHAND, MIDDLEHAND, REARHAND].map((seat, index) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: false,
        is_away: false,
        ready: false,
        total: null,
        hand: { position: POSITIONS[seat] as Position, card_count: cards[index] as number },
        former_holder_name: null,
        is_mine_to_return: false,
        nudge: null,
    }));
}

// The table with the nudges `seat` has had at its version; `byName` is read in the nudged seat's own answer only.
export function nudged(source: Table, seat: number, nudges: number, byName: string | null = null): Table {
    return {
        ...source,
        chairs: source.chairs.map((chair) =>
            chair.seat === seat ? { ...chair, nudge: { nudges, may_nudge: false, by_name: byName } } : chair,
        ),
    };
}

export function playing(changes: Partial<Playing>): Playing {
    return {
        turn_seat: FOREHAND,
        current_trick: [],
        last_trick: null,
        taken: [
            { seat: 1, tricks: 0 },
            { seat: 2, tricks: 0 },
            { seat: 3, tricks: 0 },
        ],
        legal_cards: [],
        running_points: null,
        give_up: null,
        kontra: null,
        ...changes,
    };
}

// A table of one hand: `current` and `last` are the playing state, `cards` the cards each chair still holds.
export function table(
    version: number,
    cards: [number, number, number],
    changes: {
        declaring?: Declaring | null;
        current?: SeatedCard[];
        last?: Playing["last_trick"];
        giveUp?: GiveUp | null;
        spoken?: AuctionWord[];
        kontra?: Kontra | null;
    } = {},
): Table {
    const hasPlaying = changes.current !== undefined || changes.last !== undefined || changes.kontra !== undefined;
    return {
        id: "a".repeat(32),
        version,
        chairs: chairsWithCards(cards),
        watchers: 0,
        opened_by_me: false,
        hand: {
            dealer_seat: REARHAND,
            own_cards: [],
            skat_count: 2,
            waiting_seat: null,
            abort: null,
            abortable: false,
            ramsch: false,
            pushing: null,
            pushes: 0,
            push_factor: 1,
            auction: auction(changes.spoken),
            declaring: changes.declaring === undefined ? declaringAt("picked") : changes.declaring,
            playing: hasPlaying
                ? playing({
                      current_trick: changes.current ?? [],
                      last_trick: changes.last ?? null,
                      give_up: changes.giveUp ?? null,
                      kontra: changes.kontra ?? null,
                  })
                : null,
        },
        result: null,
        passed_in: null,
        series: null,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
    };
}
