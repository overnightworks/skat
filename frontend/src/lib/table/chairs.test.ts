import { describe, expect, it } from "vitest";
import { declaringAt, FOREHAND, MIDDLEHAND, playing, REARHAND, table } from "#lib/cues.fixtures.ts";
import { auctionWith } from "#lib/table.fixtures.ts";
import type { Chair, Hand, Table } from "../../routes/(start)/tables.ts";
import { chairScenes, seatOnTurn } from "./chairs.ts";
import { surfaceScene } from "./scene.ts";

// A hand in its auction with every card still held; `changes` are what a case is about.
function inHand(changes: Partial<Hand> = {}): Table {
    const dealt = table(1, [10, 10, 10], { declaring: null });
    return { ...dealt, hand: { ...(dealt.hand as Hand), ...changes } };
}

function withChair(source: Table, seat: number, changes: Partial<Chair>): Table {
    return {
        ...source,
        chairs: source.chairs.map((chair) => (chair.seat === seat ? { ...chair, ...changes } : chair)),
    };
}

const BETWEEN_HANDS: Table = {
    ...inHand(),
    hand: null,
    chairs: inHand().chairs.map((chair) => ({ ...chair, hand: null })),
};

const PHASES: readonly { phase: string; hand: Partial<Hand>; seat: number | null }[] = [
    {
        phase: "the auction waits for a bid",
        hand: { auction: auctionWith({ turn_seat: MIDDLEHAND, facing_seat: FOREHAND, awaiting: "bid" }) },
        seat: MIDDLEHAND,
    },
    {
        phase: "the auction waits for an answer",
        hand: { auction: auctionWith({ turn_seat: FOREHAND, facing_seat: MIDDLEHAND, awaiting: "answer" }) },
        seat: FOREHAND,
    },
    { phase: "the auction is over and nothing follows yet", hand: {}, seat: null },
    { phase: "the declarer picks up or declares", hand: { declaring: declaringAt("choosing") }, seat: MIDDLEHAND },
    {
        phase: "the game is declared and no card is asked for yet",
        hand: { declaring: declaringAt("declared") },
        seat: null,
    },
    {
        phase: "the play waits for a card",
        hand: { declaring: declaringAt("declared"), playing: playing({ turn_seat: REARHAND }) },
        seat: REARHAND,
    },
    {
        phase: "a Ramsch waits for a push",
        hand: {
            ramsch: true,
            pushing: { turn_seat: MIDDLEHAND, stage: "choosing", moves: [], factor: 1, put_back_cards: [] },
        },
        seat: MIDDLEHAND,
    },
    {
        phase: "a Ramsch is played",
        hand: { ramsch: true, playing: playing({ turn_seat: FOREHAND }) },
        seat: FOREHAND,
    },
    {
        phase: "the hand waits for a sitter",
        hand: { waiting_seat: REARHAND, playing: playing({ turn_seat: REARHAND }) },
        seat: null,
    },
    {
        phase: "the first card waits for a word",
        hand: {
            declaring: declaringAt("declared"),
            playing: playing({
                turn_seat: FOREHAND,
                kontra: {
                    said: [],
                    factor: 1,
                    my_word: null,
                    my_word_answered: false,
                    first_card_waits_on: [REARHAND],
                    first_card_declined: [],
                },
            }),
        },
        seat: null,
    },
];

describe("seatOnTurn", () => {
    it.each(PHASES)("names $seat while $phase", ({ hand, seat }) => {
        expect(seatOnTurn(inHand(hand))).toBe(seat);
    });

    it("names nobody between hands", () => {
        expect(seatOnTurn(BETWEEN_HANDS)).toBeNull();
    });
});

describe("chairScenes", () => {
    it("tells a free chair, a person, an agent and the viewer apart between hands", () => {
        let seats = withChair(BETWEEN_HANDS, FOREHAND, { occupant_name: "Anna" });
        seats = withChair(seats, MIDDLEHAND, { occupant_name: "Karl", occupant_kind: "agent" });
        seats = withChair(seats, REARHAND, { occupant_name: null, occupant_kind: null });

        expect(chairScenes(seats)).toEqual([
            {
                seat: FOREHAND,
                sitter: { kind: "person", name: "Anna", away: false },
                mine: false,
                hand: null,
                onTurn: false,
                name: "Anna",
            },
            {
                seat: MIDDLEHAND,
                sitter: { kind: "agent", name: "Karl", away: false },
                mine: false,
                hand: null,
                onTurn: false,
                name: "Karl, KI",
            },
            { seat: REARHAND, sitter: { kind: "free" }, mine: false, hand: null, onTurn: false, name: "Freier Platz" },
        ]);
    });

    it("tells each chair's position, the dealer, the cards left and the turn in a hand", () => {
        const running = table(1, [10, 9, 1], { current: [] });

        expect(chairScenes(running).map(({ hand, onTurn, name }) => ({ hand, onTurn, name }))).toEqual([
            {
                hand: { position: "forehand", dealer: false, cardsLeft: 10 },
                onTurn: true,
                name: "player 1, Vorhand, 10 Karten, am Zug",
            },
            {
                hand: { position: "middlehand", dealer: false, cardsLeft: 9 },
                onTurn: false,
                name: "player 2, Mittelhand, 9 Karten",
            },
            {
                hand: { position: "rearhand", dealer: true, cardsLeft: 1 },
                onTurn: false,
                name: "player 3, Hinterhand, Geber, 1 Karte",
            },
        ]);
    });

    it("names the viewer's own chair „Du“ and says who is away", () => {
        let seats = withChair(inHand(), FOREHAND, { is_mine: true });
        seats = withChair(seats, MIDDLEHAND, { is_away: true });

        const [own, away] = chairScenes(seats);

        expect(own).toMatchObject({ mine: true, name: "Du, Vorhand, 10 Karten" });
        expect(away).toMatchObject({
            sitter: { kind: "person", name: "player 2", away: true },
            name: "player 2, nicht da, Mittelhand, 10 Karten",
        });
    });

    it("lists the chairs in seat order whatever order the table brings", () => {
        const reversed = { ...inHand(), chairs: inHand().chairs.toReversed() };

        expect(chairScenes(reversed).map((chair) => chair.seat)).toEqual([FOREHAND, MIDDLEHAND, REARHAND]);
    });
});

describe("surfaceScene", () => {
    it("names the table for its landmark and carries the chairs, the taps and the seat sentence", () => {
        const scene = surfaceScene(BETWEEN_HANDS, { lamp: 2 }, "Anna ist aufgestanden");

        expect(scene).toEqual({
            name: "Skattisch",
            chairs: chairScenes(BETWEEN_HANDS),
            taps: { lamp: 2 },
            notice: "Anna ist aufgestanden",
        });
    });
});
