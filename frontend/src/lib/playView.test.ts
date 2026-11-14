import { describe, expect, it } from "vitest";
import {
    bidLineOfGameDeclaredInTheStage,
    cardLook,
    cardsToPlay,
    dragVerdict,
    gameInPlay,
    ownCardSlotOpen,
    pileOf,
    playedCards,
    sideNames,
    trickInPile,
    trickOnTheFelt,
    type PlayingHand,
} from "#lib/playView.ts";
import { SETTLED, type StageState } from "#lib/stage.ts";
import { words } from "#lib/words.ts";
import type { Auction, Card, Chair, LastTrick, Playing, Position, Table } from "../routes/(start)/tables.ts";

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
        former_holder_name: null,
        is_mine_to_return: false,
        nudge: null,
    }));
}

function playing(changes: Partial<Playing>): Playing {
    return {
        turn_seat: 1,
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

function table(mine: number, changes: Partial<Playing> | null): Table {
    return {
        id: "a".repeat(32),
        version: 7,
        chairs: chairs(mine),
        watchers: 0,
        opened_by_me: false,
        result: null,
        hand: {
            dealer_seat: 3,
            own_cards: [],
            skat_count: 2,
            waiting_seat: null,
            abort: null,
            abortable: false,
            ramsch: false,
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
            declaring: {
                declarer_seat: DECLARER_SEAT,
                stage: "declared",
                declaration: { game: "null", hand: true, ouvert: false, announcement: "none" },
                open_cards: [],
            },
            playing: changes === null ? null : playing(changes),
        },
        passed_in: null,
        series: null,
        aborted: null,
        options: null,
        bock: null,
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
        const laid = trickOnTheFelt(chairs(viewer), twoCards, SETTLED, "sweep");

        expect(laid.map(({ seat, slot }) => [seat, slot])).toEqual([
            [1, slots[1]],
            [2, slots[2]],
        ]);
    });

    it("tags each card with its player's name", () => {
        expect(
            trickOnTheFelt(chairs(WATCHER), twoCards, SETTLED, "sweep").map(({ name, card }) => [name, card]),
        ).toEqual([
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
        "keeps the last trick in turn from its leader, seat $leader, until the next card is led, as „liegen lassen“ asks",
        ({ leader, positions, seats }) => {
            const last = playing({
                last_trick: { cards: [KARO_SEVEN, KARO_ACE, HERZ_TEN], leader_seat: leader, taker_seat: leader },
            });

            const laid = trickOnTheFelt(chairs(WATCHER, positions), last, SETTLED, "stay");

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

        expect(trickOnTheFelt(chairs(WATCHER), next, SETTLED, "sweep").map(({ card }) => card)).toEqual([HERZ_TEN]);
    });

    it.each([
        { name: "leads", viewer: 2, turn: 2, current: [], open: true },
        { name: "follows after the cards of both others", viewer: 2, turn: 2, current: [1, 3], open: true },
        { name: "has played already", viewer: 2, turn: 3, current: [1, 2], open: false },
        { name: "waits for another's card", viewer: 2, turn: 1, current: [], open: false },
        { name: "only watches", viewer: WATCHER, turn: 2, current: [], open: false },
    ])("opens the viewer's slot only when the viewer $name", ({ viewer, turn, current, open }) => {
        const cards = current.map((seat) => ({ seat, card: KARO_SEVEN }));
        const view = playing({ turn_seat: turn, current_trick: cards });

        expect(ownCardSlotOpen(chairs(viewer), trickOnTheFelt(chairs(viewer), view, SETTLED, "sweep"), turn)).toBe(
            open,
        );
    });

    it("keeps the viewer's slot shut while the turn is held back", () => {
        const view = playing({ turn_seat: 2 });

        expect(ownCardSlotOpen(chairs(2), trickOnTheFelt(chairs(2), view, SETTLED, "sweep"), undefined)).toBe(false);
    });

    it("lays nothing before the first card", () => {
        expect(trickOnTheFelt(chairs(WATCHER), playing({}), SETTLED, "sweep")).toEqual([]);
    });

    it("tags the viewer's own card „Du“ and keeps the initial of the account name", () => {
        const named = chairs(2).map((chair) => (chair.is_mine ? { ...chair, occupant_name: "Felix" } : chair));

        expect(trickOnTheFelt(named, twoCards, SETTLED, "sweep").map(({ name, initial }) => [name, initial])).toEqual([
            ["player 1", "p"],
            [words["play.sideYou"], "F"],
        ]);
    });

    it("tags a card with an empty name when its chair has none", () => {
        const empty = chairs(WATCHER).map((chair) => ({ ...chair, occupant_name: null }));

        expect(trickOnTheFelt(empty, twoCards, SETTLED, "sweep").map(({ name }) => name)).toEqual(["", ""]);
    });
});

const FINISHED: LastTrick = { cards: [KARO_SEVEN, KARO_ACE, HERZ_TEN], leader_seat: 1, taker_seat: 3 };
const EARLIER: LastTrick = { cards: [KARO_SEVEN, KARO_ACE, HERZ_TEN], leader_seat: 2, taker_seat: 1 };

function onTheMove(phase: StageState["phase"], before: Playing | null = null): StageState {
    return { phase, until: 0, trick: FINISHED, before, glideMilliseconds: 750 };
}

describe("the finished trick on the felt", () => {
    const lead = { seat: 3, card: { suit: "pik", rank: "nine" } satisfies Card };

    it("lies on the felt while the stage holds it, whatever the received table already shows", () => {
        const received = playing({ last_trick: FINISHED, current_trick: [lead] });

        const laid = trickOnTheFelt(chairs(WATCHER), received, onTheMove("resting"), "sweep");

        expect(laid.map(({ card }) => card)).toEqual(FINISHED.cards);
    });

    it("lies on the felt while the stage sweeps it", () => {
        const laid = trickOnTheFelt(chairs(WATCHER), playing({ last_trick: FINISHED }), onTheMove("gliding"), "sweep");

        expect(laid).toHaveLength(FINISHED.cards.length);
    });

    it("is gone from the felt once swept, until the next lead", () => {
        const received = playing({ last_trick: FINISHED });

        expect(trickOnTheFelt(chairs(WATCHER), received, SETTLED, "sweep")).toEqual([]);
    });

    it("stays after the settled stage with „liegen lassen“ and gives way to the next lead", () => {
        const lying = trickOnTheFelt(chairs(WATCHER), playing({ last_trick: FINISHED }), SETTLED, "stay");
        const next = playing({ last_trick: FINISHED, current_trick: [lead] });

        expect(lying).toHaveLength(FINISHED.cards.length);
        expect(trickOnTheFelt(chairs(WATCHER), next, SETTLED, "stay").map(({ card }) => card)).toEqual([lead.card]);
    });

    it("is read in the order it was played, each card with its player's name", () => {
        expect(playedCards(chairs(WATCHER), FINISHED).map(({ seat, name }) => [seat, name])).toEqual([
            [1, "player 1"],
            [2, "player 2"],
            [3, "player 3"],
        ]);
    });
});

describe("the piles of taken tricks", () => {
    const received = playing({
        last_trick: FINISHED,
        taken: [
            { seat: 1, tricks: 1 },
            { seat: 2, tricks: 0 },
            { seat: 3, tricks: 2 },
        ],
    });
    const before = playing({ last_trick: EARLIER, taken: [{ seat: 1, tricks: 1 }] });

    it.each([
        {
            name: "a pile that took nothing is empty",
            seat: 2,
            stage: SETTLED,
            mode: "sweep" as const,
            pile: { tricks: 0, rimmed: false, landing: false },
        },
        {
            name: "the pile of the last trick wears the rim once the trick is swept",
            seat: 3,
            stage: SETTLED,
            mode: "sweep" as const,
            pile: { tricks: 2, rimmed: true, landing: false },
        },
        {
            name: "another pile wears none",
            seat: 1,
            stage: SETTLED,
            mode: "sweep" as const,
            pile: { tricks: 1, rimmed: false, landing: false },
        },
        {
            name: "the taker's pile leaves the resting trick out",
            seat: 3,
            stage: onTheMove("resting", before),
            mode: "sweep" as const,
            pile: { tricks: 1, rimmed: false, landing: false },
        },
        {
            name: "the rim stays on the earlier last trick while the trick rests",
            seat: 1,
            stage: onTheMove("resting", before),
            mode: "sweep" as const,
            pile: { tricks: 1, rimmed: true, landing: false },
        },
        {
            name: "no rim stands while the first trick rests",
            seat: 1,
            stage: onTheMove("resting"),
            mode: "sweep" as const,
            pile: { tricks: 1, rimmed: false, landing: false },
        },
        {
            name: "the taker's pile counts the gliding trick as its landing top",
            seat: 3,
            stage: onTheMove("gliding", before),
            mode: "sweep" as const,
            pile: { tricks: 2, rimmed: true, landing: true },
        },
        {
            name: "the earlier pile loses the rim as the trick glides",
            seat: 1,
            stage: onTheMove("gliding", before),
            mode: "sweep" as const,
            pile: { tricks: 1, rimmed: false, landing: false },
        },
        {
            name: "with „liegen lassen“ the trick on the felt is left out of its pile",
            seat: 3,
            stage: SETTLED,
            mode: "stay" as const,
            pile: { tricks: 1, rimmed: false, landing: false },
        },
        {
            name: "with „liegen lassen“ no pile wears the rim while the trick lies",
            seat: 1,
            stage: onTheMove("resting", before),
            mode: "stay" as const,
            pile: { tricks: 1, rimmed: false, landing: false },
        },
    ])("$name", ({ seat, stage, mode, pile }) => {
        expect(pileOf(seat, received, stage, mode)).toEqual(pile);
    });

    it("gives the rim back to the pile of the last trick once the next lead clears the felt", () => {
        const led = playing({ ...received, current_trick: [{ seat: 3, card: KARO_SEVEN }] });

        expect(pileOf(3, led, SETTLED, "stay")).toEqual({ tricks: 2, rimmed: true, landing: false });
    });

    it("has no last trick in a pile before the first trick is taken", () => {
        expect(trickInPile(playing({}), SETTLED, "sweep")).toBeNull();
    });
});

describe("the names of the two sides", () => {
    it.each([
        {
            who: "the declarer",
            viewer: DECLARER_SEAT,
            names: { declarer: words["result.sideYou"], opponents: words["result.sideThem"] },
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
        play: () => Promise.resolve(true),
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

describe("what a press on a card that moves comes to", () => {
    const CARD_HEIGHT = 140;

    it.each([
        { name: "a tap while it hardly moves", move: { dx: 2, dy: -3 }, verdict: "tap" },
        { name: "a tap when it hardly moves downward", move: { dx: -4, dy: 5 }, verdict: "tap" },
        {
            name: "a return when it is moved upward but short of the threshold",
            move: { dx: 0, dy: -40 },
            verdict: "return",
        },
        { name: "a play when it is moved upward past the threshold", move: { dx: 0, dy: -90 }, verdict: "play" },
        { name: "a play when it is moved upward and a little aside", move: { dx: 25, dy: -90 }, verdict: "play" },
        { name: "a return when it is moved downward", move: { dx: 0, dy: 120 }, verdict: "return" },
        { name: "a return when it is moved sideways", move: { dx: 150, dy: -10 }, verdict: "return" },
    ])("is $name", ({ move, verdict }) => {
        expect(dragVerdict(move, CARD_HEIGHT)).toBe(verdict);
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

describe("the bid of a game declared in the stage of a Ramsch", () => {
    const withAuction = (changes: Partial<Auction>): Table => {
        const base = table(1, {});
        const hand = base.hand as NonNullable<Table["hand"]>;
        return { ...base, hand: { ...hand, auction: { ...hand.auction, ...changes } } };
    };
    const passes = ["pass", "pass", "pass"].map((action, seat) => ({
        seat: seat + 1,
        action: action as "pass",
        value: null,
    }));

    it("is the bid the wire names when the three seats passed and a game is still declared", () => {
        expect(bidLineOfGameDeclaredInTheStage(withAuction({ words: passes, declared: { seat: 2, value: 18 } }))).toBe(
            words["table.bidValue"]({ value: "18" }),
        );
    });

    it("is none for a game the auction declared, which carries a bid or play word", () => {
        const won = [...passes.slice(0, 2), { seat: 3, action: "bid" as const, value: 20 }];

        expect(
            bidLineOfGameDeclaredInTheStage(withAuction({ words: won, declared: { seat: 3, value: 20 } })),
        ).toBeNull();
    });

    it("is none while no game is declared and with no hand on the table", () => {
        expect(bidLineOfGameDeclaredInTheStage(withAuction({ words: passes }))).toBeNull();
        expect(bidLineOfGameDeclaredInTheStage({ ...table(1, {}), hand: null })).toBeNull();
    });
});
