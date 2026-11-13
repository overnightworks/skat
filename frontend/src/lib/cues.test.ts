import { describe, expect, it } from "vitest";
import { cuesBetween, type Cue } from "#lib/cues.ts";
import type {
    Auction,
    Card,
    Chair,
    Declaring,
    GiveUp,
    Playing,
    Position,
    SeatedCard,
    Table,
} from "../routes/(start)/tables.ts";

const FOREHAND = 1;
const MIDDLEHAND = 2;
const REARHAND = 3;
const KREUZ_KING: Card = { suit: "kreuz", rank: "king" };
const KREUZ_ACE: Card = { suit: "kreuz", rank: "ace" };
const HERZ_NINE: Card = { suit: "herz", rank: "nine" };
const PIK_TEN: Card = { suit: "pik", rank: "ten" };
const KARO_SEVEN: Card = { suit: "karo", rank: "seven" };
const KARO_EIGHT: Card = { suit: "karo", rank: "eight" };
const KARO_JACK: Card = { suit: "karo", rank: "jack" };

const EVERY_HAND_DEALT: [number, number, number] = [10, 10, 10];

function auction(): Auction {
    return {
        turn_seat: null,
        facing_seat: null,
        awaiting: null,
        standing: null,
        values: [],
        words: [],
        declared: null,
    };
}

function declaringAt(stage: Declaring["stage"]): Declaring {
    return { declarer_seat: MIDDLEHAND, stage, declaration: null, open_cards: [] };
}

const POSITIONS: Record<number, Position> = { 1: "forehand", 2: "middlehand", 3: "rearhand" };

function chairsWithCards(cards: [number, number, number]): Chair[] {
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
    }));
}

function playing(changes: Partial<Playing>): Playing {
    return {
        turn_seat: FOREHAND,
        current_trick: [],
        last_trick: null,
        legal_cards: [],
        running_points: null,
        give_up: null,
        kontra: null,
        ...changes,
    };
}

// A table of one hand: `current` and `last` are the playing state, `cards` the cards each chair still holds.
function table(
    version: number,
    cards: [number, number, number],
    changes: {
        declaring?: Declaring | null;
        current?: SeatedCard[];
        last?: Playing["last_trick"];
        giveUp?: GiveUp | null;
    } = {},
): Table {
    const hasPlaying = changes.current !== undefined || changes.last !== undefined;
    return {
        id: "a".repeat(32),
        version,
        chairs: chairsWithCards(cards),
        watchers: 0,
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
            auction: auction(),
            declaring: changes.declaring === undefined ? declaringAt("picked") : changes.declaring,
            playing: hasPlaying
                ? playing({
                      current_trick: changes.current ?? [],
                      last_trick: changes.last ?? null,
                      give_up: changes.giveUp ?? null,
                  })
                : null,
        },
        result: null,
        passed_in: null,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
    };
}

const FIRST_TRICK_LAST = {
    cards: [KREUZ_KING, HERZ_NINE, KREUZ_ACE],
    leader_seat: FOREHAND,
    taker_seat: MIDDLEHAND,
};

describe("the cards laid between two versions of a table", () => {
    it.each([
        {
            name: "a lead the page sees is the one card laid",
            previous: table(1, EVERY_HAND_DEALT, { current: [] }),
            next: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: KREUZ_KING }] }),
            laid: [{ seat: FOREHAND, card: KREUZ_KING }],
        },
        {
            name: "a card that joins the trick is the one card laid",
            previous: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: KREUZ_KING }] }),
            next: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            laid: [{ seat: MIDDLEHAND, card: HERZ_NINE }],
        },
        {
            name: "the card that completes a trick is laid and the trick stays on the felt",
            previous: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            next: table(4, [9, 9, 9], { current: [], last: FIRST_TRICK_LAST }),
            laid: [{ seat: REARHAND, card: KREUZ_ACE }],
        },
        {
            name: "the completing card and then the lead are laid, in that order, when both arrive together",
            previous: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            next: table(4, [9, 8, 9], {
                current: [{ seat: MIDDLEHAND, card: PIK_TEN }],
                last: { ...FIRST_TRICK_LAST, taker_seat: MIDDLEHAND },
            }),
            laid: [
                { seat: REARHAND, card: KREUZ_ACE },
                { seat: MIDDLEHAND, card: PIK_TEN },
            ],
        },
    ] satisfies { name: string; previous: Table; next: Table; laid: SeatedCard[] }[])(
        "$name",
        ({ previous, next, laid }) => {
            expect(cuesBetween(previous, next)).toEqual(
                laid.map(({ seat, card }) => ({ kind: "card-played", seat, card })),
            );
        },
    );

    it.each([
        {
            name: "two completed tricks that the page skipped lay nothing",
            previous: table(3, [8, 8, 8], { current: [], last: FIRST_TRICK_LAST }),
            next: table(5, [7, 7, 7], { current: [], last: { ...FIRST_TRICK_LAST, leader_seat: REARHAND } }),
        },
        {
            name: "the first lead of a new deal lays nothing",
            previous: table(4, [7, 7, 7], { current: [], last: FIRST_TRICK_LAST }),
            next: table(5, EVERY_HAND_DEALT, { current: [{ seat: FOREHAND, card: KARO_SEVEN }] }),
        },
        {
            name: "a change the hands do not explain lays nothing",
            previous: table(1, EVERY_HAND_DEALT, { current: [] }),
            next: table(2, EVERY_HAND_DEALT, { current: [{ seat: FOREHAND, card: KARO_EIGHT }] }),
        },
        {
            name: "a change that takes a card from a hand without laying it lays nothing",
            previous: table(1, EVERY_HAND_DEALT, { current: [] }),
            next: table(2, [9, 10, 10], { current: [] }),
        },
        {
            name: "an update that changes no card lays nothing",
            previous: table(1, [9, 10, 10], { current: [{ seat: FOREHAND, card: KARO_JACK }] }),
            next: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: KARO_JACK }] }),
        },
        {
            name: "a card swapped for another on the felt lays nothing",
            previous: table(1, [9, 10, 10], { current: [{ seat: FOREHAND, card: KREUZ_KING }] }),
            next: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: HERZ_NINE }] }),
        },
        {
            name: "a trick that completes from one card on the felt lays nothing",
            previous: table(3, [9, 10, 10], { current: [{ seat: FOREHAND, card: KREUZ_KING }] }),
            next: table(4, [9, 10, 9], { current: [], last: { ...FIRST_TRICK_LAST, cards: [KREUZ_KING, HERZ_NINE] } }),
        },
        {
            name: "a trick that completes without the cards on the felt lays nothing",
            previous: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            next: table(4, [9, 9, 9], {
                current: [],
                last: { ...FIRST_TRICK_LAST, cards: [HERZ_NINE, KREUZ_KING, KREUZ_ACE] },
            }),
        },
        {
            name: "a trick that completes with no card added lays nothing",
            previous: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            next: table(4, [9, 9, 10], { current: [], last: { ...FIRST_TRICK_LAST, cards: [KREUZ_KING, HERZ_NINE] } }),
        },
        {
            name: "a table with no playing before lays nothing",
            previous: table(1, EVERY_HAND_DEALT, { declaring: declaringAt("discarding") }),
            next: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: KARO_SEVEN }] }),
        },
    ] satisfies { name: string; previous: Table; next: Table }[])("$name", ({ previous, next }) => {
        expect(cuesBetween(previous, next)).toEqual([]);
    });

    it("lays nothing for a table that is not newer than the one before it", () => {
        const previous = table(4, [9, 10, 10], { current: [{ seat: FOREHAND, card: KARO_JACK }] });
        const sameVersion = table(4, [9, 9, 10], {
            current: [
                { seat: FOREHAND, card: KARO_JACK },
                { seat: MIDDLEHAND, card: KARO_SEVEN },
            ],
        });

        expect(cuesBetween(previous, sameVersion)).toEqual([]);
    });

    it("lays nothing on the first table of a page", () => {
        const first = table(4, [9, 9, 10], {
            current: [
                { seat: FOREHAND, card: KARO_JACK },
                { seat: MIDDLEHAND, card: KARO_SEVEN },
            ],
        });

        expect(cuesBetween(undefined, first)).toEqual([]);
    });
});

describe("the moment the auction ended", () => {
    const running = table(1, EVERY_HAND_DEALT, { declaring: null, current: undefined });
    const choosing = table(2, EVERY_HAND_DEALT, { declaring: declaringAt("choosing"), current: undefined });
    const ended: Cue = { kind: "auction-ended" };

    it("is the update that brings the declaring after a hand without one", () => {
        expect(cuesBetween(running, choosing)).toEqual([ended]);
    });

    it.each([
        { name: "the first answer of the page", previous: undefined, next: choosing },
        {
            name: "an update inside the declaring",
            previous: choosing,
            next: table(3, EVERY_HAND_DEALT, { declaring: declaringAt("discarding"), current: undefined }),
        },
        {
            name: "an update while the auction runs",
            previous: running,
            next: table(2, EVERY_HAND_DEALT, { declaring: null, current: undefined }),
        },
        { name: "a table with no hand yet", previous: { ...running, hand: null }, next: choosing },
    ] satisfies { name: string; previous: Table | undefined; next: Table }[])("is not $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).some((cue) => cue.kind === "auction-ended")).toBe(false);
    });
});

describe("the moment both opponents refused a give-up", () => {
    // The declarer at MIDDLEHAND asked and FOREHAND said no; REARHAND's no clears the request.
    const firstNo: GiveUp = { asking_seat: MIDDLEHAND, declined_seat: FOREHAND };
    const standing = table(5, [8, 8, 8], { current: [], giveUp: firstNo });
    const refused: Cue = { kind: "give-up-refused", seats: [FOREHAND, REARHAND] };

    it("is the update that clears the declarer's request after the first no and changes nothing else", () => {
        expect(cuesBetween(standing, table(6, [8, 8, 8], { current: [] }))).toEqual([refused]);
    });

    it.each([
        {
            name: "the first no, which keeps the request",
            previous: table(4, [8, 8, 8], { current: [], giveUp: { asking_seat: MIDDLEHAND, declined_seat: null } }),
            next: standing,
        },
        {
            name: "a card of the declarer, which takes the request back",
            previous: standing,
            next: table(6, [8, 7, 8], { current: [{ seat: MIDDLEHAND, card: KARO_JACK }] }),
        },
        {
            name: "a yes, which ends the hand",
            previous: standing,
            next: { ...table(6, [8, 8, 8]), hand: null },
        },
        {
            name: "a chair that changed hands",
            previous: standing,
            next: {
                ...table(6, [8, 8, 8], { current: [] }),
                chairs: chairsWithCards([8, 8, 8]).map((chair) =>
                    chair.seat === REARHAND ? { ...chair, occupant_name: "newcomer" } : chair,
                ),
            },
        },
        {
            name: "the declarer's no to an opponent's request",
            previous: table(4, [8, 8, 8], { current: [], giveUp: { asking_seat: FOREHAND, declined_seat: null } }),
            next: table(5, [8, 8, 8], { current: [] }),
        },
        {
            name: "a reload or a reconnect, which knows no table before",
            previous: undefined,
            next: table(6, [8, 8, 8], { current: [] }),
        },
        {
            name: "an update that keeps the request",
            previous: standing,
            next: table(6, [8, 8, 8], { current: [], giveUp: firstNo }),
        },
    ] satisfies { name: string; previous: Table | undefined; next: Table }[])("is not $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).some((cue) => cue.kind === "give-up-refused")).toBe(false);
    });
});
