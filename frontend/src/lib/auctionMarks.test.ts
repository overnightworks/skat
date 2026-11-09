import { describe, expect, it } from "vitest";
import {
    auctionJustEnded,
    awayOnTurn,
    chairMarks,
    decidingMarks,
    decidingPlaque,
    passedInScene,
    type ChairMarks,
} from "#lib/auctionMarks.ts";
import type { Auction, Chair, Declaring, PassedIn, Stage, Table } from "../routes/(start)/tables.ts";

const FOREHAND = 1;
const MIDDLEHAND = 2;
const REARHAND = 3;
const WATCHER = undefined;
const NO_MARKS: ChairMarks = { bubble: null, passed: false, turn: false, waits: false, declarer: null };

function auction(changes: Partial<Auction>): Auction {
    return {
        turn_seat: MIDDLEHAND,
        facing_seat: FOREHAND,
        awaiting: "bid",
        standing: null,
        values: [],
        words: [],
        declared: null,
        ...changes,
    };
}

const middlehandBid18 = auction({
    turn_seat: FOREHAND,
    facing_seat: MIDDLEHAND,
    awaiting: "answer",
    standing: 18,
    words: [{ seat: MIDDLEHAND, action: "bid", value: 18 }],
});

describe("the marks on a chair during the auction", () => {
    it.each([
        {
            name: "a bid is the loud bubble with its value",
            state: middlehandBid18,
            seat: MIDDLEHAND,
            marks: { bubble: { kind: "bid", value: 18 } },
        },
        {
            name: "a hold is the quiet bubble with the value it held",
            state: auction({ standing: 18, words: [{ seat: FOREHAND, action: "hold", value: 18 }] }),
            seat: FOREHAND,
            marks: { bubble: { kind: "hold", value: 18 } },
        },
        {
            name: "a pass greys the chair and drops its bubble",
            state: auction({ turn_seat: REARHAND, words: [{ seat: MIDDLEHAND, action: "pass", value: null }] }),
            seat: MIDDLEHAND,
            marks: { passed: true },
        },
        {
            name: "a chair that has not spoken carries nothing",
            state: auction({}),
            seat: REARHAND,
            marks: {},
        },
    ] satisfies { name: string; state: Auction; seat: number; marks: Partial<ChairMarks> }[])(
        "$name for every viewer but the one on turn",
        ({ state, seat, marks }) => {
            for (const viewer of [FOREHAND, MIDDLEHAND, REARHAND, WATCHER].filter((one) => one !== state.turn_seat)) {
                expect(chairMarks(state, seat, viewer)).toEqual({ ...NO_MARKS, ...marks });
            }
        },
    );

    it("puts the turn mark on exactly the chair on turn for every viewer", () => {
        for (const viewer of [FOREHAND, MIDDLEHAND, REARHAND, WATCHER]) {
            const onTurn = [FOREHAND, MIDDLEHAND, REARHAND].filter(
                (seat) => chairMarks(middlehandBid18, seat, viewer).turn,
            );
            expect(onTurn).toEqual([FOREHAND]);
        }
    });

    it("shows only the last word of a chair", () => {
        const state = auction({
            standing: 23,
            words: [
                { seat: FOREHAND, action: "hold", value: 20 },
                { seat: MIDDLEHAND, action: "bid", value: 23 },
            ],
            turn_seat: FOREHAND,
            facing_seat: MIDDLEHAND,
            awaiting: "answer",
        });

        expect(chairMarks(state, MIDDLEHAND, WATCHER).bubble).toEqual({ kind: "bid", value: 23 });
        expect(chairMarks(state, FOREHAND, WATCHER).bubble).toEqual({ kind: "hold", value: 20 });
    });

    it.each([
        { name: "the forehand answering a bid sees the bidder wait", state: middlehandBid18, viewer: FOREHAND },
        {
            name: "the rearhand bidding against the forehand sees the forehand wait",
            state: auction({
                turn_seat: REARHAND,
                facing_seat: FOREHAND,
                words: [{ seat: MIDDLEHAND, action: "pass", value: null }],
            }),
            viewer: REARHAND,
        },
    ] satisfies { name: string; state: Auction; viewer: number }[])("$name", ({ state, viewer }) => {
        const waiting = [FOREHAND, MIDDLEHAND, REARHAND].filter((seat) => chairMarks(state, seat, viewer).waits);

        expect(waiting).toEqual([state.facing_seat]);
    });

    it("shows the waits mark to nobody but the player on turn", () => {
        const state = middlehandBid18;

        for (const viewer of [MIDDLEHAND, REARHAND, WATCHER]) {
            for (const seat of [FOREHAND, MIDDLEHAND, REARHAND]) {
                expect(chairMarks(state, seat, viewer).waits).toBe(false);
            }
        }
    });

    it("shows no waits mark when the forehand takes 18 alone after two passes", () => {
        const state = auction({
            turn_seat: FOREHAND,
            facing_seat: null,
            awaiting: "play",
            words: [
                { seat: MIDDLEHAND, action: "pass", value: null },
                { seat: REARHAND, action: "pass", value: null },
            ],
        });

        for (const viewer of [FOREHAND, MIDDLEHAND, REARHAND, WATCHER]) {
            const marks = [FOREHAND, MIDDLEHAND, REARHAND].map((seat) => chairMarks(state, seat, viewer));
            expect(marks.filter(({ waits }) => waits)).toEqual([]);
            expect(marks.filter(({ passed }) => passed)).toHaveLength(2);
        }
    });

    it("draws nothing once the auction is over", () => {
        const state = auction({
            turn_seat: null,
            facing_seat: null,
            awaiting: null,
            standing: 18,
            words: [
                { seat: MIDDLEHAND, action: "bid", value: 18 },
                { seat: FOREHAND, action: "pass", value: null },
                { seat: REARHAND, action: "pass", value: null },
            ],
            declared: { seat: MIDDLEHAND, value: 18 },
        });

        for (const seat of [FOREHAND, MIDDLEHAND, REARHAND]) {
            expect(chairMarks(state, seat, MIDDLEHAND)).toEqual(NO_MARKS);
        }
    });

    it("draws nothing before a deal", () => {
        expect(chairMarks(undefined, FOREHAND, FOREHAND)).toEqual(NO_MARKS);
    });

    it("draws no bubble for the forehand's word to play at 18", () => {
        const state = auction({ words: [{ seat: FOREHAND, action: "play", value: 18 }] });

        expect(chairMarks(state, FOREHAND, WATCHER)).toEqual(NO_MARKS);
    });
});

function chair(seat: number, changes: Partial<Chair> = {}): Chair {
    return { seat, occupant_name: `player-${String(seat)}`, is_mine: false, is_away: false, hand: null, ...changes };
}

describe("whom the plaque waits for", () => {
    it("names the player on turn while they are away", () => {
        const chairs = [chair(FOREHAND), chair(MIDDLEHAND, { occupant_name: "Anna", is_away: true }), chair(REARHAND)];

        expect(awayOnTurn(auction({}), chairs)).toBe("Anna");
    });

    it.each([
        { name: "the player on turn is there", chairs: [chair(MIDDLEHAND), chair(FOREHAND, { is_away: true })] },
        { name: "nobody is on turn", chairs: [chair(MIDDLEHAND, { is_away: true })], changes: { turn_seat: null } },
    ] satisfies { name: string; chairs: Chair[]; changes?: Partial<Auction> }[])(
        "waits for nobody when $name",
        ({ chairs, changes }) => {
            expect(awayOnTurn(auction(changes ?? {}), chairs)).toBeNull();
        },
    );
});

describe("the scene of a passed-in hand", () => {
    const chairOf = (seat: number, changes: Partial<Chair> = {}): Chair => ({
        seat,
        occupant_name: `Name${String(seat)}`,
        is_mine: false,
        is_away: false,
        hand: null,
        ...changes,
    });
    const all = [chairOf(FOREHAND), chairOf(MIDDLEHAND), chairOf(REARHAND)];

    it("is nothing while no hand was passed in", () => {
        expect(passedInScene(null, all)).toBeNull();
    });

    it("names the next dealer when all three are there", () => {
        const passedIn: PassedIn = { next_dealer_seat: MIDDLEHAND };

        expect(passedInScene(passedIn, all)).toEqual({ dealerSeat: MIDDLEHAND, dealerName: "Name2" });
    });

    it("names nobody while an occupied chair is away", () => {
        const chairs = [chairOf(FOREHAND), chairOf(MIDDLEHAND, { is_away: true }), chairOf(REARHAND)];

        expect(passedInScene({ next_dealer_seat: REARHAND }, chairs)).toEqual({ dealerSeat: null, dealerName: null });
    });

    it("names nobody while the answer names no dealer", () => {
        const chairs = [chairOf(FOREHAND), chairOf(MIDDLEHAND, { occupant_name: null }), chairOf(REARHAND)];

        expect(passedInScene({ next_dealer_seat: null }, chairs)).toEqual({ dealerSeat: null, dealerName: null });
    });
});

describe("what the others see while the declarer decides", () => {
    const BID_WON = 23;
    const chairsAt = (mine: number | null, changes: Partial<Chair> = {}): Chair[] =>
        [FOREHAND, MIDDLEHAND, REARHAND].map((seat) => ({
            seat,
            occupant_name: `Name${String(seat)}`,
            is_mine: seat === mine,
            is_away: false,
            hand: null,
            ...(seat === MIDDLEHAND ? changes : {}),
        }));
    const tableAt = (
        declaring: Declaring | null,
        mine: number | null,
        declared: Auction["declared"] = { seat: MIDDLEHAND, value: BID_WON },
        chairChanges: Partial<Chair> = {},
    ): Table => ({
        id: "table",
        version: 1,
        chairs: chairsAt(mine, chairChanges),
        watchers: 0,
        passed_in: null,
        hand: {
            dealer_seat: FOREHAND,
            own_cards: [],
            skat_count: 2,
            auction: auction({ awaiting: null, turn_seat: null, facing_seat: null, declared }),
            declaring,
            playing: null,
        },
    });
    const declaringAt = (stage: Stage): Declaring => ({ declarer_seat: MIDDLEHAND, stage, declaration: null });

    describe("the plaque", () => {
        it.each([
            {
                name: "the moment the auction ended names the winner and the value",
                stage: "choosing",
                justWon: true,
                kind: "won",
            },
            { name: "the choosing names the winner as choosing", stage: "choosing", justWon: false, kind: "choosing" },
            {
                name: "the discarding names the winner as discarding",
                stage: "discarding",
                justWon: false,
                kind: "discarding",
            },
            {
                name: "the wait after the put-back is still the discarding",
                stage: "picked",
                justWon: false,
                kind: "discarding",
            },
        ] satisfies { name: string; stage: Stage; justWon: boolean; kind: string }[])(
            "reads $name for an opponent and a watcher",
            ({ stage, justWon, kind }) => {
                for (const mine of [FOREHAND, REARHAND, null]) {
                    expect(decidingPlaque(tableAt(declaringAt(stage), mine), justWon)).toEqual({
                        kind,
                        name: `Name${String(MIDDLEHAND)}`,
                        value: BID_WON,
                    });
                }
            },
        );

        it("is left to the declarer's own view for the declarer", () => {
            expect(decidingPlaque(tableAt(declaringAt("choosing"), MIDDLEHAND), false)).toBeNull();
        });

        it("is nothing once the game is declared", () => {
            expect(decidingPlaque(tableAt(declaringAt("declared"), FOREHAND), false)).toBeNull();
        });

        it("is nothing before the auction is over", () => {
            expect(decidingPlaque(tableAt(null, FOREHAND), false)).toBeNull();
        });

        it("is nothing with no hand on the table", () => {
            expect(decidingPlaque({ ...tableAt(null, FOREHAND), hand: null }, false)).toBeNull();
        });

        it("is nothing while the answer names no value won", () => {
            expect(decidingPlaque(tableAt(declaringAt("choosing"), FOREHAND, null), false)).toBeNull();
        });

        it("is nothing while the declarer's chair has no name", () => {
            expect(
                decidingPlaque(tableAt(declaringAt("choosing"), FOREHAND, undefined, { occupant_name: null }), false),
            ).toBeNull();
        });
    });

    describe("the marks", () => {
        it.each<Stage>(["choosing", "discarding", "picked"])(
            "put the declarer's mark and the turn on the declarer alone at %s",
            (stage) => {
                const declaring = declaringAt(stage);

                expect(decidingMarks(declaring, MIDDLEHAND, false)).toEqual({
                    ...NO_MARKS,
                    declarer: "decl",
                    turn: true,
                });
                for (const seat of [FOREHAND, REARHAND]) {
                    expect(decidingMarks(declaring, seat, false)).toEqual(NO_MARKS);
                }
            },
        );

        it("slams the won mark on the declarer and marks the two others out at the moment the auction ended", () => {
            const declaring = declaringAt("choosing");

            expect(decidingMarks(declaring, MIDDLEHAND, true)).toEqual({ ...NO_MARKS, declarer: "won", turn: true });
            for (const seat of [FOREHAND, REARHAND]) {
                expect(decidingMarks(declaring, seat, true)).toEqual({ ...NO_MARKS, passed: true });
            }
        });

        it("are nothing once the game is declared", () => {
            expect(decidingMarks(declaringAt("declared"), MIDDLEHAND, true)).toEqual(NO_MARKS);
        });

        it("keep the declarer's plain mark after the choosing even while the moment lasts", () => {
            expect(decidingMarks(declaringAt("discarding"), MIDDLEHAND, true).declarer).toBe("decl");
            expect(decidingMarks(declaringAt("discarding"), FOREHAND, true).passed).toBe(false);
        });
    });

    describe("the moment the auction ended", () => {
        const running = tableAt(null, FOREHAND);
        const choosing = tableAt(declaringAt("choosing"), FOREHAND);

        it("is the update that brings the declaring after a hand without one", () => {
            expect(auctionJustEnded(running, choosing)).toBe(true);
        });

        it.each([
            { name: "the first answer of the page", previous: undefined, next: choosing },
            {
                name: "an update inside the declaring",
                previous: choosing,
                next: tableAt(declaringAt("discarding"), FOREHAND),
            },
            { name: "an update while the auction runs", previous: running, next: running },
            { name: "a table with no hand yet", previous: { ...running, hand: null }, next: choosing },
        ] satisfies { name: string; previous: Table | undefined; next: Table }[])(
            "is not $name",
            ({ previous, next }) => {
                expect(auctionJustEnded(previous, next)).toBe(false);
            },
        );
    });
});
