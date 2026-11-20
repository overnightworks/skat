import { describe, expect, it } from "vitest";
import { MOTION_SETS } from "#lib/motionSets.ts";
import { carryOf, landTimeline, lieOf, type Flight, type LandTimeline } from "#lib/takt/land.ts";
import { sampled, type Pose } from "#lib/takt/timeline.ts";
import { RANK_TOKENS, SUIT_TOKENS } from "#lib/wire.ts";
import type { Card } from "../../routes/(start)/tables.ts";

const SEED = "table/1/8";
const NEXT_GAME = "table/1/9";
const DECK: Card[] = SUIT_TOKENS.flatMap((suit) => RANK_TOKENS.map((rank) => ({ suit, rank })));
const ACE: Card = { suit: "kreuz", rank: "ace" };
const SETS = Object.values(MOTION_SETS).map((set) => ({ id: set.id, land: set.land }));
const FLIPPING = MOTION_SETS.verspielt.land;
const FADING = MOTION_SETS.dezent.land;
// A card let go low in the hand, larger and tilted, thrown to a slot above it.
const FROM_THE_HAND: Flight = {
    from: { x: 195, y: 700, width: 84, turn: -6 },
    to: { x: 190, y: 430, width: 70, turn: 0 },
    faceDown: false,
    carry: 12,
};
const FROM_A_FAN: Flight = { ...FROM_THE_HAND, faceDown: true };
const FRAME_SECONDS = 1 / 60;

function landingOf(land: Parameters<typeof landTimeline>[0], flight: Flight = FROM_THE_HAND): LandTimeline {
    const landing = landTimeline(land, flight);
    if (landing === undefined) throw new Error("the card has no landing");
    return landing;
}

const offRest = (pose: Pose): number => Math.hypot(pose.x, pose.y);

describe("the lie of a card", () => {
    it("is the same whenever it is asked for", () => {
        expect(lieOf(SEED, { ...ACE })).toEqual(lieOf(SEED, ACE));
    });

    it("is each card's own, and another one in the next game", () => {
        const lies = [...DECK.map((card) => lieOf(SEED, card)), lieOf(NEXT_GAME, ACE)];

        expect(new Set(lies.map((lie) => JSON.stringify(lie))).size).toBe(lies.length);
    });

    it("stays within an eighth of a card's width to the side and upward and within ten degrees, and is never downward", () => {
        for (const lie of DECK.map((card) => lieOf(SEED, card))) {
            expect(Math.abs(lie.x)).toBeLessThanOrEqual(1 / 8);
            expect(lie.y).toBeGreaterThanOrEqual(-1 / 8);
            expect(lie.y).toBeLessThanOrEqual(0);
            expect(Math.abs(lie.turn)).toBeLessThanOrEqual(10);
        }
    });

    it("lays the cards of a deck to both sides and turns them both ways", () => {
        const lies = DECK.map((card) => lieOf(SEED, card));

        expect(new Set(lies.map((lie) => Math.sign(lie.x)))).toEqual(new Set([-1, 1]));
        expect(new Set(lies.map((lie) => Math.sign(lie.turn)))).toEqual(new Set([-1, 1]));
    });
});

describe.each(SETS)("the toss of a card in the set $id", ({ land }) => {
    it("is the same whenever it is asked for", () => {
        expect(carryOf(SEED, { ...ACE }, land)).toBe(carryOf(SEED, ACE, land));
    });

    it("turns the card within the set's spin, the cards of a deck to either side", () => {
        const carries = DECK.map((card) => carryOf(SEED, card, land));

        for (const carry of carries) {
            expect(Math.abs(carry)).toBeGreaterThanOrEqual(land.spin[0]);
            expect(Math.abs(carry)).toBeLessThanOrEqual(land.spin[1]);
        }
        expect(new Set(carries.map(Math.sign))).toEqual(new Set([-1, 1]));
    });
});

describe.each(SETS)("a landing in the set $id", ({ land }) => {
    const landing = landingOf(land);
    const { card, shade, name } = landing.tracks;
    const { impact } = landing.instants;

    it("starts where the hand let the card go, as large and as turned as it stood there", () => {
        expect(card(0)).toEqual({ x: 5, y: 270, turn: -6, wide: 1.2, tall: 1.2, opacity: 1 });
    });

    it("carries the card through the air above its shade, which is wider and paler the higher the card is", () => {
        const [flying, below] = [card(impact / 2), shade(impact / 2)];

        expect(flying.y).toBeLessThan(below.y);
        expect(flying.x).toBeCloseTo(below.x);
        expect(below.tall).toBeGreaterThan(flying.tall);
        expect(below.opacity).toBeLessThan(flying.opacity);
    });

    it("has the card on the felt at the impact instant, on its shade", () => {
        expect(card(impact)).toEqual(shade(impact));
        expect(shade(impact).opacity).toBe(1);
    });

    it("lands the card short of its place, turned by its toss, and gives way as it hits", () => {
        expect(offRest(card(impact))).toBeGreaterThan(0);
        expect(offRest(card(impact))).toBeLessThan(offRest(card(0)));
        expect(Math.abs(card(impact).turn)).toBeCloseTo(FROM_THE_HAND.carry);
        expect(card(impact + 0.001).tall).toBeLessThan(1);
    });

    it("never carries the card further from its place than it was", () => {
        const ways = sampled(card, landing.seconds, FRAME_SECONDS).map(offRest);

        for (const [index, way] of ways.slice(1).entries()) expect(way).toBeLessThanOrEqual(ways[index] as number);
    });

    it("slides the card to rest after the impact, where the stylesheet puts it", () => {
        const resting = card(landing.seconds);

        expect(landing.seconds).toBeGreaterThan(impact);
        expect(offRest(resting)).toBeCloseTo(0);
        expect(resting.turn).toBeCloseTo(0);
        expect(resting.wide).toBeCloseTo(1, 3);
        expect(resting.tall).toBeCloseTo(1, 3);
        expect(resting.opacity).toBe(1);
        expect(shade(landing.seconds).opacity).toBe(1);
    });

    it("shows the name only once the card lies, and whole at the end", () => {
        expect(name(impact)).toBe(0);
        expect(name(landing.seconds)).toBe(1);
    });

    it("shows a card that leaves face up by its face all the way", () => {
        expect(sampled(landing.tracks.rear, landing.seconds, FRAME_SECONDS)).not.toContain(1);
    });
});

describe("a card out of a hidden hand", () => {
    it("leaves face down and turns over on its way in a set that flips", () => {
        const landing = landingOf(FLIPPING, FROM_A_FAN);
        const { card, rear } = landing.tracks;
        const narrowest = Math.min(
            ...sampled(card, landing.instants.impact, FRAME_SECONDS).map((pose) => pose.wide / pose.tall),
        );

        expect(rear(0)).toBe(1);
        expect(card(0).opacity).toBe(1);
        expect(narrowest).toBeLessThan(0.3);
        expect(rear(landing.instants.impact)).toBe(0);
        expect(card(landing.instants.impact).wide).toBe(card(landing.instants.impact).tall);
    });

    it("fades in as it will lie in a set that does not flip", () => {
        const landing = landingOf(FADING, FROM_A_FAN);
        const { card, rear } = landing.tracks;

        expect(card(0).opacity).toBe(0);
        expect(card(0).turn).toBe(0);
        expect(card(landing.instants.impact).opacity).toBe(1);
        expect(sampled(rear, landing.seconds, FRAME_SECONDS)).not.toContain(1);
    });
});

describe("the way of a landing", () => {
    it("is none for a card with no place to leave from, which lies at once", () => {
        expect(landTimeline(FLIPPING, { ...FROM_THE_HAND, from: undefined })).toBeUndefined();
    });

    it("is measured in the frame the card rests in", () => {
        const below = { x: 190, y: 530, width: 70, turn: 90 };
        const quarterTurned = landingOf(FLIPPING, { ...FROM_THE_HAND, from: below, to: { ...below, y: 430 } });

        expect(quarterTurned.tracks.card(0).x).toBeCloseTo(100);
        expect(quarterTurned.tracks.card(0).y).toBeCloseTo(0);
    });

    it("turns the card the shorter way round", () => {
        const { from, to } = FROM_THE_HAND;
        const landing = landingOf(FLIPPING, {
            ...FROM_THE_HAND,
            from: from && { ...from, turn: 170 },
            to: { ...to, turn: -170 },
        });

        expect(landing.tracks.card(0).turn).toBeCloseTo(-20);
    });
});
