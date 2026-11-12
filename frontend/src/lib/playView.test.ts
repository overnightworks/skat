import { describe, expect, it } from "vitest";
import { cardLook, cardsToPlay, gameInPlay, sideNames, trickOnTheFelt, type PlayingHand } from "#lib/playView.ts";
import { words } from "#lib/words.ts";
import type { Card, Chair, Playing, Position, Table } from "../routes/(start)/tables.ts";

const KARO_SEVEN: Card = { suit: "karo", rank: "seven" };
const KARO_ACE: Card = { suit: "karo", rank: "ace" };
const HERZ_TEN: Card = { suit: "herz", rank: "ten" };
const WATCHER = 0;
const DECLARER_SEAT = 2;

// Seat 3 deals, so seat 1 is forehand, seat 2 middlehand and seat 3 rearhand.
const POSITIONS: Record<number, Position> = { 1: "forehand", 2: "middlehand", 3: "rearhand" };
const SEAT_TWO_DEALS: Record<number, Position> = { 1: "middlehand", 2: "rearhand", 3: "forehand" };

function chairs(mine: number, positions: Record<number, Position> = POSITIONS): Chair[] {
    return [1, 2, 3].map((seat) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === mine,
        is_away: false,
        ready: false,
        total: null,
        hand: { position: positions[seat] as Position, card_count: 9 },
    }));
}

function playing(changes: Partial<Playing>): Playing {
    return {
        turn_seat: 1,
        current_trick: [],
        last_trick: null,
        legal_cards: [],
        give_up: null,
        kontra: null,
        ...changes,
    };
}

function table(mine: number, changes: Partial<Playing> | null): Table {
    return {
        id: "a".repeat(32),
        version: 7,
        chairs: chairs(mine),
        watchers: 0,
        result: null,
        hand: {
            dealer_seat: 3,
            own_cards: [],
            skat_count: 2,
            waiting_seat: null,
            auction: {
                turn_seat: null,
                facing_seat: null,
                awaiting: null,
                standing: null,
                values: [],
                words: [],
                declared: null,
            },
            declaring: {
                declarer_seat: DECLARER_SEAT,
                stage: "declared",
                declaration: { game: "null", hand: true, ouvert: false, announcement: "none" },
                open_cards: [],
            },
            playing: changes === null ? null : playing(changes),
        },
        passed_in: null,
        ended: null,
    };
}

describe("the trick on the felt", () => {
    const twoCards = playing({
        current_trick: [
            { seat: 1, card: KARO_SEVEN },
            { seat: 2, card: KARO_ACE },
        ],
    });

    it.each([
        { viewer: 2, slots: { 1: "right", 2: "near" } },
        { viewer: 1, slots: { 1: "near", 2: "left" } },
        { viewer: WATCHER, slots: { 1: "left", 2: "right" } },
    ])("lays each card at its player's side as viewer $viewer sees the chairs", ({ viewer, slots }) => {
        const laid = trickOnTheFelt(chairs(viewer), twoCards);

        expect(laid.map(({ seat, slot }) => [seat, slot])).toEqual([
            [1, slots[1]],
            [2, slots[2]],
        ]);
    });

    it("tags each card with its player's name", () => {
        expect(trickOnTheFelt(chairs(WATCHER), twoCards).map(({ name, card }) => [name, card])).toEqual([
            ["player 1", KARO_SEVEN],
            ["player 2", KARO_ACE],
        ]);
    });

    it.each([
        { leader: 1, positions: POSITIONS, seats: [1, 2, 3] },
        { leader: 2, positions: POSITIONS, seats: [2, 3, 1] },
        { leader: 3, positions: POSITIONS, seats: [3, 1, 2] },
        {
            leader: 3,
            positions: SEAT_TWO_DEALS,
            seats: [3, 1, 2],
        },
    ])(
        "keeps the last trick in turn from its leader, seat $leader, until the next card is led",
        ({ leader, positions, seats }) => {
            const last = playing({
                last_trick: { cards: [KARO_SEVEN, KARO_ACE, HERZ_TEN], leader_seat: leader, taker_seat: leader },
            });

            const laid = trickOnTheFelt(chairs(WATCHER, positions), last);

            expect(laid.map(({ seat, card }) => [seat, card])).toEqual([
                [seats[0], KARO_SEVEN],
                [seats[1], KARO_ACE],
                [seats[2], HERZ_TEN],
            ]);
        },
    );

    it("shows only the card just led once the next trick begins", () => {
        const next = playing({
            current_trick: [{ seat: 3, card: HERZ_TEN }],
            last_trick: { cards: [KARO_SEVEN, KARO_ACE, { suit: "karo", rank: "ten" }], leader_seat: 1, taker_seat: 3 },
        });

        expect(trickOnTheFelt(chairs(WATCHER), next).map(({ card }) => card)).toEqual([HERZ_TEN]);
    });

    it("lays nothing before the first card", () => {
        expect(trickOnTheFelt(chairs(WATCHER), playing({}))).toEqual([]);
    });

    it("tags the viewer's own card „Du“ and keeps the initial of the account name", () => {
        const named = chairs(2).map((chair) => (chair.is_mine ? { ...chair, occupant_name: "Felix" } : chair));

        expect(trickOnTheFelt(named, twoCards).map(({ name, initial }) => [name, initial])).toEqual([
            ["player 1", "p"],
            [words["play.sideYou"], "F"],
        ]);
    });

    it("tags a card with an empty name when its chair has none", () => {
        const empty = chairs(WATCHER).map((chair) => ({ ...chair, occupant_name: null }));

        expect(trickOnTheFelt(empty, twoCards).map(({ name }) => name)).toEqual(["", ""]);
    });
});

describe("the names of the two sides", () => {
    it.each([
        {
            who: "the declarer",
            viewer: DECLARER_SEAT,
            names: { declarer: words["play.sideUs"], opponents: words["play.sideThem"] },
        },
        { who: "an opponent", viewer: 1, names: { declarer: "player 2", opponents: words["play.sideUs"] } },
        { who: "a watcher", viewer: WATCHER, names: { declarer: "player 2", opponents: words["play.sideThem"] } },
    ])("names the sides as $who sees them", ({ viewer, names }) => {
        expect(sideNames(chairs(viewer), DECLARER_SEAT)).toEqual(names);
    });

    it("names the declarer's side with nothing when its chair has no name", () => {
        const empty = chairs(WATCHER).map((chair) => ({ ...chair, occupant_name: null }));

        expect(sideNames(empty, DECLARER_SEAT)).toEqual({ declarer: "", opponents: words["play.sideThem"] });
    });
});

describe("the cards the viewer may play", () => {
    const legal = [KARO_SEVEN, KARO_ACE];

    it("are the legal cards while it is the viewer's turn", () => {
        expect(cardsToPlay(table(1, { turn_seat: 1, legal_cards: legal }))).toEqual(legal);
    });

    it.each([
        { who: "another seat's turn", viewer: 2, changes: { turn_seat: 1 } },
        { who: "a watcher", viewer: WATCHER, changes: { turn_seat: 1 } },
        { who: "the end of the play", viewer: 1, changes: { turn_seat: null } },
        { who: "a game not yet declared", viewer: 1, changes: null },
    ])("are none at $who", ({ viewer, changes }) => {
        expect(cardsToPlay(table(viewer, changes))).toBeNull();
    });

    it("are none with no hand on the table", () => {
        expect(cardsToPlay({ ...table(1, {}), hand: null })).toBeNull();
    });
});

describe("how a card of the own hand looks", () => {
    const onTurn = (lifted: Card | null): PlayingHand => ({
        legal: [KARO_SEVEN, KARO_ACE],
        lifted,
        disabled: false,
        tap: () => undefined,
    });

    it.each([
        { name: "plain while it is not the viewer's turn", playing: undefined, card: KARO_SEVEN, look: "plain" },
        { name: "legal on turn", playing: onTurn(null), card: KARO_SEVEN, look: "legal" },
        { name: "dimmed on turn when it may not be played", playing: onTurn(null), card: HERZ_TEN, look: "dimmed" },
        { name: "lifted after the first tap", playing: onTurn(KARO_ACE), card: KARO_ACE, look: "lifted" },
        { name: "legal beside the lifted one", playing: onTurn(KARO_ACE), card: KARO_SEVEN, look: "legal" },
    ])("is $name", ({ playing, card, look }) => {
        expect(cardLook(playing, card)).toBe(look);
    });
});

describe("the game in play", () => {
    it("names the declared game, its declarer and the play once the game is declared", () => {
        const declared = table(1, { turn_seat: 1 });

        expect(gameInPlay(declared)).toEqual({
            declaration: { game: "null", hand: true, ouvert: false, announcement: "none" },
            declarerSeat: DECLARER_SEAT,
            playing: playing({}),
        });
    });

    it("is none in a Ramsch, which has no declaration", () => {
        const ramsch = table(1, { turn_seat: 1 });
        ramsch.hand = { ...(ramsch.hand as NonNullable<Table["hand"]>), declaring: null };

        expect(gameInPlay(ramsch)).toBeNull();
        expect(cardsToPlay(ramsch)).toEqual(playing({}).legal_cards);
    });

    it("is none before the game is declared", () => {
        expect(gameInPlay(table(1, null))).toBeNull();
    });

    it("is none with no hand on the table", () => {
        expect(gameInPlay({ ...table(1, {}), hand: null })).toBeNull();
    });
});
