import { describe, expect, it } from "vitest";
import { words } from "#lib/words.ts";
import {
    bidLineWhileDeclaring,
    declarerStage,
    togglePicked,
    type Auction,
    type Card,
    type Chair,
    type Declaring,
    type Stage,
    type Table,
} from "./tables.ts";

const TABLE_ID = "a".repeat(32);

const NO_PUSHES = { ramsch: false, pushing: null, pushes: 0, push_factor: 1 };

const auctionWith = (declared: Auction["declared"]): Auction => ({
    turn_seat: null,
    facing_seat: null,
    awaiting: null,
    standing: null,
    values: [],
    words: [],
    declared,
});

describe("what the declaring stage asks of this viewer", () => {
    const seats = (mine: number): Chair[] =>
        [1, 2, 3].map((seat) => ({
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
    const bidWon = { seat: 2, value: 20 };
    const tableWith = (declaring: Declaring | null, mine: number): Table => ({
        id: TABLE_ID,
        version: 1,
        chairs: seats(mine),
        watchers: 0,
        opened_by_me: false,
        result: null,
        passed_in: null,
        series: null,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
        hand: {
            dealer_seat: 1,
            own_cards: [],
            skat_count: 2,
            waiting_seat: null,
            abort: null,
            abortable: false,
            ...NO_PUSHES,
            auction: auctionWith(bidWon),
            declaring,
            playing: null,
        },
    });
    const tableAt = (stage: Stage, mine: number): Table =>
        tableWith({ declarer_seat: 2, stage, declaration: null, open_cards: [] }, mine);

    it.each<Stage>(["choosing", "discarding", "picked"])("asks the declarer to act at %s", (stage) => {
        expect(declarerStage(tableAt(stage, 2))).toBe(stage);
    });

    it("asks the declarer nothing once the game is declared", () => {
        expect(declarerStage(tableAt("declared", 2))).toBeNull();
    });

    it("asks nothing of a chair that did not win the auction", () => {
        expect(declarerStage(tableAt("choosing", 3))).toBeNull();
    });

    it("asks nothing of a person with no chair", () => {
        expect(declarerStage(tableAt("choosing", 0))).toBeNull();
    });

    it("asks nothing before the auction is over", () => {
        expect(declarerStage(tableWith(null, 2))).toBeNull();
    });

    it("asks nothing with no hand on the table", () => {
        expect(declarerStage({ ...tableAt("choosing", 2), hand: null })).toBeNull();
    });
});

describe("the auction's value while declaring", () => {
    const table = (declaring: Declaring | null, declared: Auction["declared"]): Table => ({
        id: TABLE_ID,
        version: 1,
        chairs: [],
        watchers: 0,
        opened_by_me: false,
        result: null,
        passed_in: null,
        series: null,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
        hand: {
            dealer_seat: 1,
            own_cards: [],
            skat_count: 2,
            waiting_seat: null,
            abort: null,
            abortable: false,
            ...NO_PUSHES,
            auction: auctionWith(declared),
            declaring,
            playing: null,
        },
    });

    it.each<Stage>(["choosing", "discarding", "picked"])("is shown at %s", (stage) => {
        expect(
            bidLineWhileDeclaring(
                table({ declarer_seat: 2, stage, declaration: null, open_cards: [] }, { seat: 2, value: 20 }),
            ),
        ).toBe(words["table.bidValue"]({ value: "20" }));
    });

    it.each([
        [
            "once the game is declared",
            {
                declarer_seat: 2,
                stage: "declared" as const,
                declaration: { game: "null" as const, hand: false, ouvert: false, announcement: "none" as const },
                open_cards: [],
            },
            { seat: 2, value: 20 },
        ],
        ["before the auction is over", null, null],
        [
            "with no value won",
            { declarer_seat: 2, stage: "choosing" as const, declaration: null, open_cards: [] },
            null,
        ],
    ])("is not shown %s", (_name, declaring, declared) => {
        expect(bidLineWhileDeclaring(table(declaring, declared))).toBeNull();
    });

    it("is not shown with no hand on the table", () => {
        expect(bidLineWhileDeclaring({ ...table(null, null), hand: null })).toBeNull();
    });
});

describe("picking two cards from the twelve", () => {
    const seven: Card = { suit: "karo", rank: "seven" };
    const eight: Card = { suit: "karo", rank: "eight" };
    const nine: Card = { suit: "karo", rank: "nine" };

    it("picks a card that was not picked", () => {
        expect(togglePicked([seven], eight)).toEqual([seven, eight]);
    });

    it("puts a picked card back", () => {
        expect(togglePicked([seven, eight], seven)).toEqual([eight]);
    });

    it("does not pick a third card while two are picked", () => {
        expect(togglePicked([seven, eight], nine)).toEqual([seven, eight]);
    });
});
